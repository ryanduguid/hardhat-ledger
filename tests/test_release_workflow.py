"""The release workflow is the shared archive policy plus the frozen-tag gate."""

from pathlib import Path
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]


class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_workflow_uses_the_shared_archive_policy(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
            encoding="utf-8",
        )
        self.assertIn("github.ref_name == 'v0.1.0'", workflow)
        self.assertIn("v0.1.0 is frozen", workflow)
        self.assertIn(
            "ryanduguid/release-policy/.github/workflows/release-archive.yml@"
            "47480b782926179b621ec1c6643ef88c80fc8fd4",
            workflow,
        )
        self.assertIn("artifact-stem: subcontractor-accounting-skills", workflow)

    def test_privileged_release_job_delegates_without_local_steps(self) -> None:
        workflow = yaml.load(
            (ROOT / ".github" / "workflows" / "release.yml").read_text(
                encoding="utf-8"
            ),
            Loader=yaml.BaseLoader,
        )
        release = workflow["jobs"]["release"]

        self.assertNotIn("steps", release)
        self.assertNotIn("env", release)
        self.assertEqual(
            release["uses"],
            "ryanduguid/release-policy/.github/workflows/release-archive.yml@"
            "47480b782926179b621ec1c6643ef88c80fc8fd4",
        )
        self.assertEqual(
            release["permissions"],
            {
                "attestations": "write",
                "contents": "write",
                "id-token": "write",
            },
        )


if __name__ == "__main__":
    unittest.main()
