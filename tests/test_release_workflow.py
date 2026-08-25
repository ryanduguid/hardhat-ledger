"""The release workflow is the shared archive policy plus the frozen-tag gate."""

from pathlib import Path
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_POLICY_SHA = "f180faa567e95669224211d0282b3b437fe79ea9"
POLICY_CALL = re.compile(
    r"ryanduguid/release-policy/\.github/workflows/"
    r"(?P<workflow>verify-skills|release-skills)\.yml@(?P<sha>[0-9a-f]{40})"
)


class ReleaseWorkflowTests(unittest.TestCase):
    def test_workflows_use_the_exact_shared_skill_policy(self) -> None:
        self.assertRegex(EXPECTED_POLICY_SHA, r"^[0-9a-f]{40}$")
        release_workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8",
        )
        verify_workflow = (ROOT / ".github" / "workflows" / "verify.yml").read_text(
            encoding="utf-8",
        )
        release = yaml.load(release_workflow, Loader=yaml.BaseLoader)["jobs"]["release"]
        verify = yaml.load(verify_workflow, Loader=yaml.BaseLoader)
        policy_calls = POLICY_CALL.findall(release_workflow + "\n" + verify_workflow)

        self.assertIn('tags:\n      - "v*"', release_workflow)
        self.assertNotIn("if", release)
        self.assertNotIn("release-archive.yml", release_workflow)
        self.assertEqual(
            release["uses"],
            "ryanduguid/release-policy/.github/workflows/release-skills.yml@"
            + EXPECTED_POLICY_SHA,
        )
        self.assertEqual(
            verify["jobs"]["shared-conformance"]["uses"],
            "ryanduguid/release-policy/.github/workflows/verify-skills.yml@"
            + EXPECTED_POLICY_SHA,
        )
        self.assertEqual(
            policy_calls,
            [
                ("release-skills", EXPECTED_POLICY_SHA),
                ("verify-skills", EXPECTED_POLICY_SHA),
            ],
        )
        self.assertEqual(
            release["with"],
            {
                "artifact-stem": "subcontractor-accounting-skills",
                "skills-verification-mode": "subcontractor-accounting-v1",
            },
        )
        self.assertEqual(set(verify["jobs"]), {"verify", "shared-conformance"})
        self.assertIn("pull_request", verify_workflow)
        self.assertIn("branches:\n      - main", verify_workflow)

    def test_privileged_release_job_delegates_without_local_steps(self) -> None:
        release_workflow = yaml.load(
            (ROOT / ".github" / "workflows" / "release.yml").read_text(
                encoding="utf-8"
            ),
            Loader=yaml.BaseLoader,
        )
        verify_workflow = yaml.load(
            (ROOT / ".github" / "workflows" / "verify.yml").read_text(
                encoding="utf-8"
            ),
            Loader=yaml.BaseLoader,
        )
        release = release_workflow["jobs"]["release"]
        self.assertIn("shared-conformance", verify_workflow["jobs"])
        shared_conformance = verify_workflow["jobs"]["shared-conformance"]
        local_verify = verify_workflow["jobs"]["verify"]

        for forbidden in ("steps", "runs-on", "env", "outputs", "secrets"):
            with self.subTest(job="release", forbidden=forbidden):
                self.assertNotIn(forbidden, release)
            with self.subTest(job="shared-conformance", forbidden=forbidden):
                self.assertNotIn(forbidden, shared_conformance)
        self.assertEqual(
            release["uses"],
            "ryanduguid/release-policy/.github/workflows/release-skills.yml@"
            + EXPECTED_POLICY_SHA,
        )
        self.assertEqual(
            release["permissions"],
            {
                "attestations": "write",
                "contents": "write",
                "id-token": "write",
            },
        )
        self.assertEqual(shared_conformance["permissions"], {"contents": "read"})
        self.assertEqual(
            shared_conformance["with"],
            {"skills-verification-mode": "subcontractor-accounting-v1"},
        )
        local_steps = "\n".join(step.get("run", "") for step in local_verify["steps"])
        self.assertIn("actions/checkout", str(local_verify["steps"]))
        self.assertIn(
            {"python-version": "3.12"},
            [step.get("with", {}) for step in local_verify["steps"]],
        )
        self.assertIn("requirements-test.txt", local_steps)
        self.assertIn("unittest discover -s tests -v", local_steps)
        self.assertIn("scripts/validate_validation.py", local_steps)
        self.assertIn("tests/verify_skills_cli.py", local_steps)


if __name__ == "__main__":
    unittest.main()
