#!/usr/bin/env python3
"""Build reproducible source archives, checksums and an SPDX 2.3 SBOM.

The builder reads the committed ``HEAD`` tree rather than the working tree.
Text blobs that decode as UTF-8 are normalised to LF before packaging. Archive
timestamps come from the ``HEAD`` commit time in UTC, and ownership metadata is
fixed so the same commit produces byte-identical assets on each supported OS.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import gzip
import hashlib
import io
import json
import re
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence


REPOSITORY_SLUG = "ryanduguid/hardhat-ledger"
PRODUCT_NAME = "subcontractor-accounting-skills"
EXPECTED_SKILL_COUNT = 10
FROZEN_VERSION = "v0.1.0"
VERSION_PATTERN = re.compile(r"^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")


class BuildError(RuntimeError):
    """A release precondition or deterministic-build rule was not met."""


@dataclasses.dataclass(frozen=True)
class SourceFile:
    """A normal file from the committed Git tree."""

    path: str
    mode: int
    data: bytes


@dataclasses.dataclass(frozen=True)
class BuildResult:
    """Paths and source identity for a completed release build."""

    version: str
    commit: str
    tree: str
    output_directory: Path
    assets: tuple[Path, ...]


def _git(repository: Path, *arguments: str) -> bytes:
    process = subprocess.run(
        ["git", *arguments],
        cwd=repository,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if process.returncode:
        detail = process.stderr.decode("utf-8", errors="replace").strip()
        raise BuildError(f"git {' '.join(arguments)} failed: {detail}")
    return process.stdout


def _normalise_text(data: bytes) -> bytes:
    """Convert UTF-8 text line endings to LF and leave binary blobs unchanged."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return data
    return text.replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")


def _committed_sources(repository: Path) -> tuple[SourceFile, ...]:
    output = _git(repository, "ls-tree", "-r", "-z", "--full-tree", "HEAD")
    sources: list[SourceFile] = []
    for raw_record in output.split(b"\0"):
        if not raw_record:
            continue
        metadata, separator, raw_path = raw_record.partition(b"\t")
        if not separator:
            raise BuildError("could not parse git ls-tree output")
        fields = metadata.split()
        if len(fields) != 3:
            raise BuildError("could not parse git ls-tree metadata")
        raw_mode, object_type, object_id = fields
        if object_type != b"blob" or raw_mode not in {b"100644", b"100755"}:
            path = raw_path.decode("utf-8", errors="replace")
            raise BuildError(
                f"unsupported tracked entry {path!r}: only regular files are releasable"
            )
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError as error:
            raise BuildError("tracked paths must be valid UTF-8") from error
        if PurePosixPath(path).is_absolute() or ".." in PurePosixPath(path).parts:
            raise BuildError(f"unsafe tracked path: {path!r}")
        data = _git(repository, "cat-file", "blob", object_id.decode("ascii"))
        sources.append(
            SourceFile(
                path=path,
                mode=0o755 if raw_mode == b"100755" else 0o644,
                data=_normalise_text(data),
            )
        )
    sources.sort(key=lambda item: item.path)
    if not sources:
        raise BuildError("the committed source tree is empty")
    return tuple(sources)


def _source_map(sources: Iterable[SourceFile]) -> dict[str, SourceFile]:
    return {source.path: source for source in sources}


