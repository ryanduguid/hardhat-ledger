"""Determinism and release-content tests for the portable builder."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts import build_release


SKILL_NAMES = (
    "coal-lsl-levy",
    "contract-cost-tracking",
    "contracting-exports",
    "contractor-super-tpar",
    "fuel-tax-credits",
    "payroll-tax-contractors",
    "plant-and-equipment-costing",
    "progress-claim-preparation",
    "retention-schedule",
    "wip-over-under-billing",
)
FIXED_GIT_DATE = "2026-08-15T01:02:03Z"


class ReleaseRepository:
    """Small committed repository used to exercise the builder."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True)
        self._git("init", "--initial-branch=main")
        self._git("config", "core.autocrlf", "false")
        self._write("LICENSE", "fixture\r\n")
        self._write("docs/releases/v0.1.1.md", "# v0.1.1\r\nreview\r")
        self._write("line-endings.md", "first\r\nsecond\rthird\n")
        for name in SKILL_NAMES:
            self._write(
                f".claude/skills/{name}/SKILL.md",
                f"---\r\nname: {name}\r\ndescription: fixture\r\n---\r\n",
            )
        self.write_marketplace(SKILL_NAMES)
        self.commit("fixture release")

    def _git(self, *arguments: str, environment: dict[str, str] | None = None) -> str:
        process = subprocess.run(
            ["git", *arguments],
            cwd=self.root,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
        )
        if process.returncode:
            raise AssertionError(process.stderr)
        return process.stdout.strip()

    def _write(self, relative_path: str, content: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content.encode("utf-8"))

    def write_marketplace(
        self,
        skills: tuple[str, ...] | list[str],
        *,
        version: str | None = None,
    ) -> None:
        plugin: dict[str, object] = {
            "name": build_release.PRODUCT_NAME,
            "source": "./",
            "skills": [f"./.claude/skills/{name}" for name in skills],
        }
        if version is not None:
            plugin["version"] = version
        marketplace = {"name": "fixture", "plugins": [plugin]}
        self._write(
            ".claude-plugin/marketplace.json",
            json.dumps(marketplace, indent=2) + "\n",
        )

    def commit(self, message: str) -> None:
        self._git("add", "--all")
        environment = os.environ.copy()
        environment.update(
            {
                "GIT_AUTHOR_DATE": FIXED_GIT_DATE,
                "GIT_COMMITTER_DATE": FIXED_GIT_DATE,
            }
        )
        self._git(
            "-c",
            "user.name=Release Test",
            "-c",
            "user.email=release-test@example.invalid",
            "commit",
            "--quiet",
            "-m",
            message,
            environment=environment,
        )


class ReleaseBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repository = ReleaseRepository(self.base / "repository")

    def build(self, output_name: str = "output") -> build_release.BuildResult:
        return build_release.build_release(
            self.repository.root,
            self.base / output_name,
            "v0.1.1",
        )

    def test_repeated_builds_are_byte_identical(self) -> None:
        first = self.build("first")
        second = self.build("second")

        self.assertEqual([path.name for path in first.assets], [path.name for path in second.assets])
        for first_path, second_path in zip(first.assets, second.assets, strict=True):
            with self.subTest(asset=first_path.name):
                self.assertEqual(first_path.read_bytes(), second_path.read_bytes())

    def test_archives_have_the_same_sorted_lf_normalised_source_tree(self) -> None:
        result = self.build()
        root = f"{build_release.PRODUCT_NAME}-v0.1.1"
        zip_path = next(path for path in result.assets if path.suffix == ".zip")
        tar_path = next(path for path in result.assets if path.name.endswith(".tar.gz"))
        expected_epoch = int(
            dt.datetime(2026, 8, 15, 1, 2, 3, tzinfo=dt.timezone.utc).timestamp()
        )

        with zipfile.ZipFile(zip_path) as archive:
            infos = archive.infolist()
            self.assertEqual(
                [info.filename.rstrip("/") for info in infos],
                sorted(info.filename.rstrip("/") for info in infos),
            )
            zip_files = {
                info.filename: archive.read(info)
                for info in infos
                if not info.is_dir()
            }
            for info in infos:
                self.assertEqual(info.date_time, (2026, 8, 15, 1, 2, 2))
                expected_mode = 0o755 if info.is_dir() else 0o644
                self.assertEqual((info.external_attr >> 16) & 0o777, expected_mode)

        with tarfile.open(tar_path, "r:gz") as archive:
            members = archive.getmembers()
            self.assertEqual([member.name for member in members], sorted(member.name for member in members))
            tar_files = {
                member.name: archive.extractfile(member).read()
                for member in members
                if member.isfile()
            }
            for member in members:
                self.assertEqual(member.mtime, expected_epoch)
                self.assertEqual(member.uid, 0)
                self.assertEqual(member.gid, 0)
                self.assertEqual(member.uname, "")
                self.assertEqual(member.gname, "")
                self.assertEqual(member.mode, 0o755 if member.isdir() else 0o644)

        self.assertEqual(zip_files, tar_files)
        self.assertEqual(
            zip_files[f"{root}/line-endings.md"],
            b"first\nsecond\nthird\n",
        )
        skill_entries = [
            name
            for name in zip_files
            if name.startswith(f"{root}/.claude/skills/") and name.endswith("/SKILL.md")
        ]
        self.assertEqual(len(skill_entries), 10)
        self.assertIn(f"{root}/.claude-plugin/marketplace.json", zip_files)

    def test_checksums_cover_exactly_the_two_archives_and_sbom(self) -> None:
        result = self.build()
        checksum_path = next(path for path in result.assets if path.name == "SHA256SUMS")
        lines = checksum_path.read_text(encoding="ascii").splitlines()
        parsed = [line.split("  ", maxsplit=1) for line in lines]
        self.assertEqual(
            [name for _, name in parsed],
            sorted(path.name for path in result.assets if path.name != "SHA256SUMS"),
        )
        for digest, name in parsed:
            asset = checksum_path.parent / name
            self.assertEqual(digest, hashlib.sha256(asset.read_bytes()).hexdigest())

    def test_sbom_is_deterministic_spdx_2_3_for_every_source_file(self) -> None:
        result = self.build()
        sbom_path = next(path for path in result.assets if path.name.endswith(".spdx.json"))
        sbom = json.loads(sbom_path.read_text(encoding="utf-8"))

        self.assertEqual(sbom["spdxVersion"], "SPDX-2.3")
        self.assertEqual(sbom["dataLicense"], "CC0-1.0")
        self.assertEqual(sbom["creationInfo"]["created"], "2026-08-15T01:02:03Z")
        self.assertTrue(sbom["documentNamespace"].endswith(result.tree))
        package = sbom["packages"][0]
        self.assertEqual(package["versionInfo"], "0.1.1")
        self.assertEqual(package["licenseDeclared"], "MIT")

        tracked = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", "HEAD"],
            cwd=self.repository.root,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.splitlines()
        spdx_names = [item["fileName"].removeprefix("./") for item in sbom["files"]]
        self.assertEqual(spdx_names, sorted(tracked))
        relationships = sbom["relationships"]
        self.assertEqual(
            sum(item["relationshipType"] == "CONTAINS" for item in relationships),
            len(tracked),
        )

    def test_builder_rejects_a_stale_marketplace_version(self) -> None:
        self.repository.write_marketplace(SKILL_NAMES, version="0.1.1")
        self.repository.commit("pin stale version")
        with self.assertRaisesRegex(build_release.BuildError, "must not pin a stale version"):
            self.build()

    def test_builder_rejects_a_release_with_other_than_ten_skills(self) -> None:
        missing = SKILL_NAMES[-1]
        (self.repository.root / ".claude" / "skills" / missing / "SKILL.md").unlink()
        self.repository.write_marketplace(list(SKILL_NAMES[:-1]))
        self.repository.commit("remove one skill")
        with self.assertRaisesRegex(build_release.BuildError, "exactly 10 discoverable skills"):
            self.build()

    def test_builder_rejects_dirty_tracked_source(self) -> None:
        (self.repository.root / "LICENSE").write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(build_release.BuildError, "must be committed"):
            self.build()

    def test_builder_rejects_a_nonempty_output_directory(self) -> None:
        output = self.base / "output"
        output.mkdir()
        (output / "existing").write_text("keep", encoding="utf-8")
        with self.assertRaisesRegex(build_release.BuildError, "must be empty"):
            self.build()
        self.assertEqual((output / "existing").read_text(encoding="utf-8"), "keep")

    def test_builder_will_never_rebuild_v0_1_0(self) -> None:
        with self.assertRaisesRegex(build_release.BuildError, "must never be rebuilt"):
            build_release.build_release(
                self.repository.root,
                self.base / "output",
                "v0.1.0",
            )


if __name__ == "__main__":
    unittest.main()
