"""Test the thin caller activation adapter; exact-pinned shared skill-release policy owns frozen-tag refusal."""

from pathlib import Path
from copy import deepcopy
import re
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_POLICY_SHA = "d08de09646fc46b43d3e59394105005c123496bb"
POLICY_CALL = re.compile(
    r"ryanduguid/release-policy/\.github/workflows/"
    r"(?P<workflow>verify-skills|release-skills)\.yml@(?P<sha>[0-9a-f]{40})"
)


def assert_workflow_contract(testcase, release_workflow, verify_workflow):
    testcase.assertEqual(set(release_workflow["jobs"]), {"release"})
    testcase.assertEqual(
        set(verify_workflow["jobs"]),
        {"verify", "shared-conformance"},
    )

    release = release_workflow["jobs"]["release"]
    local_verify = verify_workflow["jobs"]["verify"]
    shared = verify_workflow["jobs"]["shared-conformance"]

    testcase.assertEqual(set(release), {"permissions", "uses", "with"})
    testcase.assertEqual(set(local_verify), {"name", "runs-on", "steps"})
    testcase.assertEqual(
        set(shared),
        {"name", "permissions", "uses", "with"},
    )

    testcase.assertEqual(
        local_verify["steps"],
        [
            {
                "name": "Check out source",
                "uses": "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
                "with": {"persist-credentials": "false"},
            },
            {
                "name": "Set up Python",
                "uses": "actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97",
                "with": {"python-version": "3.12"},
            },
            {
                "name": "Install test dependencies",
                "run": "python -m pip install --disable-pip-version-check --no-deps --requirement requirements-test.txt",
            },
            {
                "name": "Verify skill metadata",
                "run": "python -m unittest discover -s tests -v",
            },
            {
                "name": "Verify fabricated validation pack",
                "run": "python scripts/validate_validation.py",
            },
            {
                "name": "Verify Skills CLI discovery",
                "run": "python tests/verify_skills_cli.py",
            },
        ],
    )


class ReleaseWorkflowTests(unittest.TestCase):
    def _load_workflows(self):
        release_workflow = yaml.load(
            (ROOT / ".github" / "workflows" / "release.yml").read_text(
                encoding="utf-8",
            ),
            Loader=yaml.BaseLoader,
        )
        verify_workflow = yaml.load(
            (ROOT / ".github" / "workflows" / "verify.yml").read_text(
                encoding="utf-8",
            ),
            Loader=yaml.BaseLoader,
        )
        return release_workflow, verify_workflow

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
        assert_workflow_contract(
            self,
            yaml.load(release_workflow, Loader=yaml.BaseLoader),
            verify,
        )
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
        assert_workflow_contract(self, release_workflow, verify_workflow)

    def test_workflow_contract_rejects_activation_mutations(self) -> None:
        release_workflow, verify_workflow = self._load_workflows()
        assert_workflow_contract(self, release_workflow, verify_workflow)
        mutations = {
            "extra release job": lambda release, verify: release["jobs"].update(
                {"renamed-frozen": {"runs-on": "ubuntu-latest", "steps": []}}
            ),
            "conditional release": lambda release, verify: release["jobs"]["release"].update(
                {"if": "github.ref_name != 'v0.1.0'"}
            ),
            "masked release failure": lambda release, verify: release["jobs"]["release"].update(
                {"continue-on-error": "true"}
            ),
            "conditional local verify": lambda release, verify: verify["jobs"]["verify"].update(
                {"if": "success()"}
            ),
            "masked local verify failure": lambda release, verify: verify["jobs"]["verify"].update(
                {"continue-on-error": "true"}
            ),
            "conditional shared verification": lambda release, verify: verify["jobs"]["shared-conformance"].update(
                {"if": "success()"}
            ),
            "masked shared failure": lambda release, verify: verify["jobs"]["shared-conformance"].update(
                {"continue-on-error": "true"}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(mutation=name):
                mutated_release = deepcopy(release_workflow)
                mutated_verify = deepcopy(verify_workflow)
                mutate(mutated_release, mutated_verify)
                with self.assertRaises(AssertionError):
                    assert_workflow_contract(self, mutated_release, mutated_verify)


if __name__ == "__main__":
    unittest.main()