def _validate_marketplace(sources: Sequence[SourceFile], version: str) -> None:
    by_path = _source_map(sources)
    marketplace_path = ".claude-plugin/marketplace.json"
    if marketplace_path not in by_path:
        raise BuildError("the release must contain .claude-plugin/marketplace.json")
    try:
        marketplace = json.loads(by_path[marketplace_path].data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise BuildError("marketplace.json must be valid UTF-8 JSON") from error
    if not isinstance(marketplace, dict):
        raise BuildError("marketplace.json must contain a JSON object")
    if "version" in marketplace:
        raise BuildError("marketplace metadata must not pin a version")

    plugins = marketplace.get("plugins")
    if not isinstance(plugins, list) or len(plugins) != 1:
        raise BuildError("marketplace.json must declare exactly one plugin")
    plugin = plugins[0]
    if not isinstance(plugin, dict):
        raise BuildError("the marketplace plugin must be a JSON object")
    if plugin.get("name") != PRODUCT_NAME:
        raise BuildError(f"the marketplace plugin must be named {PRODUCT_NAME!r}")
    if plugin.get("source") != "./":
        raise BuildError("the marketplace plugin source must be './'")
    if "version" in plugin:
        raise BuildError("marketplace metadata must not pin a stale version")

    declared = plugin.get("skills")
    if not isinstance(declared, list) or not all(
        isinstance(item, str) for item in declared
    ):
        raise BuildError("the marketplace skills field must be a list of paths")
    if len(declared) != len(set(declared)):
        raise BuildError("the marketplace skills list contains duplicates")

    discovered = sorted(
        str(PurePosixPath(source.path).parent)
        for source in sources
        if len(PurePosixPath(source.path).parts) == 4
        and PurePosixPath(source.path).parts[:2] == (".claude", "skills")
        and PurePosixPath(source.path).name == "SKILL.md"
    )
    declared_normalised: list[str] = []
    for item in declared:
        if not item.startswith("./") or item.endswith("/"):
            raise BuildError(f"marketplace skill path is not canonical: {item!r}")
        path = str(PurePosixPath(item[2:]))
        if path not in discovered:
            raise BuildError(f"marketplace skill is not discoverable: {item!r}")
        declared_normalised.append(path)

    if len(discovered) != EXPECTED_SKILL_COUNT:
        raise BuildError(
            f"release must contain exactly {EXPECTED_SKILL_COUNT} discoverable skills; "
            f"found {len(discovered)}"
        )
    if sorted(declared_normalised) != discovered:
        raise BuildError("marketplace inventory does not match the discoverable skills")

    notes_path = f"docs/releases/{version}.md"
    if notes_path not in by_path:
        raise BuildError(f"release notes are missing from the committed tree: {notes_path}")


def _archive_entries(sources: Sequence[SourceFile], root: str) -> tuple[str, ...]:
    entries: set[str] = {f"{root}/"}
    for source in sources:
        archive_path = PurePosixPath(root) / source.path
        for parent in archive_path.parents:
            if str(parent) == ".":
                continue
            entries.add(f"{parent.as_posix().rstrip('/')}/")
        entries.add(archive_path.as_posix())
    # Sort directory names as paths rather than by their archive-only trailing
    # slash. This keeps ZIP and tar member order aligned after tar readers strip
    # that slash from directory names.
    return tuple(sorted(entries, key=lambda item: item.rstrip("/")))


def _zip_timestamp(epoch: int) -> tuple[int, int, int, int, int, int]:
    timestamp = time.gmtime(epoch)
    year = timestamp.tm_year
    if not 1980 <= year <= 2107:
        raise BuildError("the commit timestamp is outside the ZIP timestamp range")
    return (
        year,
        timestamp.tm_mon,
        timestamp.tm_mday,
        timestamp.tm_hour,
        timestamp.tm_min,
        timestamp.tm_sec - (timestamp.tm_sec % 2),
    )


def _write_zip(
    destination: Path,
    sources: Sequence[SourceFile],
    root: str,
    epoch: int,
) -> None:
    by_archive_path = {f"{root}/{item.path}": item for item in sources}
    timestamp = _zip_timestamp(epoch)
    with zipfile.ZipFile(destination, "w", allowZip64=True) as archive:
        for name in _archive_entries(sources, root):
            info = zipfile.ZipInfo(filename=name, date_time=timestamp)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.flag_bits = 0
            if name.endswith("/"):
                info.external_attr = (0o040755 << 16) | 0x10
                data = b""
            else:
                source = by_archive_path[name]
                info.external_attr = (0o100000 | source.mode) << 16
                data = source.data
            archive.writestr(info, data)


def _write_tar_gz(
    destination: Path,
    sources: Sequence[SourceFile],
    root: str,
    epoch: int,
) -> None:
    by_archive_path = {f"{root}/{item.path}": item for item in sources}
    with destination.open("wb") as raw_file:
        with gzip.GzipFile(
            filename="",
            mode="wb",
            compresslevel=9,
            fileobj=raw_file,
            mtime=epoch,
        ) as gzip_file:
            with tarfile.open(
                fileobj=gzip_file,
                mode="w",
                format=tarfile.PAX_FORMAT,
            ) as archive:
                for name in _archive_entries(sources, root):
                    info = tarfile.TarInfo(name=name)
                    info.mtime = epoch
                    info.uid = 0
                    info.gid = 0
                    info.uname = ""
                    info.gname = ""
                    if name.endswith("/"):
                        info.type = tarfile.DIRTYPE
                        info.mode = 0o755
                        info.size = 0
                        archive.addfile(info)
                    else:
                        source = by_archive_path[name]
                        info.type = tarfile.REGTYPE
                        info.mode = source.mode
                        info.size = len(source.data)
                        archive.addfile(info, io.BytesIO(source.data))


def _checksum(algorithm: str, data: bytes) -> str:
    digest = hashlib.new(algorithm)
    digest.update(data)
    return digest.hexdigest()


def _spdx_identifier(path: str) -> str:
    suffix = hashlib.sha256(path.encode("utf-8")).hexdigest()[:24]
    return f"SPDXRef-File-{suffix}"


def _spdx_document(
    sources: Sequence[SourceFile],
    version: str,
    commit: str,
    tree: str,
    epoch: int,
) -> bytes:
    package_id = "SPDXRef-Package"
    files: list[dict[str, object]] = []
    relationships: list[dict[str, str]] = [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": package_id,
        }
    ]
    verification_inputs: list[str] = []
    for source in sources:
        sha1 = _checksum("sha1", source.data)
        sha256 = _checksum("sha256", source.data)
        file_id = _spdx_identifier(source.path)
        verification_inputs.append(sha1)
        files.append(
            {
                "SPDXID": file_id,
                "checksums": [
                    {"algorithm": "SHA1", "checksumValue": sha1},
                    {"algorithm": "SHA256", "checksumValue": sha256},
                ],
                "copyrightText": "Copyright (c) 2026 Ryan Duguid",
                "fileName": f"./{source.path}",
                "licenseConcluded": "NOASSERTION",
            }
        )
        relationships.append(
            {
                "spdxElementId": package_id,
                "relationshipType": "CONTAINS",
                "relatedSpdxElement": file_id,
            }
        )

    verification_code = _checksum(
        "sha1", "".join(sorted(verification_inputs)).encode("ascii")
    )
    created = dt.datetime.fromtimestamp(epoch, tz=dt.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    plain_version = version.removeprefix("v")
    document = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "created": created,
            "creators": [f"Tool: {PRODUCT_NAME}-release-builder"],
        },
        "dataLicense": "CC0-1.0",
        "documentDescribes": [package_id],
        "documentNamespace": (
            f"https://github.com/{REPOSITORY_SLUG}/releases/tag/{version}"
            f"#spdx-{tree}"
        ),
        "files": files,
        "name": f"{PRODUCT_NAME}-{version}",
        "packages": [
            {
                "SPDXID": package_id,
                "copyrightText": "Copyright (c) 2026 Ryan Duguid",
                "downloadLocation": (
                    f"https://github.com/{REPOSITORY_SLUG}/tree/{commit}"
                ),
                "filesAnalyzed": True,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "MIT",
                "name": PRODUCT_NAME,
                "packageVerificationCode": {
                    "packageVerificationCodeValue": verification_code
                },
                "supplier": "Person: Ryan Duguid",
                "versionInfo": plain_version,
            }
        ],
        "relationships": relationships,
        "spdxVersion": "SPDX-2.3",
        "comment": f"Source tree {tree} at commit {commit}.",
    }
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )


