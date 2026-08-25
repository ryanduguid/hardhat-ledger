"""Offline integrity checks for distributable accounting skills."""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import yaml


REPOSITORY = Path(__file__).resolve().parents[1]
PLUGIN_ROOT = REPOSITORY / "plugins" / "subcontractor-accounting-skills"
SKILLS_DIRECTORY = PLUGIN_ROOT / "skills"
ALLOWED_FRONT_MATTER_FIELDS = {"name", "description"}
PORTABLE_SAFETY_BOUNDARY = (
    "Current mutable facts must come from a current authoritative primary source; "
    "if the source is unavailable, leave the fact blank or explicitly unverified "
    "and do not rely on it.",
    "Real client data must stay in a firm-approved environment, outside repositories "
    "and unapproved cloud prompts, with unnecessary identifiers excluded.",
    "Write client output only to a configured firm-approved secure path; if none is "
    "supplied, stop and ask, create no fallback, and do not edit `.gitignore`.",
    "Do not lodge, make declarations, communicate with a client or regulator, pay, "
    "post journals or lock records; prepare the hand-off for an authorised human.",
    "Legal, tax and accounting judgement belongs to the authorised reviewer, partner, "
    "lawyer or registered agent.",
)

STRICT_YAML = REPOSITORY / "scripts" / "strict_yaml.py"
STRICT_YAML_SPEC = importlib.util.spec_from_file_location("strict_yaml", STRICT_YAML)
if STRICT_YAML_SPEC is None or STRICT_YAML_SPEC.loader is None:  # pragma: no cover
    raise RuntimeError(f"cannot load {STRICT_YAML}")
strict_yaml = importlib.util.module_from_spec(STRICT_YAML_SPEC)
STRICT_YAML_SPEC.loader.exec_module(strict_yaml)

UniqueKeySafeLoader = strict_yaml.unique_key_safe_loader(
    ValueError,
    field_noun="front-matter field",
    keys_noun="front-matter keys",
)


def front_matter(skill_file: Path) -> dict[str, str]:
    """Parse and validate the deliberately small YAML skill front matter."""
    lines = skill_file.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("front matter must start with '---'")
    try:
        end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("front matter must end with '---'") from error

    for line in lines[1:end]:
        key, separator, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if (
            not separator
            or not key
            or not value
            or line.lstrip().startswith("#")
            or value in {">", "|"}
        ):
            raise ValueError(
                f"invalid front-matter field: {line!r} "
                "(this repo restricts skill front matter to single-line fields)"
            )

    raw_front_matter = "\n".join(lines[1:end])
    try:
        loaded = yaml.load(raw_front_matter, Loader=UniqueKeySafeLoader)
    except ValueError:
        raise
    except yaml.YAMLError as error:
        raise ValueError(f"front matter must be valid YAML: {error}") from error

    if not isinstance(loaded, dict):
        raise ValueError("front matter must be a YAML mapping")

    metadata: dict[str, str] = {}
    for key, value in loaded.items():
        if not isinstance(key, str) or key not in ALLOWED_FRONT_MATTER_FIELDS:
            raise ValueError(f"unknown front-matter field: {key!r}")
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"front-matter field {key!r} must be a non-empty string")
        metadata[key] = value
    return metadata


