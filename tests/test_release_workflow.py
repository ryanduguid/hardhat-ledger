"""Static safety gates for the operator-controlled release path."""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
WORKFLOWS = REPOSITORY / ".github" / "workflows"
RELEASE_WORKFLOW = WORKFLOWS / "release.yml"
RELEASE_PROCEDURE = REPOSITORY / "RELEASING.md"
RELEASE_NOTES = REPOSITORY / "docs" / "releases" / "v0.1.1.md"
ACTION_REFERENCE = re.compile(r"^\s*uses:\s*([^\s#]+)", re.MULTILINE)
FULL_SHA_REFERENCE = re.compile(r"^[^@]+@[0-9a-f]{40}$")


class ReleaseWorkflowTests(unittest.TestCase):
    def test_every_external_action_is_pinned_to_a_full_commit_sha(self) -> None:
        references: list[tuple[str, str]] = []
        workflows = sorted(
            {*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")}
        )
        for workflow in workflows:
            for reference in ACTION_REFERENCE.findall(
                workflow.read_text(encoding="utf-8")
            ):
                if not reference.startswith("./"):
                    references.append((workflow.name, reference))
        self.assertGreater(len(references), 0)
        for workflow, reference in references:
            with self.subTest(workflow=workflow, action=reference):
                self.assertRegex(reference, FULL_SHA_REFERENCE)

    def test_release_is_tag_only_and_requires_an_annotated_exact_main_tag(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        trigger = text.split("permissions:", maxsplit=1)[0]
        self.assertIn('tags:\n      - "v*.*.*"', trigger)
        self.assertNotIn("workflow_dispatch", trigger)
        self.assertNotIn("pull_request", trigger)
        self.assertIn('git cat-file -t "refs/tags/${tag}"', text)
        self.assertIn('!= "tag"', text)
        self.assertIn('git rev-parse "refs/tags/${tag}^{commit}"', text)
        self.assertIn("git/ref/heads/main", text)
        self.assertIn("exact current main commit", text)
        self.assertIn('"${tag}" == "v0.1.0"', text)
        self.assertIn("--verify-tag", text)
        self.assertNotIn("--clobber", text)
        self.assertNotIn("--force", text)

    def test_workflow_has_attestation_permissions_and_both_attestation_types(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        self.assertIn("contents: write", text)
        self.assertIn("id-token: write", text)
        self.assertIn("attestations: write", text)
        attest_references = [
            reference
            for reference in ACTION_REFERENCE.findall(text)
            if reference.startswith("actions/attest@")
        ]
        self.assertEqual(len(attest_references), 2)
        self.assertIn("sbom-path:", text)
        self.assertIn(".spdx.json", text)
        self.assertIn("SHA256SUMS", text)

    def test_workflow_does_not_attempt_repository_admin_mutation(self) -> None:
        workflow = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        procedure = RELEASE_PROCEDURE.read_text(encoding="utf-8")
        self.assertNotIn("immutable-releases", workflow)
        self.assertIn("--method PUT", procedure)
        self.assertGreaterEqual(procedure.count("immutable-releases"), 3)
        self.assertIn("--jq '{enabled, enforced_by_owner}'", procedure)
        self.assertIn("Stop unless `enabled` is `true`", procedure)
        self.assertIn("before creating the tag", procedure)
        self.assertIn("does **not** call", procedure)

    def test_draft_and_exact_assets_are_verified_before_publication(self) -> None:
        text = RELEASE_WORKFLOW.read_text(encoding="utf-8")
        draft_create = text.index('gh release create "${tag}"')
        draft_verify = text.index('The release was not created as a draft')
        asset_verify = text.index('The draft release does not contain the exact asset set')
        publish = text.index('gh release edit "${tag}" --draft=false')
        immutable_readback = text.index('Published release is not immutable')
        self.assertLess(draft_create, draft_verify)
        self.assertLess(draft_verify, asset_verify)
        self.assertLess(asset_verify, publish)
        self.assertLess(publish, immutable_readback)
        self.assertEqual(text.count('"dist/SHA256SUMS#SHA-256 checksums"'), 1)

    def test_release_notes_state_the_regulated_human_review_boundary(self) -> None:
        text = RELEASE_NOTES.read_text(encoding="utf-8")
        prose = " ".join(text.split())
        self.assertIn("review-schedule skills", prose)
        self.assertIn("fresh check of the current primary sources", prose)
        self.assertIn("qualified human review", prose)
        self.assertIn("registered", prose)
        self.assertIn("not an SG calculator or a TPAR", prose)
        self.assertIn("No skill gives final", prose)
        self.assertIn("does not move", prose)

    def test_release_inventory_is_exactly_ten_and_has_no_pinned_version(self) -> None:
        marketplace = json.loads(
            (REPOSITORY / ".claude-plugin" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertNotIn("version", marketplace)
        self.assertEqual(len(marketplace["plugins"]), 1)
        plugin = marketplace["plugins"][0]
        self.assertNotIn("version", plugin)
        self.assertEqual(len(plugin["skills"]), 10)
        self.assertEqual(len(plugin["skills"]), len(set(plugin["skills"])))
        discovered = sorted(
            f"./{path.parent.relative_to(REPOSITORY).as_posix()}"
            for path in (REPOSITORY / ".claude" / "skills").glob("*/SKILL.md")
        )
        self.assertEqual(sorted(plugin["skills"]), discovered)


if __name__ == "__main__":
    unittest.main()