def _prepare_output_directory(output_directory: Path) -> None:
    if output_directory.exists():
        if not output_directory.is_dir():
            raise BuildError("the output path exists and is not a directory")
        if any(output_directory.iterdir()):
            raise BuildError("the output directory must be empty")
    else:
        output_directory.mkdir(parents=True)


def build_release(repository: Path, output_directory: Path, version: str) -> BuildResult:
    """Build all v0.1.1-style release assets from a clean committed tree."""
    repository = repository.resolve()
    output_directory = output_directory.resolve()
    match = VERSION_PATTERN.fullmatch(version)
    if match is None:
        raise BuildError("version must be a canonical vMAJOR.MINOR.PATCH tag")
    if version == FROZEN_VERSION:
        raise BuildError(f"{FROZEN_VERSION} is immutable and must never be rebuilt")
    if not (repository / ".git").exists():
        # Linked worktrees use a .git file, while ordinary repositories use a directory.
        if not (repository / ".git").is_file():
            raise BuildError("repository must be the root of a Git worktree")

    dirty = _git(repository, "status", "--porcelain", "--untracked-files=no")
    if dirty.strip():
        raise BuildError("tracked working-tree changes must be committed before building")

    commit = _git(repository, "rev-parse", "HEAD").decode("ascii").strip()
    tree = _git(repository, "rev-parse", "HEAD^{tree}").decode("ascii").strip()
    try:
        epoch = int(
            _git(repository, "show", "-s", "--format=%ct", "HEAD")
            .decode("ascii")
            .strip()
        )
    except ValueError as error:
        raise BuildError("HEAD has an invalid commit timestamp") from error

    sources = _committed_sources(repository)
    _validate_marketplace(sources, version)
    _prepare_output_directory(output_directory)

    root = f"{PRODUCT_NAME}-{version}"
    zip_name = f"{root}.zip"
    tar_name = f"{root}.tar.gz"
    sbom_name = f"{root}.spdx.json"
    checksum_name = "SHA256SUMS"
    zip_path = output_directory / zip_name
    tar_path = output_directory / tar_name
    sbom_path = output_directory / sbom_name
    checksum_path = output_directory / checksum_name

    _write_zip(zip_path, sources, root, epoch)
    _write_tar_gz(tar_path, sources, root, epoch)
    sbom_path.write_bytes(
        _spdx_document(sources, version, commit, tree, epoch)
    )

    checksummed_assets = sorted((zip_path, tar_path, sbom_path), key=lambda item: item.name)
    checksum_lines = [
        f"{_checksum('sha256', asset.read_bytes())}  {asset.name}"
        for asset in checksummed_assets
    ]
    checksum_path.write_bytes(("\n".join(checksum_lines) + "\n").encode("ascii"))

    assets = (zip_path, tar_path, sbom_path, checksum_path)
    return BuildResult(
        version=version,
        commit=commit,
        tree=tree,
        output_directory=output_directory,
        assets=assets,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repository",
        type=Path,
        default=Path.cwd(),
        help="Git worktree root (default: current directory)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dist"),
        help="absent or empty output directory (default: dist)",
    )
    parser.add_argument("--version", required=True, help="release tag, for example v0.1.1")
    return parser


def main(arguments: Sequence[str] | None = None) -> int:
    options = _parser().parse_args(arguments)
    try:
        result = build_release(options.repository, options.output_dir, options.version)
    except BuildError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(f"Built {result.version} from commit {result.commit}")
    for asset in result.assets:
        print(asset)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