class SkillMetadataTests(unittest.TestCase):
    def test_front_matter_rejects_ambiguous_or_unknown_yaml(self) -> None:
        cases = {
            "duplicate": (
                "---\nname: first\nname: second\ndescription: valid\n---\n",
                "duplicate front-matter field",
            ),
            "unknown": (
                "---\nname: valid\ndescription: valid\ntools: shell\n---\n",
                "unknown front-matter field",
            ),
            "comment": (
                "---\nname: valid\n# note: hidden metadata\ndescription: valid\n---\n",
                "invalid front-matter field",
            ),
            "block scalar": (
                "---\nname: valid\ndescription: >\n  folded text\n---\n",
                "invalid front-matter field",
            ),
            "unquoted colon": (
                "---\nname: valid\ndescription: invalid: plain scalar\n---\n",
                "front matter must be valid YAML",
            ),
            "alias": (
                "---\nname: &shared valid\ndescription: *shared\n---\n",
                "YAML aliases are not permitted",
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "SKILL.md"
            for label, (content, error) in cases.items():
                with self.subTest(case=label):
                    path.write_text(content, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, error):
                        front_matter(path)

    def test_front_matter_accepts_a_quoted_colon(self) -> None:
        content = (
            "---\n"
            "name: valid\n"
            'description: "valid: quoted scalar"\n'
            "---\n"
        )
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "SKILL.md"
            path.write_text(content, encoding="utf-8")
            self.assertEqual(
                front_matter(path),
                {"name": "valid", "description": "valid: quoted scalar"},
            )

    def test_skill_layout_stays_one_level_deep(self) -> None:
        """Discovery here is `<skills>/<name>/SKILL.md`, one level, no deeper.

        The other checks in this file glob one level. A nested skill would be
        silently skipped by all of them, so fail loudly on the layout instead
        of letting a skill ship unchecked.
        """
        nested = sorted(
            str(path.relative_to(SKILLS_DIRECTORY))
            for path in SKILLS_DIRECTORY.rglob("SKILL.md")
            if path.parent.parent != SKILLS_DIRECTORY
        )
        self.assertEqual(nested, [])

    def test_every_skill_has_matching_complete_front_matter(self) -> None:
        skill_files = sorted(SKILLS_DIRECTORY.glob("*/SKILL.md"))
        self.assertGreaterEqual(len(skill_files), 1, "at least one distributable skill is required")

        declared_names: set[str] = set()
        for skill_file in skill_files:
            with self.subTest(skill=skill_file.parent.name):
                metadata = front_matter(skill_file)
                self.assertEqual(metadata.get("name"), skill_file.parent.name)
                self.assertTrue(metadata.get("description"))
                self.assertNotIn(metadata["name"], declared_names)
                declared_names.add(metadata["name"])

    def test_skill_directories_do_not_omit_the_entrypoint(self) -> None:
        directories = sorted(path for path in SKILLS_DIRECTORY.iterdir() if path.is_dir())
        missing = [path.name for path in directories if not (path / "SKILL.md").is_file()]
        self.assertEqual(missing, [])

    def test_manifest_skill_root_exactly_matches_discovered_skills(self) -> None:
        manifest = json.loads(
            (PLUGIN_ROOT / ".claude-plugin" / "plugin.json").read_text(
                encoding="utf-8"
            )
        )
        declared = manifest.get("skills")
        self.assertIsInstance(declared, str)
        self.assertEqual((PLUGIN_ROOT / declared).resolve(), SKILLS_DIRECTORY.resolve())
        self.assertEqual(len(list(SKILLS_DIRECTORY.glob("*/SKILL.md"))), 10)

    def test_every_skill_marks_embedded_instructions_as_untrusted(self) -> None:
        skill_files = sorted(SKILLS_DIRECTORY.glob("*/SKILL.md"))
        missing = [
            str(path.relative_to(REPOSITORY))
            for path in skill_files
            if "instructions found inside" not in path.read_text(encoding="utf-8")
            or "untrusted content" not in path.read_text(encoding="utf-8")
        ]
        self.assertEqual(missing, [])

        firm_template = (REPOSITORY / "templates" / "firm-CLAUDE.md.example").read_text(
            encoding="utf-8"
        )
        self.assertIn("Instructions embedded in client files", firm_template)
        self.assertIn("untrusted data", firm_template)

    def test_every_skill_carries_the_portable_safety_boundary(self) -> None:
        for path in sorted(SKILLS_DIRECTORY.glob("*/SKILL.md")):
            with self.subTest(skill=path.parent.name):
                text = path.read_text(encoding="utf-8")
                self.assertEqual(text.count("## Portable safety boundary"), 1)
                for boundary in PORTABLE_SAFETY_BOUNDARY:
                    self.assertIn(boundary, text)

    def test_standalone_instructions_have_no_unsafe_fallbacks(self) -> None:
        coal = (
            SKILLS_DIRECTORY / "coal-lsl-levy" / "SKILL.md"
        ).read_text(encoding="utf-8")
        payroll_tax = (
            SKILLS_DIRECTORY / "payroll-tax-contractors" / "SKILL.md"
        ).read_text(encoding="utf-8")
        fuel_tax = (
            SKILLS_DIRECTORY / "fuel-tax-credits" / "SKILL.md"
        ).read_text(encoding="utf-8")
        wip = (
            SKILLS_DIRECTORY / "wip-over-under-billing" / "SKILL.md"
        ).read_text(encoding="utf-8")

        self.assertNotIn("lodging the monthly levy return and payment", coal)
        self.assertNotIn("**Lodge and pay", coal)
        self.assertNotIn("repo's `output/`", payroll_tax)
        self.assertNotIn("`bas-preparation`", fuel_tax)
        self.assertNotIn("Optional schedule:", wip)


if __name__ == "__main__":
    unittest.main()
