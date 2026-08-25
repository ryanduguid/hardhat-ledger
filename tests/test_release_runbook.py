from pathlib import Path
import copy
import json
import re
import shutil
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "RELEASING.md"
EVIDENCE = ROOT / "docs" / "releases" / "v0.1.5.md"
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

POST_APPROVAL_404_PROBE = """$nativeErrorPreference = $PSNativeCommandUseErrorActionPreference
try {
    $PSNativeCommandUseErrorActionPreference = $false
    $postApprovalReleaseError = gh api "repos/$repo/releases/tags/$releaseTag" 2>&1
    $postApprovalReleaseExit = $LASTEXITCODE
} finally {
    $PSNativeCommandUseErrorActionPreference = $nativeErrorPreference
}
if ($postApprovalReleaseExit -eq 0 -or "$postApprovalReleaseError" -notmatch 'HTTP 404') {
    throw "post-approval release absence was not proved"
}"""

POST_APPROVAL_TAG_ABSENCE_IF = """if ($postApprovalTag) {
    throw "candidate tag appeared after approval"
}"""

POST_APPROVAL_TAG_QUERY = (
    '$postApprovalTag = git ls-remote --tags origin "refs/tags/$releaseTag"'
)

POWERSHELL_AST_EVIDENCE = r'''$ErrorActionPreference = "Stop"
$sources = @([Console]::In.ReadToEnd() | ConvertFrom-Json)
$assignments = [Collections.Generic.List[object]]::new()
$commands = [Collections.Generic.List[object]]::new()
$conditions = [Collections.Generic.List[object]]::new()

for ($fence = 0; $fence -lt $sources.Count; $fence++) {
    $tokens = $null
    $errors = $null
    $ast = [Management.Automation.Language.Parser]::ParseInput(
        $sources[$fence], [ref]$tokens, [ref]$errors
    )
    if ($errors.Count) {
        throw "PowerShell fence $($fence + 1) did not parse"
    }

    $assignmentNodes = $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.AssignmentStatementAst]
    }, $true)
    foreach ($node in $assignmentNodes) {
        $name = $null
        if ($node.Left -is [Management.Automation.Language.VariableExpressionAst]) {
            $name = $node.Left.VariablePath.UserPath
        }
        $assignments.Add([pscustomobject]@{
            fence = $fence
            name = $name
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            topLevel = (
                $node.Parent -is [Management.Automation.Language.NamedBlockAst] -and
                $node.Parent.Parent -is
                [Management.Automation.Language.ScriptBlockAst]
            )
        })
    }

    $commandNodes = $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.CommandAst]
    }, $true)
    foreach ($node in $commandNodes) {
        $commandName = $node.GetCommandName()
        $commands.Add([pscustomobject]@{
            fence = $fence
            name = $commandName
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            topLevel = (
                $node.Parent -is [Management.Automation.Language.PipelineAst] -and
                $node.Parent.Parent -is
                [Management.Automation.Language.NamedBlockAst] -and
                $node.Parent.Parent.Parent -is
                [Management.Automation.Language.ScriptBlockAst]
            )
        })
    }

    $ifNodes = $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.IfStatementAst]
    }, $true)
    foreach ($node in $ifNodes) {
        foreach ($clause in $node.Clauses) {
            $conditions.Add([pscustomobject]@{
                fence = $fence
                condition = $clause.Item1.Extent.Text
                text = $node.Extent.Text
                start = $node.Extent.StartOffset
                end = $node.Extent.EndOffset
            })
        }
    }
}

[pscustomobject]@{
    assignments = [object[]]$assignments
    commands = [object[]]$commands
    conditions = [object[]]$conditions
} | ConvertTo-Json -Depth 5 -Compress
'''

NOTE_NORMALISER = """function ConvertTo-Lf([string]$Text) {
    return $Text.Replace("`r`n", "`n")
}"""

CHECK_RUN_GATE = """if (
        $matchingChecks.Count -ne 1 -or
        $matchingChecks[0].status -cne "completed" -or
        $matchingChecks[0].conclusion -cne "success"
    ) {"""

APPROVED_SIGNER_OPTION = (
    '--signer-workflow '
    '"ryanduguid/release-policy/.github/workflows/publish-archives.yml"'
)
VARIABLE_SIGNER_OPTION = "--signer-workflow $signerWorkflow"

