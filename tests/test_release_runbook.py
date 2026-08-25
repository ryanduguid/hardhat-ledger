from pathlib import Path
import copy
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "RELEASING.md"
POWERSHELL = shutil.which("pwsh")
FENCE = re.compile(r"```powershell\n(?P<code>.*?)\n```", re.DOTALL)

INITIAL_FENCE = r"""$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$repo = "ryanduguid/hardhat-ledger"
$releaseTag = "v0.1.6" # Replace with the reviewed new version.
$expectedPolicySha = "f180faa567e95669224211d0282b3b437fe79ea9"
$protectedTags = @("v0.1.0", "v0.1.4", "v0.1.5")
if ($releaseTag -notmatch '^v[0-9]+\.[0-9]+\.[0-9]+$' -or $protectedTags -ccontains $releaseTag) {
    throw "releaseTag must be a new semantic version"
}
git fetch origin main --tags"""

CANDIDATE_404_PROBE = """$nativeErrorPreference = $PSNativeCommandUseErrorActionPreference
try {
    $PSNativeCommandUseErrorActionPreference = $false
    $candidateReleaseError = gh api "repos/$repo/releases/tags/$releaseTag" 2>&1
    $candidateReleaseExit = $LASTEXITCODE
} finally {
    $PSNativeCommandUseErrorActionPreference = $nativeErrorPreference
}
if ($candidateReleaseExit -eq 0 -or "$candidateReleaseError" -notmatch 'HTTP 404') {
    throw "candidate release absence was not proved"
}"""

PROTECTED_404_PROBE = """$nativeErrorPreference = $PSNativeCommandUseErrorActionPreference
try {
    $PSNativeCommandUseErrorActionPreference = $false
    $protectedReleaseError = gh api "repos/$repo/releases/tags/v0.1.4" 2>&1
    $protectedReleaseExit = $LASTEXITCODE
} finally {
    $PSNativeCommandUseErrorActionPreference = $nativeErrorPreference
}
if ($protectedReleaseExit -eq 0 -or "$protectedReleaseError" -notmatch 'HTTP 404') {
    throw "protected v0.1.4 release absence was not proved"
}"""


def assert_runbook_contract(testcase: unittest.TestCase, text: str) -> None:
    testcase.assertIn("## Published v0.1.5 baseline", text)
    testcase.assertIn("## Future release procedure", text)
    testcase.assertNotIn("recovery version is `v0.1.5`", text)
    testcase.assertNotIn("isLatest", text)
    testcase.assertIn(
        "body,databaseId,isDraft,isImmutable,isPrerelease,tagName,assets", text
    )
    testcase.assertIn("repos/$repo/releases/latest", text)
    testcase.assertIn("[guid]::NewGuid()", text)
    testcase.assertIn("[IO.FileAttributes]::ReparsePoint", text)
    testcase.assertIn("repos/$repo/git/ref/tags/$releaseTag", text)
    testcase.assertIn("repos/$repo/git/tags/$tagObjectSha", text)
    testcase.assertIn("$tagCommitSha -cne $approvedSha", text)
    testcase.assertIn("$remoteMainSha -cne $approvedSha", text)

    fences = [match["code"] for match in FENCE.finditer(text)]
    testcase.assertGreaterEqual(len(fences), 4)
    testcase.assertTrue(fences[0].startswith(INITIAL_FENCE))
    native_fail_closed = text.index("$PSNativeCommandUseErrorActionPreference = $true")
    first_native_command = min(text.index("git fetch"), text.index("gh api"))
    testcase.assertLess(native_fail_closed, first_native_command)

    testcase.assertIn(CANDIDATE_404_PROBE, text)
    testcase.assertIn(PROTECTED_404_PROBE, text)
    testcase.assertEqual(text.count("$candidateReleaseExit = $LASTEXITCODE"), 1)
    testcase.assertEqual(text.count("$protectedReleaseExit = $LASTEXITCODE"), 1)
    testcase.assertEqual(text.count("-notmatch 'HTTP 404'"), 2)
    testcase.assertGreaterEqual(
        text.count(
            "finally {\n    $PSNativeCommandUseErrorActionPreference = "
            "$nativeErrorPreference\n}"
        ),
        2,
    )

    testcase.assertIn('$protectedTags = @("v0.1.0", "v0.1.4", "v0.1.5")', text)
    testcase.assertIn("$protectedTags -ccontains $releaseTag", text)
    testcase.assertIn(
        "[int64]$release.databaseId -ne [int64]$latest.id", text
    )
    testcase.assertIn("$release.tagName -cne $latest.tag_name", text)
    testcase.assertIn("repos/$repo/immutable-releases", text)
    testcase.assertIn("-not $immutableReleaseState.enabled", text)
    testcase.assertIn("$release.body -cne $expectedNotes", text)

    testcase.assertIn("finally {\n    if (Test-Path -LiteralPath $downloadPath)", text)
    testcase.assertGreaterEqual(text.count("[IO.FileAttributes]::ReparsePoint"), 4)
    cleanup = text.index("Remove-Item -LiteralPath $resolvedDownloadPath -Force")
    final_block = text.rfind("finally {", 0, cleanup)
    testcase.assertNotEqual(final_block, -1)
    testcase.assertIn("[IO.Path]::GetRelativePath", text[final_block:cleanup])
    testcase.assertIn("[IO.FileAttributes]::ReparsePoint", text[final_block:cleanup])

    testcase.assertIn('$checksumAsset = "SHA256SUMS"', text)
    testcase.assertIn(
        '$spdxAsset = "subcontractor-accounting-skills-$releaseVersion.spdx.json"',
        text,
    )
    testcase.assertIn(
        '$tarAsset = "subcontractor-accounting-skills-$releaseVersion.tar.gz"',
        text,
    )
    testcase.assertIn(
        '$zipAsset = "subcontractor-accounting-skills-$releaseVersion.zip"', text
    )
    testcase.assertIn("$serverDigestChecks -ne 4", text)
    testcase.assertIn("$payloadChecksumChecks -ne 3", text)

    attestation_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("gh attestation verify ")
    ]
    provenance_lines = [
        line for line in attestation_lines if "--predicate-type" not in line
    ]
    spdx_lines = [line for line in attestation_lines if "--predicate-type" in line]
    testcase.assertEqual(len(provenance_lines), 4)
    testcase.assertEqual(len(spdx_lines), 2)
    testcase.assertTrue(
        all("--signer-workflow $signerWorkflow" in line for line in attestation_lines)
    )
    testcase.assertTrue(
        all(
            '--predicate-type "https://spdx.dev/Document/v2.3"' in line
            for line in spdx_lines
        )
    )
    testcase.assertEqual(
        len(
            re.findall(
                r"^\s*gh release verify \$releaseTag --repo \$repo$", text, re.MULTILINE
            )
        ),
        1,
    )
    testcase.assertEqual(
        len(
            re.findall(
                r"^\s*gh release verify-asset \$releaseTag ", text, re.MULTILINE
            )
        ),
        4,
    )


