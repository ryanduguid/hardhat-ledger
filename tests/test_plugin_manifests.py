"""Cross-runtime plugin packaging regression gates."""

from __future__ import annotations

import json
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
PLUGIN_NAME = "subcontractor-accounting-skills"
PLUGIN_ROOT = REPOSITORY / "plugins" / PLUGIN_NAME
EXPECTED_SKILLS = {
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
}
COMPONENT_FIELDS = {
    "commands",
    "agents",
    "skills",
    "hooks",
    "mcpServers",
    "lspServers",
}


def load_json(path: Path) -> dict[str, object]:
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise TypeError(f"{path} must contain a JSON object")
    return loaded


class PluginManifestTests(unittest.TestCase):
    def test_both_marketplaces_resolve_the_same_nested_plugin(self) -> None:
        generic_marketplace = load_json(
            REPOSITORY / ".agents" / "plugins" / "marketplace.json"
        )
        self.assertNotIn("version", generic_marketplace)
        self.assertEqual(len(generic_marketplace.get("plugins", [])), 1)
        generic_entry = generic_marketplace["plugins"][0]
        self.assertNotIn("version", generic_entry)
        self.assertEqual(generic_entry["name"], PLUGIN_NAME)
        self.assertEqual(
            generic_entry["source"],
            {"source": "local", "path": f"./plugins/{PLUGIN_NAME}"},
        )

        claude_marketplace = load_json(
            REPOSITORY / ".claude-plugin" / "marketplace.json"
        )
        self.assertNotIn("version", claude_marketplace)
        self.assertEqual(len(claude_marketplace.get("plugins", [])), 1)
        claude_entry = claude_marketplace["plugins"][0]
        self.assertNotIn("version", claude_entry)
        self.assertEqual(claude_entry["name"], PLUGIN_NAME)
        self.assertEqual(claude_entry["source"], f"./plugins/{PLUGIN_NAME}")

        self.assertTrue((PLUGIN_ROOT / ".claude-plugin" / "plugin.json").is_file())
        self.assertTrue((PLUGIN_ROOT / ".codex-plugin" / "plugin.json").is_file())
        self.assertFalse((REPOSITORY / ".claude-plugin" / "plugin.json").exists())
        self.assertFalse((REPOSITORY / ".codex-plugin" / "plugin.json").exists())

    def test_claude_manifest_is_the_only_component_owner(self) -> None:
        marketplace = load_json(REPOSITORY / ".claude-plugin" / "marketplace.json")
        entry = marketplace["plugins"][0]
        manifest = load_json(PLUGIN_ROOT / ".claude-plugin" / "plugin.json")

        self.assertIs(entry.get("strict"), True)
        self.assertEqual(COMPONENT_FIELDS & entry.keys(), set())
        self.assertEqual(manifest["skills"], "./skills")
        self.assertNotIn("version", marketplace)
        self.assertNotIn("version", entry)

    def test_concrete_manifest_versions_match_the_release_version(self) -> None:
        version = (REPOSITORY / "VERSION").read_text(encoding="utf-8").strip()
        self.assertRegex(version, r"^[0-9]+\.[0-9]+\.[0-9]+$")
        self.assertEqual(version, "0.1.6")
        recovery_notes = (REPOSITORY / "docs" / "releases" / "v0.1.5.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("2f29bb51957888b1f427be44a7a0866ed4f4f5e5", recovery_notes)
        self.assertIn("32839062910", recovery_notes)
        self.assertIn("No skill or accounting content changed", recovery_notes)
        release_heading = (
            REPOSITORY / "RELEASE_NOTES.md"
        ).read_text(encoding="utf-8").splitlines()[0]
        self.assertEqual(release_heading, f"# v{version}")

        for runtime in (".claude-plugin", ".codex-plugin"):
            with self.subTest(runtime=runtime):
                manifest = load_json(PLUGIN_ROOT / runtime / "plugin.json")
                self.assertEqual(manifest["name"], PLUGIN_NAME)
                self.assertEqual(manifest["version"], version)

    def test_deprecation_release_routes_new_installs_and_preserves_rollback(self) -> None:
        readme = (REPOSITORY / "README.md").read_text(encoding="utf-8")
        transition = (REPOSITORY / "docs" / "consolidation-transition.md").read_text(
            encoding="utf-8"
        )
        release_notes = (REPOSITORY / "RELEASE_NOTES.md").read_text(encoding="utf-8")

        for command in (
            "/plugin marketplace add ryanduguid/australian-accounting-skills",
            "/plugin install australian-accounting-skills@ryanduguid",
            "codex plugin marketplace add ryanduguid/australian-accounting-skills",
            "codex plugin add australian-accounting-skills@ryanduguid",
            "npx skills add ryanduguid/australian-accounting-skills",
        ):
            self.assertIn(command, readme)
        self.assertIn("Never enable both packs at once", readme)
        self.assertIn(
            "https://github.com/ryanduguid/hardhat-ledger/releases/tag/v0.1.5",
            readme,
        )
        self.assertIn(
            "https://github.com/ryanduguid/australian-accounting-skills/releases/tag/v0.2.0",
            readme,
        )
        self.assertIn("The replacement is publicly verified", transition)
        self.assertIn("No skill or accounting content changed", release_notes)

        manifests = (
            load_json(REPOSITORY / ".claude-plugin" / "marketplace.json")["plugins"][0],
            load_json(PLUGIN_ROOT / ".claude-plugin" / "plugin.json"),
            load_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json"),
        )
        for manifest in manifests:
            with self.subTest(manifest=manifest["name"]):
                self.assertIn("Deprecated", manifest["description"])
                self.assertIn("australian-accounting-skills", manifest["description"])
        generic_marketplace = load_json(
            REPOSITORY / ".agents" / "plugins" / "marketplace.json"
        )
        self.assertIn("Deprecated", generic_marketplace["interface"]["displayName"])

    def test_codex_manifest_uses_supported_portable_fields(self) -> None:
        manifest = load_json(PLUGIN_ROOT / ".codex-plugin" / "plugin.json")
        self.assertEqual(manifest["skills"], "./skills")
        self.assertNotIn("safety", manifest)
        self.assertNotIn("privacyPolicyURL", manifest["interface"])

    def test_canonical_skill_root_contains_the_exact_inventory(self) -> None:
        skill_root = PLUGIN_ROOT / "skills"
        discovered = {
            path.parent.name for path in skill_root.glob("*/SKILL.md")
        }
        self.assertEqual(discovered, EXPECTED_SKILLS)
        self.assertEqual(
            [
                path.relative_to(skill_root).as_posix()
                for path in skill_root.rglob("SKILL.md")
                if path.parent.parent != skill_root
            ],
            [],
        )


if __name__ == "__main__":
    unittest.main()