PROVENANCE_COMMANDS = (
    'gh attestation verify $checksumPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha',
    'gh attestation verify $spdxPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha',
    'gh attestation verify $tarPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha',
    'gh attestation verify $zipPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha',
)

SPDX_COMMANDS = (
    'gh attestation verify $tarPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha --predicate-type "https://spdx.dev/Document/v2.3"',
    'gh attestation verify $zipPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha --predicate-type "https://spdx.dev/Document/v2.3"',
)

RELEASE_VERIFICATION_COMMANDS = (
    "gh release verify $releaseTag --repo $repo",
    "gh release verify-asset $releaseTag $checksumPath --repo $repo",
    "gh release verify-asset $releaseTag $spdxPath --repo $repo",
    "gh release verify-asset $releaseTag $tarPath --repo $repo",
    "gh release verify-asset $releaseTag $zipPath --repo $repo",
)

PROTECTED_TAG_LIVE_PROOF = """$protectedTagRef = gh api "repos/$repo/git/ref/tags/v0.1.4" | ConvertFrom-Json
if ($protectedTagRef.object.type -cne "tag") { throw "protected v0.1.4 tag is not annotated" }
$protectedTagObjectSha = $protectedTagRef.object.sha
$protectedTagObject = gh api "repos/$repo/git/tags/$protectedTagObjectSha" | ConvertFrom-Json
if ($protectedTagObject.object.type -cne "commit") { throw "protected v0.1.4 tag does not target a commit" }
$protectedV014Commit = $protectedTagObject.object.sha
if ($protectedV014Commit -cne "2f29bb51957888b1f427be44a7a0866ed4f4f5e5") {
    throw "protected v0.1.4 commit changed"
}"""

EVIDENCE_MARKERS = (
    "Hardhat commit: 0cd5478c0aa412813cd1b0a182f365250d823c93",
    "Annotated tag object: b690d7e0a155e0574840b47e977a70855a775a89",
    "Policy commit: f180faa567e95669224211d0282b3b437fe79ea9",
    "Release run: 32865033315",
    "SHA256SUMS                                      a6c26561592fa3df5c2675bd3801ca3c7af2034ce4a47bd804af703f983e944c",
    "subcontractor-accounting-skills-0.1.5.spdx.json 2abebc84ed705aecd81517f1c14226a76deb3cb4528f5c60f5fc3937e9d903cf",
    "subcontractor-accounting-skills-0.1.5.tar.gz     5aaf15b93cb06fc67e39b1fcc270dca0a6d20e5cc85cadd597a46fc810962d13",
    "subcontractor-accounting-skills-0.1.5.zip        231784a4decc64760318ba1033f6da03a8938dbda6142d4351f60f510b8e6419",
)