class ReleaseRunbookTests(unittest.TestCase):
    def test_runbook_has_fail_closed_release_contract(self) -> None:
        assert_runbook_contract(self, RUNBOOK.read_text(encoding="utf-8"))

    def test_runbook_contract_rejects_safety_mutations(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        assert_runbook_contract(self, text)
        mutations = {
            "native failures no longer terminate": (
                "$PSNativeCommandUseErrorActionPreference = $true",
                "$PSNativeCommandUseErrorActionPreference = $false",
            ),
            "candidate probe accepts a non-404": ("'HTTP 404'", "'HTTP 403'"),
            "protected version can be selected": (
                '$protectedTags = @("v0.1.0", "v0.1.4", "v0.1.5")',
                '$protectedTags = @("v0.1.0", "v0.1.4")',
            ),
            "latest comparison omits release identity": (
                "[int64]$release.databaseId -ne [int64]$latest.id",
                "[int64]$release.databaseId -lt 1",
            ),
            "latest comparison omits tag identity": (
                "$release.tagName -cne $latest.tag_name",
                "$release.tagName -cne $releaseTag",
            ),
            "immutable release enablement is not required": (
                "-not $immutableReleaseState.enabled",
                "$false",
            ),
            "release notes comparison is weakened": (
                "$release.body -cne $expectedNotes",
                "$release.body.TrimEnd() -cne $expectedNotes.TrimEnd()",
            ),
            "temporary child is predictable": (
                "[guid]::NewGuid()",
                '"fixed-download"',
            ),
            "cleanup permits a reparse point": (
                "[IO.FileAttributes]::ReparsePoint",
                "[IO.FileAttributes]::Directory",
            ),
            "server digest count is weakened": (
                "$serverDigestChecks -ne 4",
                "$serverDigestChecks -lt 1",
            ),
            "payload checksum count is weakened": (
                "$payloadChecksumChecks -ne 3",
                "$payloadChecksumChecks -lt 1",
            ),
            "one provenance verification is removed": (
                "gh attestation verify $checksumPath ",
                "# removed provenance verification $checksumPath ",
            ),
            "one SPDX verification is removed": (
                '$signerWorkflow --signer-digest $expectedPolicySha '
                '--predicate-type "https://spdx.dev/Document/v2.3"',
                "# removed SPDX verification",
            ),
            "one release asset verification is removed": (
                "gh release verify-asset $releaseTag $checksumPath --repo $repo",
                "# removed release asset verification",
            ),
            "tag target comparison is weakened": (
                "$tagCommitSha -cne $approvedSha",
                "$tagCommitSha -cne $tagCommitSha",
            ),
            "main comparison is weakened": (
                "$remoteMainSha -cne $approvedSha",
                "$remoteMainSha -cne $remoteMainSha",
            ),
        }
        for name, (old, new) in mutations.items():
            with self.subTest(mutation=name):
                self.assertIn(old, text)
                mutated = copy.copy(text).replace(old, new, 1)
                with self.assertRaises(AssertionError):
                    assert_runbook_contract(self, mutated)

    @unittest.skipUnless(POWERSHELL, "PowerShell 7 is required to parse release commands")
    def test_every_powershell_fence_parses(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        fences = [match["code"] for match in FENCE.finditer(text)]
        self.assertGreaterEqual(len(fences), 4)
        parser = r"""
$source = [Console]::In.ReadToEnd()
$tokens = $null
$errors = $null
[System.Management.Automation.Language.Parser]::ParseInput(
    $source, [ref]$tokens, [ref]$errors
) | Out-Null
if ($errors.Count) {
    $errors | ForEach-Object { [Console]::Error.WriteLine($_.Message) }
    exit 1
}
"""
        for number, fence in enumerate(fences, start=1):
            with self.subTest(fence=number):
                result = subprocess.run(
                    [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", parser],
                    input=fence,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