def powershell_ast_evidence(
    testcase: unittest.TestCase, fences: list[str]
) -> dict[str, list[dict[str, object]]]:
    testcase.assertIsNotNone(
        POWERSHELL, "PowerShell 7 is required to verify executable release statements"
    )
    result = subprocess.run(
        [
            POWERSHELL,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            POWERSHELL_AST_EVIDENCE,
        ],
        input=json.dumps(fences),
        text=True,
        capture_output=True,
        check=False,
    )
    testcase.assertEqual(result.returncode, 0, result.stderr)
    return json.loads(result.stdout)


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
    ast = powershell_ast_evidence(testcase, fences)
    native_fail_closed = text.index("$PSNativeCommandUseErrorActionPreference = $true")
    first_native_command = min(text.index("git fetch"), text.index("gh api"))
    testcase.assertLess(native_fail_closed, first_native_command)

    testcase.assertIn(CANDIDATE_404_PROBE, text)
    testcase.assertIn(POST_APPROVAL_404_PROBE, text)
    testcase.assertIn(PROTECTED_404_PROBE, text)
    testcase.assertEqual(text.count("$candidateReleaseExit = $LASTEXITCODE"), 1)
    testcase.assertEqual(text.count("$postApprovalReleaseExit = $LASTEXITCODE"), 1)
    testcase.assertEqual(text.count("$protectedReleaseExit = $LASTEXITCODE"), 1)
    testcase.assertEqual(text.count("-notmatch 'HTTP 404'"), 3)
    testcase.assertGreaterEqual(
        text.count(
            "finally {\n    $PSNativeCommandUseErrorActionPreference = "
            "$nativeErrorPreference\n}"
        ),
        3,
    )

    testcase.assertIn('$protectedTags = @("v0.1.0", "v0.1.4", "v0.1.5")', text)
    testcase.assertIn("$protectedTags -ccontains $releaseTag", text)
    testcase.assertIn(
        "[int64]$release.databaseId -ne [int64]$latest.id", text
    )
    testcase.assertIn("$release.tagName -cne $latest.tag_name", text)
    testcase.assertEqual(text.count("repos/$repo/immutable-releases"), 2)
    testcase.assertIn("-not $immutableReleaseState.enabled", text)
    testcase.assertIn("-not $postApprovalImmutableReleaseState.enabled", text)
    testcase.assertIn(NOTE_NORMALISER, text)
    testcase.assertIn("$releaseBodyLf -cne $expectedNotesLf", text)

    testcase.assertIn(CHECK_RUN_GATE, text)
    testcase.assertEqual(text.count("if (git status --porcelain)"), 1)
    testcase.assertIn("$postApprovalStatus = git status --porcelain", text)
    testcase.assertIn("if ($postApprovalStatus)", text)
    testcase.assertIn("$confirmedApprovedSha -cne $approvedSha", text)
    testcase.assertIn(
        "$postApprovalOriginMainSha -cne $approvedSha -or\n"
        "    $postApprovalApiMainSha -cne $approvedSha",
        text,
    )
    testcase.assertIn("$postApprovalHeadSha -cne $approvedSha", text)
    approval = text.index("$confirmedApprovedSha -cne $approvedSha")
    post_approval_gate = text.index("$postApprovalImmutableReleaseState")
    tag_create = text.index("git tag -a $releaseTag")
    tag_push = text.index('git push origin "refs/tags/$releaseTag"')
    testcase.assertLess(approval, post_approval_gate)

    approval_conditions = [
        condition
        for condition in ast["conditions"]
        if condition["condition"] == "$confirmedApprovedSha -cne $approvedSha"
    ]
    testcase.assertEqual(len(approval_conditions), 1)
    approval_condition = approval_conditions[0]
    approval_fence = approval_condition["fence"]

    fetch_commands = [
        command
        for command in ast["commands"]
        if command["name"] is not None
        and command["name"].casefold() == "git"
        and command["text"] == "git fetch origin main --tags"
        and command["topLevel"]
    ]
    testcase.assertEqual(len(fetch_commands), 2)
    post_approval_fetches = [
        command for command in fetch_commands if command["fence"] == approval_fence
    ]
    testcase.assertEqual(len(post_approval_fetches), 1)
    post_approval_fetch = post_approval_fetches[0]

    immutable_assignments = [
        assignment
        for assignment in ast["assignments"]
        if assignment["fence"] == approval_fence
        and assignment["name"] is not None
        and assignment["name"].casefold()
        == "postapprovalimmutablereleasestate"
    ]
    testcase.assertEqual(len(immutable_assignments), 1)

    tag_queries = [
        assignment
        for assignment in ast["assignments"]
        if assignment["fence"] == approval_fence
        and assignment["text"] == POST_APPROVAL_TAG_QUERY
        and assignment["topLevel"]
    ]
    testcase.assertEqual(len(tag_queries), 1)
    tag_query = tag_queries[0]

    tag_rejections = [
        condition
        for condition in ast["conditions"]
        if condition["fence"] == approval_fence
        and condition["condition"] == "$postApprovalTag"
        and condition["text"] == POST_APPROVAL_TAG_ABSENCE_IF
    ]
    testcase.assertEqual(len(tag_rejections), 1)
    tag_rejection = tag_rejections[0]

    tag_create_commands = [
        command
        for command in ast["commands"]
        if command["fence"] == approval_fence
        and command["name"] is not None
        and command["name"].casefold() == "git"
        and command["text"]
        == "git tag -a $releaseTag $approvedSha -m $releaseTag"
        and command["topLevel"]
    ]
    testcase.assertEqual(len(tag_create_commands), 1)
    tag_create_command = tag_create_commands[0]

    testcase.assertLess(approval_condition["end"], post_approval_fetch["start"])
    testcase.assertLess(
        post_approval_fetch["end"], immutable_assignments[0]["start"]
    )
    testcase.assertLess(approval_condition["end"], tag_query["start"])
    testcase.assertLess(tag_query["end"], tag_rejection["start"])
    testcase.assertLess(tag_rejection["end"], tag_create_command["start"])
    post_approval_markers = (
        "$postApprovalImmutableReleaseState",
        "$postApprovalOriginMainSha = git rev-parse origin/main",
        '$postApprovalApiMainSha = gh api "repos/$repo/git/ref/heads/main"',
        "$postApprovalHeadSha = git rev-parse HEAD",
        "$postApprovalStatus = git status --porcelain",
        '$postApprovalTag = git ls-remote --tags origin "refs/tags/$releaseTag"',
        POST_APPROVAL_404_PROBE,
    )
    for marker in post_approval_markers:
        testcase.assertIn(marker, text)
        marker_position = text.index(marker)
        testcase.assertLess(approval, marker_position)
        testcase.assertLess(marker_position, tag_create)
    testcase.assertLess(tag_create, tag_push)
    testcase.assertIn(
        '(git cat-file -t "refs/tags/$releaseTag") -cne "tag"', text
    )
    testcase.assertIn("$localTagCommitSha -cne $approvedSha", text)

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
    testcase.assertIn(
        'if (-not ($checksumLines -ccontains "$payloadDigest  $payloadName"))',
        text,
    )
    attestation_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("gh attestation verify ")
    ]
    provenance_lines = [
        line for line in attestation_lines if "--predicate-type" not in line
    ]
    spdx_lines = [line for line in attestation_lines if "--predicate-type" in line]
    testcase.assertCountEqual(provenance_lines, PROVENANCE_COMMANDS)
    testcase.assertCountEqual(spdx_lines, SPDX_COMMANDS)

    release_verification_lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip().startswith("gh release verify")
    ]
    testcase.assertCountEqual(
        release_verification_lines,
        RELEASE_VERIFICATION_COMMANDS,
    )

    testcase.assertIn(PROTECTED_TAG_LIVE_PROOF, text)
    testcase.assertNotIn("$protectedV014Commit = git rev-parse", text)


def assert_evidence_contract(testcase: unittest.TestCase, text: str) -> None:
    for marker in EVIDENCE_MARKERS:
        testcase.assertEqual(text.count(marker), 1)
    testcase.assertIn("All four provenance attestations", text)
    testcase.assertIn("both SPDX v2.3 archive attestations", text)
    testcase.assertIn("`gh release verify` passed", text)
    testcase.assertIn("`gh release verify-asset` for each", text)
    testcase.assertIn("32839062910", text)
    testcase.assertIn("No skill or accounting content changed", text)


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
            "post-approval immutable state is not required": (
                "-not $postApprovalImmutableReleaseState.enabled",
                "$false",
            ),
            "post-approval main check accepts drift": (
                "$postApprovalApiMainSha -cne $approvedSha",
                "$postApprovalApiMainSha -cne $postApprovalApiMainSha",
            ),
            "post-approval origin main is not queried": (
                "$postApprovalOriginMainSha = git rev-parse origin/main",
                "$postApprovalOriginMainSha = $approvedSha",
            ),
            "post-approval local head is not queried": (
                "$postApprovalHeadSha = git rev-parse HEAD",
                "$postApprovalHeadSha = $approvedSha",
            ),
            "post-approval clean checkout is not required": (
                "$postApprovalStatus = git status --porcelain",
                "$postApprovalStatus = $null",
            ),
            "post-approval release probe accepts a non-404": (
                '"$postApprovalReleaseError" -notmatch \'HTTP 404\'',
                '"$postApprovalReleaseError" -notmatch \'HTTP 403\'',
            ),
            "post-approval candidate tag absence is not queried": (
                '$postApprovalTag = git ls-remote --tags origin "refs/tags/$releaseTag"',
                "$postApprovalTag = $null",
            ),
            "approval can differ from the selected commit": (
                "$confirmedApprovedSha -cne $approvedSha",
                "$confirmedApprovedSha -cne $confirmedApprovedSha",
            ),
            "local tag target need not match approval": (
                "$localTagCommitSha -cne $approvedSha",
                "$localTagCommitSha -cne $localTagCommitSha",
            ),
            "failed checks are accepted": (
                '$matchingChecks[0].conclusion -cne "success"',
                '$matchingChecks[0].conclusion -ceq "success"',
            ),
            "release note normalisation is removed": (
                'return $Text.Replace("`r`n", "`n")',
                "return $Text",
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
            "checksum membership is inverted": (
                'if (-not ($checksumLines -ccontains "$payloadDigest  $payloadName"))',
                'if ($checksumLines -ccontains "$payloadDigest  $payloadName")',
            ),
            "signer workflow is changed": (
                APPROVED_SIGNER_OPTION,
                '--signer-workflow '
                '"ryanduguid/hardhat-ledger/.github/workflows/release.yml"',
            ),
            "attestation source digest is changed": (
                "--source-digest $approvedSha",
                "--source-digest $expectedPolicySha",
            ),
            "attestation source ref is changed": (
                '--source-ref "refs/tags/$releaseTag"',
                '--source-ref "refs/heads/main"',
            ),
            "attestation signer digest is changed": (
                "--signer-digest $expectedPolicySha",
                "--signer-digest $approvedSha",
            ),
            "one provenance verification is removed": (
                "gh attestation verify $checksumPath ",
                "# removed provenance verification $checksumPath ",
            ),
            "zip provenance is replaced by duplicate tar provenance": (
                PROVENANCE_COMMANDS[3],
                PROVENANCE_COMMANDS[2],
            ),
            "one SPDX verification is removed": (
                SPDX_COMMANDS[0],
                "# removed SPDX verification",
            ),
            "one release asset verification is removed": (
                "gh release verify-asset $releaseTag $checksumPath --repo $repo",
                "# removed release asset verification",
            ),
            "zip asset verification is replaced by duplicate tar verification": (
                RELEASE_VERIFICATION_COMMANDS[4],
                RELEASE_VERIFICATION_COMMANDS[3],
            ),
            "protected tag proof uses a local ref": (
                '$protectedTagRef = gh api "repos/$repo/git/ref/tags/v0.1.4" '
                "| ConvertFrom-Json",
                "$protectedV014Commit = git rev-parse "
                "'refs/tags/v0.1.4^{commit}'",
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

        moved_probe = text.replace(POST_APPROVAL_404_PROBE, "", 1).replace(
            'git push origin "refs/tags/$releaseTag"',
            'git push origin "refs/tags/$releaseTag"\n' + POST_APPROVAL_404_PROBE,
            1,
        )
        with self.assertRaises(AssertionError):
            assert_runbook_contract(self, moved_probe)

    def test_runbook_contract_rejects_effective_assignment_mutations(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        assert_runbook_contract(self, text)

        first_attestation = PROVENANCE_COMMANDS[0]
        variable_attestation = first_attestation.replace(
            APPROVED_SIGNER_OPTION, VARIABLE_SIGNER_OPTION
        )
        first_attestation = "    " + first_attestation
        self.assertIn(first_attestation, text)
        unsafe_signer_reassignment = text.replace(
            first_attestation,
            '    $signerWorkflow = "unsafe/example.yml"\n    '
            + variable_attestation,
            1,
        )

        approval = text.index("$confirmedApprovedSha -cne $approvedSha")
        pre_approval = text[:approval]
        post_approval = text[approval:]
        self.assertIn("git fetch origin main --tags\n", post_approval)
        missing_post_approval_fetch = pre_approval + post_approval.replace(
            "git fetch origin main --tags\n", "", 1
        )

        self.assertIn("if ($postApprovalTag) {", text)
        inverted_candidate_tag_predicate = text.replace(
            "if ($postApprovalTag) {", "if (-not $postApprovalTag) {", 1
        )

        mutations = {
            "effective signer is reassigned": unsafe_signer_reassignment,
            "post-approval fetch is removed": missing_post_approval_fetch,
            "candidate tag absence predicate is inverted": (
                inverted_candidate_tag_predicate
            ),
        }
        for name, mutated in mutations.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_runbook_contract(self, mutated)

    def test_runbook_contract_rejects_parser_bypasses(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        assert_runbook_contract(self, text)

        first_attestation = PROVENANCE_COMMANDS[0]
        variable_attestation = first_attestation.replace(
            APPROVED_SIGNER_OPTION, VARIABLE_SIGNER_OPTION
        )
        first_attestation = "    " + first_attestation
        self.assertIn(first_attestation, text)
        braced_signer_reassignment = text.replace(
            first_attestation,
            '    ${signerWorkflow} = "unsafe/example.yml"\n    '
            + variable_attestation,
            1,
        )
        command_signer_reassignment = text.replace(
            first_attestation,
            '    Set-Variable -Name signerWorkflow -Value "unsafe/example.yml"\n'
            '    '
            + variable_attestation,
            1,
        )

        approval = text.index("$confirmedApprovedSha -cne $approvedSha")
        pre_approval = text[:approval]
        post_approval = text[approval:]
        fetch = "git fetch origin main --tags"
        self.assertIn(fetch, post_approval)
        commented_post_approval_fetch = pre_approval + post_approval.replace(
            fetch, "# " + fetch, 1
        )

        tag_query = (
            '$postApprovalTag = git ls-remote --tags origin '
            '"refs/tags/$releaseTag"'
        )
        self.assertIn(tag_query, post_approval)
        commented_candidate_tag_query = pre_approval + post_approval.replace(
            tag_query, "# " + tag_query, 1
        )

        mutations = {
            "braced signer reassignment": braced_signer_reassignment,
            "Set-Variable signer reassignment": command_signer_reassignment,
            "commented post-approval fetch": commented_post_approval_fetch,
            "commented candidate tag query": commented_candidate_tag_query,
        }
        for name, mutated in mutations.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_runbook_contract(self, mutated)

    def test_runbook_contract_rejects_structural_bypasses(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        assert_runbook_contract(self, text)

        first_attestation = PROVENANCE_COMMANDS[0]
        variable_attestation = first_attestation.replace(
            APPROVED_SIGNER_OPTION, VARIABLE_SIGNER_OPTION
        )
        self.assertIn("    " + first_attestation, text)

        def reintroduce_signer_seam(assignment: str) -> str:
            return text.replace(
                "    " + first_attestation,
                "    " + assignment + "\n    " + variable_attestation,
                1,
            )

        short_parameter_reassignment = reintroduce_signer_seam(
            'Set-Variable -N signerWorkflow -Value "unsafe/example.yml"'
        )
        alias_reassignment = reintroduce_signer_seam(
            'sv -Name signerWorkflow -Value "unsafe/example.yml"'
        )

        approval = text.index("$confirmedApprovedSha -cne $approvedSha")
        pre_approval = text[:approval]
        post_approval = text[approval:]
        fetch = "git fetch origin main --tags"
        self.assertIn(fetch, post_approval)
        conditional_fetch = pre_approval + post_approval.replace(
            fetch, "if ($false) {\n    " + fetch + "\n}", 1
        )

        tag_query = (
            '$postApprovalTag = git ls-remote --tags origin '
            '"refs/tags/$releaseTag"'
        )
        self.assertIn(tag_query, post_approval)
        conditional_tag_query = pre_approval + post_approval.replace(
            tag_query, "if ($false) {\n    " + tag_query + "\n}", 1
        )

        mutations = {
            "short Set-Variable parameter": short_parameter_reassignment,
            "Set-Variable alias": alias_reassignment,
            "conditional post-approval fetch": conditional_fetch,
            "conditional candidate tag query": conditional_tag_query,
        }
        for name, mutated in mutations.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_runbook_contract(self, mutated)

    @unittest.skipUnless(POWERSHELL, "PowerShell 7 is required to test note normalisation")
    def test_note_normaliser_only_collapses_crlf(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        self.assertIn(NOTE_NORMALISER, text)
        probe = NOTE_NORMALISER + r'''
$windowsNotes = "heading`r`nbody`r`n"
$githubNotes = "heading`nbody`n"
if ((ConvertTo-Lf $windowsNotes) -cne (ConvertTo-Lf $githubNotes)) { exit 1 }
if ((ConvertTo-Lf "body`r`n") -ceq (ConvertTo-Lf "body")) { exit 2 }
if ((ConvertTo-Lf "body") -ceq (ConvertTo-Lf "changed")) { exit 3 }
'''
        result = subprocess.run(
            [POWERSHELL, "-NoLogo", "-NoProfile", "-NonInteractive", "-Command", probe],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_v015_evidence_has_exact_completed_contract(self) -> None:
        assert_evidence_contract(self, EVIDENCE.read_text(encoding="utf-8"))

    def test_v015_evidence_rejects_identity_and_digest_mutations(self) -> None:
        text = EVIDENCE.read_text(encoding="utf-8")
        assert_evidence_contract(self, text)
        for marker in EVIDENCE_MARKERS:
            with self.subTest(marker=marker.split()[0]):
                replacement = marker[:-1] + ("0" if marker[-1] != "0" else "1")
                mutated = text.replace(marker, replacement, 1)
                with self.assertRaises(AssertionError):
                    assert_evidence_contract(self, mutated)

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
