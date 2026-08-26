from pathlib import Path
import base64
import copy
from hashlib import sha256
import json
import re
import shutil
import subprocess
import textwrap
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNBOOK = ROOT / "RELEASING.md"
EVIDENCE = ROOT / "docs" / "releases" / "v0.1.5.md"
POWERSHELL = shutil.which("pwsh")
FENCE_OPENING = re.compile(
    r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>[^\r\n]*)(?:\r?\n|\Z)",
    re.MULTILINE,
)
POWERSHELL_FENCE_LANGUAGES = frozenset({"powershell", "pwsh", "ps1"})
# SHA-256 of compact UTF-8 JSON for the five ordered PowerShell fence bodies.
APPROVED_POWERSHELL_FENCES_SHA256 = (
    "ec22fc86dfaf1392709bff9f4c2252a03be688e4d6ff8f30e620428eb8bb818f"
)
EXPECTED_POWERSHELL_FENCES = 5
POWERSHELL_VERSION_PREREQUISITE = (
    "Use a clean checkout of remote `main` and PowerShell 7.4 or newer."
)
POWERSHELL_VERSION_GATE = r'''if ($PSVersionTable.PSVersion -lt [version]"7.4") {
    throw "PowerShell 7.4 or newer is required"
}'''

INITIAL_FENCE = r"""$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
if ($PSVersionTable.PSVersion -lt [version]"7.4") {
    throw "PowerShell 7.4 or newer is required"
}
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


def powershell_fence_bodies(text: str) -> list[str]:
    bodies = []
    search_start = 0
    while opening := FENCE_OPENING.search(text, search_start):
        marker = opening["marker"]
        info = opening["info"]
        if marker.startswith("`") and "`" in info:
            search_start = opening.end()
            continue

        closing = re.compile(
            rf"^ {{0,3}}{re.escape(marker[0])}{{{len(marker)},}}[ \t]*(?:\r?\n|\Z)",
            re.MULTILINE,
        ).search(text, opening.end())
        body_end = closing.start() if closing else len(text)
        body = text[opening.end() : body_end]
        if closing:
            if body.endswith("\r\n"):
                body = body[:-2]
            elif body.endswith(("\r", "\n")):
                body = body[:-1]

        info_words = info.strip().split(maxsplit=1)
        if (
            info_words
            and info_words[0].casefold() in POWERSHELL_FENCE_LANGUAGES
        ):
            bodies.append(body)

        search_start = closing.end() if closing else len(text)

    return bodies


POWERSHELL_AST_EVIDENCE = r'''$ErrorActionPreference = "Stop"
$sources = @([Console]::In.ReadToEnd() | ConvertFrom-Json)
$assignments = [Collections.Generic.List[object]]::new()
$commands = [Collections.Generic.List[object]]::new()
$conditions = [Collections.Generic.List[object]]::new()
$foreachStatements = [Collections.Generic.List[object]]::new()
$functionDefinitions = [Collections.Generic.List[object]]::new()
$invocations = [Collections.Generic.List[object]]::new()
$mutatingUnaryExpressions = [Collections.Generic.List[object]]::new()
$throws = [Collections.Generic.List[object]]::new()
$terminators = [Collections.Generic.List[object]]::new()
$redirections = [Collections.Generic.List[object]]::new()
$tryStatements = [Collections.Generic.List[object]]::new()

$scopePlumbingTypes = @("NamedBlockAst", "PipelineAst", "StatementBlockAst")

function Get-NonPlumbingAncestors([object]$Node) {
    $scope = [Collections.Generic.List[string]]::new()
    $parent = $Node.Parent
    while ($null -ne $parent) {
        if ($scopePlumbingTypes -cnotcontains $parent.GetType().Name) {
            $scope.Add($parent.GetType().Name)
        }
        $parent = $parent.Parent
    }
    return [string[]]$scope
}

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
        $statementBlock = $node.Parent
        while (
            $null -ne $statementBlock -and
            $statementBlock -isnot
            [Management.Automation.Language.StatementBlockAst] -and
            $statementBlock -isnot
            [Management.Automation.Language.NamedBlockAst]
        ) {
            $statementBlock = $statementBlock.Parent
        }
        $assignments.Add([pscustomobject]@{
            fence = $fence
            name = $name
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            scope = [object[]]@(Get-NonPlumbingAncestors $node)
            lastInBlock = (
                $null -ne $statementBlock -and
                $statementBlock.Statements.Count -gt 0 -and
                [object]::ReferenceEquals(
                    $statementBlock.Statements[-1], $node
                )
            )
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
            invocationOperator = $node.InvocationOperator.ToString()
            parameters = [object[]]@(
                $node.CommandElements |
                    Where-Object {
                        $_ -is
                        [Management.Automation.Language.CommandParameterAst]
                    } |
                    ForEach-Object { $_.ParameterName }
            )
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            scope = [object[]]@(Get-NonPlumbingAncestors $node)
            topLevel = (
                $node.Parent -is [Management.Automation.Language.PipelineAst] -and
                $node.Parent.Parent -is
                [Management.Automation.Language.NamedBlockAst] -and
                $node.Parent.Parent.Parent -is
                [Management.Automation.Language.ScriptBlockAst]
            )
        })
    }

    $functionNodes = $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.FunctionDefinitionAst]
    }, $true)
    foreach ($node in $functionNodes) {
        $functionDefinitions.Add([pscustomobject]@{
            fence = $fence
            name = $node.Name
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            scope = [object[]]@(Get-NonPlumbingAncestors $node)
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
                bodyStart = $clause.Item2.Extent.StartOffset
                bodyEnd = $clause.Item2.Extent.EndOffset
                scope = [object[]]@(Get-NonPlumbingAncestors $node)
            })
        }
    }

    $foreachNodes = $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.ForEachStatementAst]
    }, $true)
    foreach ($node in $foreachNodes) {
        $foreachStatements.Add([pscustomobject]@{
            fence = $fence
            variable = $node.Variable.VariablePath.UserPath
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            scope = [object[]]@(Get-NonPlumbingAncestors $node)
        })
    }

    $tryNodes = $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.TryStatementAst]
    }, $true)
    foreach ($node in $tryNodes) {
        $tryStatements.Add([pscustomobject]@{
            fence = $fence
            catchCount = $node.CatchClauses.Count
            hasFinally = $null -ne $node.Finally
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            scope = [object[]]@(Get-NonPlumbingAncestors $node)
        })
    }

    $invocationNodes = $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.InvokeMemberExpressionAst]
    }, $true)
    foreach ($node in $invocationNodes) {
        $invocations.Add([pscustomobject]@{
            fence = $fence
            member = $node.Member.Extent.Text
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            scope = [object[]]@(Get-NonPlumbingAncestors $node)
        })
    }

    $throwNodes = $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.ThrowStatementAst]
    }, $true)
    foreach ($node in $throwNodes) {
        $throws.Add([pscustomobject]@{
            fence = $fence
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            scope = [object[]]@(Get-NonPlumbingAncestors $node)
        })
    }

    $terminationNodes = $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.ReturnStatementAst] -or
        $node -is [Management.Automation.Language.ExitStatementAst] -or
        $node -is [Management.Automation.Language.BreakStatementAst] -or
        $node -is [Management.Automation.Language.ContinueStatementAst] -or
        $node -is [Management.Automation.Language.TrapStatementAst]
    }, $true)
    foreach ($node in $terminationNodes) {
        $terminators.Add([pscustomobject]@{
            fence = $fence
            kind = $node.GetType().Name
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            scope = [object[]]@(Get-NonPlumbingAncestors $node)
        })
    }

    $mutatingUnaryNodes = $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.UnaryExpressionAst] -and
        $node.TokenKind.ToString() -in @(
            "PostfixPlusPlus",
            "PostfixMinusMinus",
            "PrefixPlusPlus",
            "PrefixMinusMinus"
        )
    }, $true)
    foreach ($node in $mutatingUnaryNodes) {
        $mutatingUnaryExpressions.Add([pscustomobject]@{
            fence = $fence
            kind = $node.TokenKind.ToString()
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            scope = [object[]]@(Get-NonPlumbingAncestors $node)
        })
    }

    $redirectionNodes = $ast.FindAll({
        param($node)
        $node -is [Management.Automation.Language.RedirectionAst]
    }, $true)
    foreach ($node in $redirectionNodes) {
        $redirections.Add([pscustomobject]@{
            fence = $fence
            text = $node.Extent.Text
            start = $node.Extent.StartOffset
            end = $node.Extent.EndOffset
            scope = [object[]]@(Get-NonPlumbingAncestors $node)
        })
    }
}

[pscustomobject]@{
    assignments = [object[]]$assignments
    commands = [object[]]$commands
    conditions = [object[]]$conditions
    foreachStatements = [object[]]$foreachStatements
    functionDefinitions = [object[]]$functionDefinitions
    invocations = [object[]]$invocations
    mutatingUnaryExpressions = [object[]]$mutatingUnaryExpressions
    throws = [object[]]$throws
    terminators = [object[]]$terminators
    redirections = [object[]]$redirections
    tryStatements = [object[]]$tryStatements
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

VERIFICATION_NOT_COMPLETE = "$verificationSucceeded = $false"
VERIFICATION_COMPLETE = "$verificationSucceeded = $true"
CLEANUP_SUCCESS_CONDITION = (
    "$verificationSucceeded -and (Test-Path -LiteralPath $downloadPath)"
)
SERVER_DIGEST_CONDITION = "$serverDigestChecks -ne 4"
PAYLOAD_DIGEST_CONDITION = (
    "$checksumLines.Count -ne 3 -or $payloadChecksumChecks -ne 3"
)
CLEANUP_CONTAINMENT_CONDITION = '''[IO.Path]::IsPathRooted($relativeDownloadPath) -or
            $relativeDownloadPath -eq "." -or
            $relativeDownloadPath -eq ".." -or
            $relativeDownloadPath.StartsWith("..$([IO.Path]::DirectorySeparatorChar)") -or
            $relativeDownloadPath.StartsWith("..$([IO.Path]::AltDirectorySeparatorChar)")'''
CLEANUP_TEMP_ROOT_REPARSE_CONDITION = (
    "$tempRootItem.Attributes -band [IO.FileAttributes]::ReparsePoint"
)
CLEANUP_DOWNLOAD_REPARSE_CONDITION = (
    "$downloadItem.Attributes -band [IO.FileAttributes]::ReparsePoint"
)
CLEANUP_GUARDS = (
    (
        CLEANUP_CONTAINMENT_CONDITION,
        'throw "cleanup path is not a unique contained child"',
    ),
    (
        CLEANUP_TEMP_ROOT_REPARSE_CONDITION,
        'throw "system temporary directory became a reparse point"',
    ),
    (
        CLEANUP_DOWNLOAD_REPARSE_CONDITION,
        'throw "cleanup path is a reparse point"',
    ),
)
CLEANUP_ASSIGNMENTS = {
    "temproot": '''$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd(
            [IO.Path]::DirectorySeparatorChar,
            [IO.Path]::AltDirectorySeparatorChar
        )''',
    "resolveddownloadpath": (
        "$resolvedDownloadPath = [IO.Path]::GetFullPath($downloadPath)"
    ),
    "relativedownloadpath": (
        "$relativeDownloadPath = "
        "[IO.Path]::GetRelativePath($tempRoot, $resolvedDownloadPath)"
    ),
    "temprootitem": "$tempRootItem = Get-Item -LiteralPath $tempRoot -Force",
    "downloaditem": (
        "$downloadItem = Get-Item -LiteralPath $resolvedDownloadPath -Force"
    ),
}
DOWNLOAD_PATH_ASSIGNMENT = '''$downloadPath = Join-Path `
    -Path $tempRoot `
    -ChildPath ("hardhat-ledger-release-" + [guid]::NewGuid().ToString("N"))'''
ROOT_EXECUTION_SCOPE = ("ScriptBlockAst",)
TRY_EXECUTION_SCOPE = ("TryStatementAst", "ScriptBlockAst")
CLEANUP_EXECUTION_SCOPE = (
    "IfStatementAst",
    "TryStatementAst",
    "ScriptBlockAst",
)
CLEANUP_SUCCESS_GATE = """} finally {
    if ($verificationSucceeded -and (Test-Path -LiteralPath $downloadPath)) {"""
EVIDENCE_RETENTION_NOTICE = """    } elseif (-not $verificationSucceeded) {
        try {
            [Console]::Error.WriteLine(
                "release verification failed; evidence retained at literal path: $resolvedDownloadPath"
            )
        } catch {
            # Do not mask the original verification failure.
        }
    }"""

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

EVIDENCE_COMPLETED_STATE = (
    "At acceptance, GitHub reported `v0.1.5` as immutable, non-draft, "
    "non-prerelease and the latest release."
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


def normalise_powershell_reference(value: object) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def assert_powershell_fence_snapshot(
    testcase: unittest.TestCase, fences: list[str]
) -> None:
    testcase.assertEqual(len(fences), EXPECTED_POWERSHELL_FENCES)
    payload = json.dumps(
        fences,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    testcase.assertEqual(
        sha256(payload).hexdigest(),
        APPROVED_POWERSHELL_FENCES_SHA256,
    )


def normalise_powershell_command_name(value: object) -> str:
    return str(value).casefold().rsplit("\\", 1)[-1]


def only_ast_node(
    testcase: unittest.TestCase,
    nodes: list[dict[str, object]],
    **expected: object,
) -> dict[str, object]:
    matches = [
        node
        for node in nodes
        if all(node.get(key) == value for key, value in expected.items())
    ]
    testcase.assertEqual(len(matches), 1)
    return matches[0]


def assert_release_verification_ast_contract(
    testcase: unittest.TestCase,
    ast: dict[str, list[dict[str, object]]],
) -> None:
    verification_assignments = [
        assignment
        for assignment in ast["assignments"]
        if assignment["name"] is not None
        and str(assignment["name"]).casefold().rsplit(":", 1)[-1]
        == "verificationsucceeded"
    ]
    testcase.assertEqual(len(verification_assignments), 2)
    false_assignment = only_ast_node(
        testcase,
        verification_assignments,
        text=VERIFICATION_NOT_COMPLETE,
    )
    true_assignment = only_ast_node(
        testcase,
        verification_assignments,
        text=VERIFICATION_COMPLETE,
    )
    testcase.assertTrue(false_assignment["topLevel"])
    testcase.assertEqual(
        false_assignment["scope"],
        list(ROOT_EXECUTION_SCOPE),
    )
    testcase.assertEqual(
        true_assignment["scope"],
        list(TRY_EXECUTION_SCOPE),
    )
    testcase.assertTrue(true_assignment["lastInBlock"])
    verification_fence = true_assignment["fence"]
    testcase.assertEqual(false_assignment["fence"], verification_fence)
    verification_not_complete_end = int(false_assignment["end"])
    verification_complete_start = int(true_assignment["start"])

    indirect_assignments = [
        assignment
        for assignment in ast["assignments"]
        if assignment["name"] is None
    ]
    testcase.assertEqual(indirect_assignments, [])

    command_resolution_providers = {"alias", "env", "function"}
    command_resolution_assignments = [
        assignment
        for assignment in ast["assignments"]
        if assignment["name"] is not None
        and str(assignment["name"]).casefold().split(":", 1)[0]
        in command_resolution_providers
    ]
    testcase.assertEqual(command_resolution_assignments, [])

    immutable_identity_assignment_counts = {
        "approvedsha": 1,
        "confirmedapprovedsha": 1,
        "expectedpolicysha": 1,
        "protectedtags": 1,
        "releasetag": 1,
        "repo": 1,
    }
    for name, expected_count in immutable_identity_assignment_counts.items():
        actual_count = sum(
            assignment["name"] is not None
            and str(assignment["name"]).casefold().rsplit(":", 1)[-1]
            == name
            for assignment in ast["assignments"]
        )
        testcase.assertEqual(actual_count, expected_count)

    assignment_counts: dict[str, int] = {}
    for assignment in ast["assignments"]:
        if assignment["name"] is None:
            continue
        name = str(assignment["name"]).casefold().rsplit(":", 1)[-1]
        assignment_counts[name] = assignment_counts.get(name, 0) + 1
    expected_reassignment_counts = {
        "downloaditem": 2,
        "nativeerrorpreference": 3,
        "psnativecommanduseerroractionpreference": 7,
        "relativedownloadpath": 2,
        "resolveddownloadpath": 2,
        "temproot": 2,
        "temprootitem": 2,
        "verificationsucceeded": 2,
    }
    actual_reassignment_counts = {
        name: count for name, count in assignment_counts.items() if count > 1
    }
    testcase.assertEqual(
        actual_reassignment_counts,
        expected_reassignment_counts,
    )

    expected_mutating_unary_expressions = [
        (
            verification_fence,
            "PostfixPlusPlus",
            text,
            [
                "CommandExpressionAst",
                "ForEachStatementAst",
                "TryStatementAst",
                "ScriptBlockAst",
            ],
        )
        for text in (
            "$serverDigestChecks++",
            "$payloadChecksumChecks++",
        )
    ]
    actual_mutating_unary_expressions = [
        (
            int(expression["fence"]),
            str(expression["kind"]),
            str(expression["text"]),
            expression["scope"],
        )
        for expression in ast["mutatingUnaryExpressions"]
    ]
    testcase.assertCountEqual(
        actual_mutating_unary_expressions,
        expected_mutating_unary_expressions,
    )

    actual_foreach_variables = [
        (
            int(statement["fence"]),
            str(statement["variable"]).casefold(),
        )
        for statement in ast["foreachStatements"]
    ]
    expected_foreach_variables = [
        (0, "requiredcheck"),
        (verification_fence, "assetname"),
        (verification_fence, "payloadname"),
    ]
    testcase.assertCountEqual(
        actual_foreach_variables,
        expected_foreach_variables,
    )

    root_condition_scope = tuple(ROOT_EXECUTION_SCOPE)
    try_condition_scope = tuple(TRY_EXECUTION_SCOPE)
    expected_condition_scopes_by_fence = (
        sorted(
            [root_condition_scope] * 11
            + [("ForEachStatementAst", *root_condition_scope)]
        ),
        sorted([root_condition_scope] * 9),
        sorted([root_condition_scope] * 5),
        sorted(
            [root_condition_scope] * 3
            + [("ForEachStatementAst", *try_condition_scope)] * 4
            + [try_condition_scope] * 4
            + [("IfStatementAst", *try_condition_scope)] * 3
        ),
        sorted([root_condition_scope] * 8),
    )
    actual_condition_scopes_by_fence = tuple(
        sorted(
            tuple(condition["scope"])
            for condition in ast["conditions"]
            if int(condition["fence"]) == fence
        )
        for fence in range(EXPECTED_POWERSHELL_FENCES)
    )
    testcase.assertEqual(
        actual_condition_scopes_by_fence,
        expected_condition_scopes_by_fence,
    )

    non_throwing_conditions = {
        (verification_fence, CLEANUP_SUCCESS_CONDITION),
        (verification_fence, "-not $verificationSucceeded"),
    }
    for condition in ast["conditions"]:
        direct_throws = [
            throw
            for throw in ast["throws"]
            if throw["fence"] == condition["fence"]
            and int(condition["bodyStart"]) < int(throw["start"])
            and int(throw["end"]) < int(condition["bodyEnd"])
            and throw["scope"] == ["IfStatementAst", *condition["scope"]]
        ]
        condition_key = (
            int(condition["fence"]),
            str(condition["condition"]),
        )
        expected_throw_count = (
            0 if condition_key in non_throwing_conditions else 1
        )
        testcase.assertEqual(len(direct_throws), expected_throw_count)

    provider_assignment_references = [
        assignment
        for assignment in ast["assignments"]
        if assignment["fence"] == verification_fence
        and assignment not in verification_assignments
        and verification_not_complete_end < int(assignment["start"])
        and (
            "verificationsucceeded"
            in normalise_powershell_reference(assignment["text"])
            or "variableverification"
            in normalise_powershell_reference(assignment["text"])
        )
    ]
    testcase.assertEqual(provider_assignment_references, [])

    allowed_command_names_by_fence = (
        {
            "convertfrom-json",
            "gh",
            "git",
            "python",
            "where-object",
        },
        {"convertfrom-json", "gh", "git", "read-host"},
        {
            "compare-object",
            "convertfrom-json",
            "convertto-lf",
            "foreach-object",
            "get-content",
            "gh",
            "sort-object",
        },
        {
            "get-content",
            "get-filehash",
            "get-item",
            "gh",
            "join-path",
            "new-item",
            "out-null",
            "remove-item",
            "test-path",
            "where-object",
        },
        {"convertfrom-json", "gh"},
    )
    testcase.assertEqual(
        len(allowed_command_names_by_fence),
        EXPECTED_POWERSHELL_FENCES,
    )
    verification_commands = [
        command
        for command in ast["commands"]
        if command["fence"] == verification_fence
    ]
    unexpected_commands = [
        command
        for command in ast["commands"]
        if command["name"] is None
        or normalise_powershell_command_name(command["name"])
        not in allowed_command_names_by_fence[int(command["fence"])]
    ]
    testcase.assertEqual(unexpected_commands, [])

    allowed_gh_operations = {
        ("api",),
        ("attestation", "verify"),
        ("release", "download"),
        ("release", "verify"),
        ("release", "verify-asset"),
        ("release", "view"),
    }
    unsafe_gh_commands = []
    for command in ast["commands"]:
        if command["name"] is None or (
            normalise_powershell_command_name(command["name"]) != "gh"
        ):
            continue
        words = re.sub(r"`\r?\n[ \t]*", " ", str(command["text"])).split()
        operation = tuple(word.casefold() for word in words[1:3])
        if operation[:1] == ("api",):
            operation = operation[:1]
            api_parameters = {
                str(parameter).casefold()
                for parameter in command["parameters"]
            }
            if not api_parameters <= {"h", "jq"}:
                unsafe_gh_commands.append(command)
                continue
        if operation not in allowed_gh_operations:
            unsafe_gh_commands.append(command)
    testcase.assertEqual(unsafe_gh_commands, [])

    expected_function_definitions = [(2, "convertto-lf", NOTE_NORMALISER)]
    actual_function_definitions = [
        (
            int(function["fence"]),
            str(function["name"]).casefold(),
            str(function["text"]),
        )
        for function in ast["functionDefinitions"]
    ]
    testcase.assertEqual(
        actual_function_definitions,
        expected_function_definitions,
    )

    expected_state_writer_commands = [
        (
            "new-item",
            "New-Item -ItemType Directory -Path $resolvedDownloadPath",
        ),
        (
            "remove-item",
            "Remove-Item -LiteralPath $resolvedDownloadPath -Force -Recurse",
        ),
    ]
    actual_state_writer_commands = [
        (
            normalise_powershell_command_name(command["name"]),
            str(command["text"]),
        )
        for command in verification_commands
        if command["name"] is not None
        and normalise_powershell_command_name(command["name"])
        in {"new-item", "remove-item"}
    ]
    testcase.assertCountEqual(
        actual_state_writer_commands,
        expected_state_writer_commands,
    )
    allowed_invocation_members_by_fence = (
        {"matches"},
        set(),
        {"replace", "substring"},
        {
            "getfullpath",
            "getrelativepath",
            "gettemppath",
            "ispathrooted",
            "newguid",
            "startswith",
            "tolowerinvariant",
            "tostring",
            "trimend",
            "writeline",
        },
        set(),
    )
    unexpected_invocations = [
        invocation
        for invocation in ast["invocations"]
        if str(invocation["member"]).casefold()
        not in allowed_invocation_members_by_fence[int(invocation["fence"])]
    ]
    testcase.assertEqual(unexpected_invocations, [])
    state_writer_parameter_names = {
        "errorvariable",
        "informationvariable",
        "outvariable",
        "pipelinevariable",
        "warningvariable",
    }
    state_writer_parameter_aliases = {"ev", "iv", "ov", "pv", "wv"}

    def parameter_writes_state(value: object) -> bool:
        parameter = str(value).casefold()
        return parameter in state_writer_parameter_aliases or (
            len(parameter) >= 3
            and any(
                name.startswith(parameter) for name in state_writer_parameter_names
            )
        )

    state_writer_parameter_references = [
        command
        for command in ast["commands"]
        if any(
            parameter_writes_state(parameter)
            for parameter in command["parameters"]
        )
    ]
    testcase.assertEqual(state_writer_parameter_references, [])
    expected_redirections = [
        (
            fence,
            "2>&1",
            [
                "CommandAst",
                "AssignmentStatementAst",
                "TryStatementAst",
                "ScriptBlockAst",
            ],
        )
        for fence in (0, 1, 4)
    ]
    actual_redirections = [
        (
            int(redirection["fence"]),
            str(redirection["text"]),
            redirection["scope"],
        )
        for redirection in ast["redirections"]
    ]
    testcase.assertCountEqual(actual_redirections, expected_redirections)

    preference_names = {
        "erroractionpreference",
        "psnativecommanduseerroractionpreference",
    }
    actual_preference_assignments = [
        (
            int(assignment["fence"]),
            str(assignment["name"]).casefold().rsplit(":", 1)[-1],
            str(assignment["text"]),
            assignment["scope"],
        )
        for assignment in ast["assignments"]
        if assignment["name"] is not None
        and str(assignment["name"]).casefold().rsplit(":", 1)[-1]
        in preference_names
    ]
    expected_preference_assignments = [
        (
            0,
            "erroractionpreference",
            '$ErrorActionPreference = "Stop"',
            list(ROOT_EXECUTION_SCOPE),
        ),
        (
            0,
            "psnativecommanduseerroractionpreference",
            "$PSNativeCommandUseErrorActionPreference = $true",
            list(ROOT_EXECUTION_SCOPE),
        ),
        *[
            (
                fence,
                "psnativecommanduseerroractionpreference",
                text,
                list(TRY_EXECUTION_SCOPE),
            )
            for fence in (0, 1, 4)
            for text in (
                "$PSNativeCommandUseErrorActionPreference = $false",
                "$PSNativeCommandUseErrorActionPreference = "
                "$nativeErrorPreference",
            )
        ],
    ]
    testcase.assertCountEqual(
        actual_preference_assignments,
        expected_preference_assignments,
    )

    dynamic_execution_commands = [
        command
        for command in ast["commands"]
        if str(command["invocationOperator"]).casefold() != "unknown"
    ]
    testcase.assertEqual(dynamic_execution_commands, [])

    flag_command_references = [
        command
        for command in ast["commands"]
        if command["fence"] == verification_fence
        and verification_not_complete_end < int(command["start"])
        and (
            "verificationsucceeded"
            in normalise_powershell_reference(command["text"])
            or "variableverification"
            in normalise_powershell_reference(command["text"])
        )
    ]
    testcase.assertEqual(flag_command_references, [])

    actual_terminators = [
        (
            int(terminator["fence"]),
            str(terminator["kind"]),
            str(terminator["text"]),
            terminator["scope"],
        )
        for terminator in ast["terminators"]
    ]
    expected_terminators = [
        (
            2,
            "ReturnStatementAst",
            'return $Text.Replace("`r`n", "`n")',
            ["ScriptBlockAst", "FunctionDefinitionAst", "ScriptBlockAst"],
        )
    ]
    testcase.assertEqual(actual_terminators, expected_terminators)

    actual_try_shapes = [
        (
            int(statement["fence"]),
            int(statement["catchCount"]),
            bool(statement["hasFinally"]),
        )
        for statement in ast["tryStatements"]
    ]
    expected_try_shapes = [
        (0, 0, True),
        (1, 0, True),
        (verification_fence, 0, True),
        (verification_fence, 1, False),
        (4, 0, True),
    ]
    testcase.assertCountEqual(actual_try_shapes, expected_try_shapes)

    def assert_direct_throw(
        condition: dict[str, object], expected_throw: str
    ) -> None:
        matching_throws = [
            throw
            for throw in ast["throws"]
            if throw["fence"] == condition["fence"]
            and throw["text"] == expected_throw
            and int(condition["bodyStart"]) < int(throw["start"])
            and int(throw["end"]) < int(condition["bodyEnd"])
        ]
        testcase.assertEqual(len(matching_throws), 1)
        testcase.assertEqual(
            matching_throws[0]["scope"],
            ["IfStatementAst", *condition["scope"]],
        )

    for expected_condition, expected_throw in (
        (
            SERVER_DIGEST_CONDITION,
            'throw "four server digest checks did not complete"',
        ),
        (
            PAYLOAD_DIGEST_CONDITION,
            'throw "exactly three payload checksum bindings were not proved"',
        ),
    ):
        condition = only_ast_node(
            testcase,
            ast["conditions"],
            fence=verification_fence,
            condition=expected_condition,
        )
        testcase.assertEqual(
            condition["scope"],
            list(TRY_EXECUTION_SCOPE),
        )
        testcase.assertLess(
            int(condition["end"]),
            verification_complete_start,
        )
        assert_direct_throw(condition, expected_throw)

    for expected_command in (
        *PROVENANCE_COMMANDS,
        *SPDX_COMMANDS,
        *RELEASE_VERIFICATION_COMMANDS,
    ):
        command = only_ast_node(
            testcase,
            ast["commands"],
            text=expected_command,
        )
        testcase.assertEqual(command["fence"], verification_fence)
        testcase.assertEqual(
            command["scope"],
            list(TRY_EXECUTION_SCOPE),
        )
        testcase.assertLess(
            int(command["end"]),
            verification_complete_start,
        )

    cleanup_condition = only_ast_node(
        testcase,
        ast["conditions"],
        fence=verification_fence,
        condition=CLEANUP_SUCCESS_CONDITION,
    )
    testcase.assertEqual(
        cleanup_condition["scope"],
        list(TRY_EXECUTION_SCOPE),
    )
    cleanup_body_start = int(cleanup_condition["bodyStart"])
    cleanup_body_end = int(cleanup_condition["bodyEnd"])

    cleanup_guards = {}
    cleanup_conditions = [
        condition
        for condition in ast["conditions"]
        if condition["fence"] == verification_fence
        and cleanup_body_start < int(condition["start"])
        and int(condition["end"]) < cleanup_body_end
    ]
    for guard_condition, guard_throw in CLEANUP_GUARDS:
        guard = only_ast_node(
            testcase,
            cleanup_conditions,
            condition=guard_condition,
        )
        testcase.assertEqual(
            guard["scope"],
            list(CLEANUP_EXECUTION_SCOPE),
        )
        assert_direct_throw(guard, guard_throw)
        cleanup_guards[guard_throw] = guard

    critical_assignment_counts = {
        "downloadpath": 1,
        **{name: 2 for name in CLEANUP_ASSIGNMENTS},
    }
    critical_assignments = [
        assignment
        for assignment in ast["assignments"]
        if assignment["fence"] == verification_fence
        and assignment["name"] is not None
        and str(assignment["name"]).casefold().rsplit(":", 1)[-1]
        in critical_assignment_counts
    ]
    for assignment_name, expected_count in critical_assignment_counts.items():
        actual_count = sum(
            str(assignment["name"]).casefold().rsplit(":", 1)[-1]
            == assignment_name
            for assignment in critical_assignments
        )
        testcase.assertEqual(actual_count, expected_count)

    download_path_assignment = only_ast_node(
        testcase,
        critical_assignments,
        name="downloadPath",
        text=DOWNLOAD_PATH_ASSIGNMENT,
    )
    testcase.assertEqual(
        download_path_assignment["scope"],
        list(ROOT_EXECUTION_SCOPE),
    )

    cleanup_assignments_by_name = {}
    cleanup_assignments = [
        assignment
        for assignment in critical_assignments
        if cleanup_body_start < int(assignment["start"])
        and int(assignment["end"]) < cleanup_body_end
    ]
    for assignment_name, expected_text in CLEANUP_ASSIGNMENTS.items():
        assignment = only_ast_node(
            testcase,
            cleanup_assignments,
            text=expected_text,
        )
        testcase.assertEqual(
            assignment["scope"],
            list(CLEANUP_EXECUTION_SCOPE),
        )
        cleanup_assignments_by_name[assignment_name] = assignment

    removal_command = only_ast_node(
        testcase,
        ast["commands"],
        fence=verification_fence,
        text="Remove-Item -LiteralPath $resolvedDownloadPath -Force -Recurse",
    )
    testcase.assertLess(cleanup_body_start, int(removal_command["start"]))
    testcase.assertLess(int(removal_command["end"]), cleanup_body_end)
    testcase.assertEqual(
        removal_command["scope"],
        list(CLEANUP_EXECUTION_SCOPE),
    )

    ordered_cleanup_nodes = (
        cleanup_assignments_by_name["temproot"],
        cleanup_assignments_by_name["resolveddownloadpath"],
        cleanup_assignments_by_name["relativedownloadpath"],
        cleanup_guards['throw "cleanup path is not a unique contained child"'],
        cleanup_assignments_by_name["temprootitem"],
        cleanup_guards[
            'throw "system temporary directory became a reparse point"'
        ],
        cleanup_assignments_by_name["downloaditem"],
        cleanup_guards['throw "cleanup path is a reparse point"'],
        removal_command,
    )
    for before, after in zip(ordered_cleanup_nodes, ordered_cleanup_nodes[1:]):
        testcase.assertLess(int(before["end"]), int(after["start"]))


def assert_powershell_version_contract(
    testcase: unittest.TestCase, text: str
) -> None:
    testcase.assertEqual(text.count(POWERSHELL_VERSION_PREREQUISITE), 1)
    testcase.assertEqual(text.count(POWERSHELL_VERSION_GATE), 1)
    testcase.assertIn(
        "$PSNativeCommandUseErrorActionPreference = $true", text
    )
    native_preference = text.index(
        "$PSNativeCommandUseErrorActionPreference = $true"
    )
    version_gate = text.index(POWERSHELL_VERSION_GATE)
    first_native_command = min(text.index("git fetch"), text.index("gh api"))
    testcase.assertLess(native_preference, version_gate)
    testcase.assertLess(version_gate, first_native_command)


def assert_evidence_retention_contract(
    testcase: unittest.TestCase,
    text: str,
    ast: dict[str, list[dict[str, object]]] | None = None,
) -> None:
    testcase.assertEqual(text.count(VERIFICATION_NOT_COMPLETE), 1)
    testcase.assertEqual(text.count(VERIFICATION_COMPLETE), 1)
    testcase.assertEqual(text.count(CLEANUP_SUCCESS_GATE), 1)
    testcase.assertEqual(text.count(EVIDENCE_RETENTION_NOTICE), 1)

    not_complete = text.index(VERIFICATION_NOT_COMPLETE)
    verification_try = text.index("try {", not_complete)
    complete = text.index(VERIFICATION_COMPLETE)
    final_block = text.index("} finally {", complete)
    cleanup = text.index(
        "Remove-Item -LiteralPath $resolvedDownloadPath -Force", final_block
    )
    retention_notice = text.index(EVIDENCE_RETENTION_NOTICE, cleanup)
    testcase.assertLess(not_complete, verification_try)
    testcase.assertLess(verification_try, complete)
    testcase.assertLess(complete, final_block)
    testcase.assertLess(final_block, cleanup)
    testcase.assertLess(cleanup, retention_notice)

    successful_cleanup = text[final_block:cleanup]
    testcase.assertIn("[IO.Path]::GetRelativePath", successful_cleanup)
    testcase.assertIn(
        "[IO.FileAttributes]::ReparsePoint", successful_cleanup
    )
    testcase.assertNotIn("throw", EVIDENCE_RETENTION_NOTICE)

    if ast is None:
        fences = powershell_fence_bodies(text)
        testcase.assertEqual(len(fences), EXPECTED_POWERSHELL_FENCES)
        ast = powershell_ast_evidence(testcase, fences)
    assert_release_verification_ast_contract(testcase, ast)


def assert_runbook_contract(testcase: unittest.TestCase, text: str) -> None:
    assert_powershell_version_contract(testcase, text)
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

    fences = powershell_fence_bodies(text)
    assert_powershell_fence_snapshot(testcase, fences)
    testcase.assertTrue(fences[0].startswith(INITIAL_FENCE))
    ast = powershell_ast_evidence(testcase, fences)
    assert_evidence_retention_contract(testcase, text, ast)
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
    testcase.assertEqual(
        approval_condition["scope"],
        list(ROOT_EXECUTION_SCOPE),
    )
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

    testcase.assertIn(CLEANUP_SUCCESS_GATE, text)
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
    testcase.assertIn(PROTECTED_TAG_LIVE_PROOF, text)
    testcase.assertNotIn("$protectedV014Commit = git rev-parse", text)


def assert_evidence_contract(testcase: unittest.TestCase, text: str) -> None:
    for marker in EVIDENCE_MARKERS:
        testcase.assertEqual(text.count(marker), 1)
    testcase.assertEqual(text.count(EVIDENCE_COMPLETED_STATE), 1)
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

        candidate_tag_query = (
            '$candidateTag = git ls-remote --tags origin '
            '"refs/tags/$releaseTag"'
        )
        pre_approval_tag_creation = text.replace(
            candidate_tag_query,
            'gh api --method POST "repos/$repo/git/refs" '
            '-f "ref=refs/tags/$releaseTag" -f "sha=$approvedSha"\n'
            + candidate_tag_query,
            1,
        )
        pre_approval_command_lookup_hook = text.replace(
            candidate_tag_query,
            "$ExecutionContext.InvokeCommand.PreCommandLookupAction = { }\n"
            + candidate_tag_query,
            1,
        )
        pre_approval_trap = text.replace(
            candidate_tag_query,
            "trap { continue }\n" + candidate_tag_query,
            1,
        )
        pre_approval_error_suppression = text.replace(
            candidate_tag_query,
            '$ErrorActionPreference = "SilentlyContinue"\n'
            + candidate_tag_query,
            1,
        )
        approval_prompt = (
            'Read-Host "Re-enter the separately approved full commit SHA"'
        )
        approval_out_variable = text.replace(
            approval_prompt,
            approval_prompt + " -OutVariable approvedSha",
            1,
        )
        approval_condition = "if ($confirmedApprovedSha -cne $approvedSha) {"
        approval_gate = '''if ($confirmedApprovedSha -cne $approvedSha) {
    throw "the separate approval does not match approvedSha"
}'''
        commented_approval_throw = text.replace(
            '    throw "the separate approval does not match approvedSha"',
            '    # throw "the separate approval does not match approvedSha"',
            1,
        )
        caught_approval_gate = text.replace(
            approval_gate,
            "try {\n" + approval_gate + "\n} catch { }",
            1,
        )
        conditional_approval_gate = text.replace(
            approval_gate,
            "if ($false) {\n" + approval_gate + "\n}",
            1,
        )
        short_circuited_approval_gate = text.replace(
            approval_gate,
            "$false -and {\n" + approval_gate + "\n}",
            1,
        )
        post_approval_immutable_gate = '''if (-not $postApprovalImmutableReleaseState.enabled) {
    throw "immutable releases were disabled after approval"
}'''
        conditional_post_approval_immutable_gate = text.replace(
            post_approval_immutable_gate,
            "if ($false) {\n" + post_approval_immutable_gate + "\n}",
            1,
        )
        approved_sha_reassignment = text.replace(
            approval_condition,
            "$approvedSha = $confirmedApprovedSha\n" + approval_condition,
            1,
        )
        release_tag_reassignment = text.replace(
            approval_condition,
            '$releaseTag = "v9.9.9"\n' + approval_condition,
            1,
        )
        server_digest_counter_reassignment = text.replace(
            "    if ($serverDigestChecks -ne 4) {",
            "    $serverDigestChecks = 4\n"
            "    if ($serverDigestChecks -ne 4) {",
            1,
        )
        server_digest_counter_increment = text.replace(
            "    if ($serverDigestChecks -ne 4) {",
            "    $serverDigestChecks++\n"
            "    if ($serverDigestChecks -ne 4) {",
            1,
        )
        verification_flag_increment = text.replace(
            VERIFICATION_NOT_COMPLETE,
            VERIFICATION_NOT_COMPLETE + "\n$verificationSucceeded++",
            1,
        )
        verification_flag_foreach_write = text.replace(
            VERIFICATION_NOT_COMPLETE,
            VERIFICATION_NOT_COMPLETE
            + "\nforeach ($verificationSucceeded in @($true)) { }",
            1,
        )
        post_approval_variable_redirection = pre_approval + post_approval.replace(
            fetch,
            '("0" * 40) > variable:approvedSha\n' + fetch,
            1,
        )
        gh_function_shadow = text.replace(
            first_attestation,
            "    function gh { }\n" + first_attestation,
            1,
        )
        release_download = (
            "    gh release download $releaseTag --repo $repo "
            "--dir $resolvedDownloadPath"
        )
        forged_file_hash = '''    function Get-FileHash {
        param([string]$LiteralPath)
        $assetName = $LiteralPath -replace '^.*[\\/]'
        [pscustomobject]@{ Hash = (($release.assets | Where-Object name -CEQ $assetName)[0].digest -replace '^sha256:') }
    }
'''
        get_file_hash_function_shadow = text.replace(
            release_download,
            forged_file_hash + release_download,
            1,
        )
        provider_shadows = {
            "function provider shadows gh": "${function:gh} = { 'shadowed' }",
            "alias provider shadows gh": "${alias:gh} = 'Write-Output'",
            "environment provider redirects command lookup": (
                "$env:PATH = 'C:\\unsafe;' + $env:PATH"
            ),
        }
        provider_shadow_mutations = {
            name: text.replace(
                first_attestation,
                "    " + assignment + "\n" + first_attestation,
                1,
            )
            for name, assignment in provider_shadows.items()
        }

        unsafe_extra_fences = {
            name: (
                text
                + f"\n\n{delimiter}{language}\n"
                + '''$releaseTag = "v9.9.9"\n'''
                + '''git tag -a $releaseTag HEAD -m $releaseTag\n'''
                + 'git push origin "refs/tags/$releaseTag"\n'
                + delimiter
                + "\n"
            )
            for name, delimiter, language in (
                ("extra powershell fence", "```", "powershell"),
                ("extra pwsh fence", "```", "pwsh"),
                ("extra ps1 fence", "```", "ps1"),
                ("extra padded powershell fence", "```", "powershell   "),
                (
                    "extra attributed powershell fence",
                    "```",
                    'powershell title="unsafe"',
                ),
                ("extra tilde pwsh fence", "~~~", "pwsh"),
            )
        }
        unsafe_extra_fences.update(
            {
                "pwsh fence with trailing info whitespace": (
                    text
                    + '''\n\n```pwsh \n'''
                    + '''Write-Output "unsafe untracked fence"\n```\n'''
                ),
                "ps1 fence with leading info whitespace": (
                    text
                    + '''\n\n``` ps1\n'''
                    + '''Write-Output "unsafe untracked fence"\n```\n'''
                ),
                "tilde powershell fence": (
                    text
                    + '''\n\n~~~powershell\n'''
                    + '''Write-Output "unsafe untracked fence"\n~~~\n'''
                ),
            }
        )

        mutations = {
            "braced signer reassignment": braced_signer_reassignment,
            "Set-Variable signer reassignment": command_signer_reassignment,
            "commented post-approval fetch": commented_post_approval_fetch,
            "commented candidate tag query": commented_candidate_tag_query,
            "pre-approval gh API tag creation": pre_approval_tag_creation,
            "pre-approval command lookup hook": (
                pre_approval_command_lookup_hook
            ),
            "pre-approval trap continues after failures": pre_approval_trap,
            "pre-approval error handling is weakened": (
                pre_approval_error_suppression
            ),
            "approval prompt overwrites approved SHA": approval_out_variable,
            "approval throw is only a comment": commented_approval_throw,
            "approval failure is swallowed by catch": caught_approval_gate,
            "approval guard is conditional": conditional_approval_gate,
            "approval guard is short-circuited": short_circuited_approval_gate,
            "post-approval immutable gate is conditional": (
                conditional_post_approval_immutable_gate
            ),
            "approved SHA is reassigned after confirmation": (
                approved_sha_reassignment
            ),
            "release tag is reassigned after validation": (
                release_tag_reassignment
            ),
            "server digest counter is reassigned before its gate": (
                server_digest_counter_reassignment
            ),
            "server digest counter is incremented before its gate": (
                server_digest_counter_increment
            ),
            "verification flag is incremented before proofs": (
                verification_flag_increment
            ),
            "foreach writes verification flag before proofs": (
                verification_flag_foreach_write
            ),
            "post-approval redirection overwrites approved SHA": (
                post_approval_variable_redirection
            ),
            "gh function shadows verification commands": gh_function_shadow,
            "Get-FileHash function forges local digests": (
                get_file_hash_function_shadow
            ),
            **provider_shadow_mutations,
            **unsafe_extra_fences,
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

    def test_powershell_version_gate_is_exact_and_fail_closed(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        candidate = text.replace(
            "Use a clean checkout of remote `main` and one PowerShell 7 session.",
            POWERSHELL_VERSION_PREREQUISITE,
            1,
        )
        if POWERSHELL_VERSION_GATE not in candidate:
            candidate = candidate.replace(
                "$PSNativeCommandUseErrorActionPreference = $true\n",
                "$PSNativeCommandUseErrorActionPreference = $true\n"
                + POWERSHELL_VERSION_GATE
                + "\n",
                1,
            )
        assert_powershell_version_contract(self, candidate)

        mutations = {
            "version gate removed": candidate.replace(
                POWERSHELL_VERSION_GATE + "\n", "", 1
            ),
            "PowerShell 7.3 accepted": candidate.replace(
                '[version]"7.4"', '[version]"7.3"', 1
            ),
        }
        for name, mutated in mutations.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_powershell_version_contract(self, mutated)

        assert_powershell_version_contract(self, text)

    def test_failed_verification_retains_evidence(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        candidate = text
        if VERIFICATION_NOT_COMPLETE not in candidate:
            candidate = candidate.replace(
                "try {\n    gh release download $releaseTag --repo $repo --dir $resolvedDownloadPath",
                VERIFICATION_NOT_COMPLETE
                + "\ntry {\n    gh release download $releaseTag --repo $repo --dir $resolvedDownloadPath",
                1,
            )
        if VERIFICATION_COMPLETE not in candidate:
            last_proof = "    " + RELEASE_VERIFICATION_COMMANDS[-1]
            candidate = candidate.replace(
                last_proof + "\n} finally {",
                last_proof + "\n    " + VERIFICATION_COMPLETE + "\n} finally {",
                1,
            )
        candidate = candidate.replace(
            "} finally {\n    if (Test-Path -LiteralPath $downloadPath) {",
            CLEANUP_SUCCESS_GATE,
            1,
        )
        if EVIDENCE_RETENTION_NOTICE not in candidate:
            candidate = candidate.replace(
                "        Remove-Item -LiteralPath $resolvedDownloadPath -Force -Recurse\n"
                "    }\n}\n```",
                "        Remove-Item -LiteralPath $resolvedDownloadPath -Force -Recurse\n"
                + EVIDENCE_RETENTION_NOTICE
                + "\n}\n```",
                1,
            )
        assert_evidence_retention_contract(self, candidate)

        unconditional_cleanup = candidate.replace(
            CLEANUP_SUCCESS_GATE,
            "} finally {\n    if (Test-Path -LiteralPath $downloadPath) {",
            1,
        )
        last_proof = "    " + RELEASE_VERIFICATION_COMMANDS[-1]
        premature_success = candidate.replace(
            last_proof + "\n    " + VERIFICATION_COMPLETE,
            "    " + VERIFICATION_COMPLETE + "\n" + last_proof,
            1,
        )
        initially_authorised_cleanup = candidate.replace(
            VERIFICATION_NOT_COMPLETE, VERIFICATION_COMPLETE, 1
        )
        mutations = {
            "cleanup is unconditional": unconditional_cleanup,
            "cleanup is authorised before the final proof": premature_success,
            "cleanup starts authorised": initially_authorised_cleanup,
        }
        for name, mutated in mutations.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_evidence_retention_contract(self, mutated)

        assert_evidence_retention_contract(self, text)

    def test_release_proofs_reject_conditional_and_early_success_bypasses(
        self,
    ) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        assert_runbook_contract(self, text)

        def wrap_executable(
            source: str,
            snippet: str,
            opening: str,
            closing: str,
        ) -> str:
            self.assertEqual(source.count(snippet), 1)
            indentation = snippet[: len(snippet) - len(snippet.lstrip())]
            return source.replace(
                snippet,
                indentation
                + opening
                + "\n"
                + textwrap.indent(snippet, "    ")
                + "\n"
                + indentation
                + closing,
                1,
            )

        download = (
            "    gh release download $releaseTag --repo $repo "
            "--dir $resolvedDownloadPath"
        )
        server_digest_gate = '''    if ($serverDigestChecks -ne 4) {
        throw "four server digest checks did not complete"
    }'''
        payload_digest_gate = '''    if ($checksumLines.Count -ne 3 -or $payloadChecksumChecks -ne 3) {
        throw "exactly three payload checksum bindings were not proved"
    }'''
        cleanup_temp_root_guard = '''        if ($tempRootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "system temporary directory became a reparse point"
        }'''
        cleanup_download_guard = '''        if ($downloadItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "cleanup path is a reparse point"
        }'''
        cleanup_download_guard_else = '''        if ($downloadItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            # unsafe path accepted
        } else {
            throw "cleanup path is a reparse point"
        }'''
        cleanup_removal = (
            "        Remove-Item -LiteralPath $resolvedDownloadPath "
            "-Force -Recurse"
        )
        cleanup_failure_branch = "    } elseif (-not $verificationSucceeded) {"

        proof_after_success = text.replace(
            "    " + PROVENANCE_COMMANDS[0],
            "    # " + PROVENANCE_COMMANDS[0],
            1,
        ).replace(
            "    " + VERIFICATION_COMPLETE,
            "    "
            + VERIFICATION_COMPLETE
            + "\n    "
            + PROVENANCE_COMMANDS[0],
            1,
        )
        server_digest_throw_in_else_if = text.replace(
            server_digest_gate,
            '''    if ($serverDigestChecks -ne 4) {
    } elseif ($false) {
        throw "four server digest checks did not complete"
    }''',
            1,
        )
        mismatched_cleanup_data_flow = text.replace(
            "    " + VERIFICATION_COMPLETE,
            "    " + VERIFICATION_COMPLETE + "\n    $downloadPath = $tempRoot",
            1,
        ).replace(
            "        $relativeDownloadPath = "
            "[IO.Path]::GetRelativePath($tempRoot, $resolvedDownloadPath)",
            "        $relativeDownloadPath = [IO.Path]::GetRelativePath(\n"
            '            $tempRoot, [IO.Path]::Combine($tempRoot, "decoy")\n'
            "        )",
            1,
        )
        notes_gate = '''if ($releaseBodyLf -cne $expectedNotesLf) {
    throw "published notes differ from RELEASE_NOTES.md"
}'''
        self.assertEqual(text.count(notes_gate), 1)
        proof_after_success_flag = text.replace(notes_gate, "", 1).replace(
            "    " + VERIFICATION_COMPLETE,
            "    "
            + VERIFICATION_COMPLETE
            + "\n"
            + textwrap.indent(notes_gate, "    "),
            1,
        )
        dynamic_payload = '''$verificationSucceeded = $true
$ErrorActionPreference = "SilentlyContinue"
$PSNativeCommandUseErrorActionPreference = $false'''
        encoded_dynamic_payload = base64.b64encode(
            dynamic_payload.encode("utf-8")
        ).decode("ascii")
        dot_sourced_dynamic_writer = (
            ". ([ScriptBlock]::Create([Text.Encoding]::UTF8.GetString("
            f'[Convert]::FromBase64String("{encoded_dynamic_payload}")'
            ")))"
        )

        def character_built_name(value: str) -> str:
            codepoints = ",".join(str(ord(character)) for character in value)
            return f"(-join [char[]]({codepoints}))"

        writer_snippets = {
            "Set-Variable writer": (
                "Set-Variable -Name ('verification' + 'Succeeded') -Value $true"
            ),
            "Set-Variable alias writer": (
                "sv -Name verificationSucceeded -Value $true"
            ),
            "Get-Variable property writer": (
                "(Get-Variable -Name ('verification' + 'Succeeded')).Value "
                "= $true"
            ),
            "New-Variable writer": (
                "New-Variable -Name verificationSucceeded -Value $true -Force"
            ),
            "wildcard Set-Item writer": (
                "Set-Item -Path Variable:verificationSucceede? -Value $true"
            ),
            "wildcard Set-Content writer": (
                "Set-Content -Path Variable:verificationSucceede? -Value $true"
            ),
            "New-Item provider writer": (
                "$flagPath = 'Variable:verification' + 'Succeeded'\n"
                "    New-Item -Path $flagPath -Value $true -Force | Out-Null"
            ),
            "SessionState method writer": (
                "$ExecutionContext.SessionState.PSVariable.Set("
                "'verification' + 'Succeeded', $true)"
            ),
            "encoded dot-sourced writer": dot_sourced_dynamic_writer,
            "module-qualified character-built writer": (
                "Microsoft.PowerShell.Utility\\Set-Variable -Name "
                + character_built_name("verificationSucceeded")
                + " -Value $true"
            ),
            "character-built OutVariable writer": (
                "Write-Output $true -OutVariable "
                + character_built_name("verificationSucceeded")
                + " | Out-Null"
            ),
            "character-built redirection writer": (
                "$statePath = 'Variable:' + "
                + character_built_name("verificationSucceeded")
                + "\n    Write-Output $true > $statePath"
            ),
        }
        writer_mutations = {
            name: text.replace(
                download,
                "    " + snippet + "\n" + download,
                1,
            )
            for name, snippet in writer_snippets.items()
        }
        preference_writer_snippets = {
            "Set-Variable weakens error preference before verification": (
                "Set-Variable -Name ('ErrorAction' + 'Preference') "
                "-Value 'SilentlyContinue'"
            ),
            "Set-Item weakens native preference before verification": (
                "Set-Item -Path Variable:PSNativeCommandUseErrorActionPreference "
                "-Value $false"
            ),
            "computed provider path weakens error preference": (
                "$preferencePath = 'Variable:ErrorAction' + 'Preference'\n"
                "Set-Item -Path $preferencePath -Value 'SilentlyContinue'"
            ),
            "SessionState weakens error preference before verification": (
                "$ExecutionContext.SessionState.PSVariable.Set("
                "'ErrorAction' + 'Preference', 'SilentlyContinue')"
            ),
            "qualified Set-Variable weakens error preference": (
                "Microsoft.PowerShell.Utility\\Set-Variable -Name "
                + character_built_name("ErrorActionPreference")
                + " -Value 'SilentlyContinue'"
            ),
            "qualified New-Item weakens native preference": (
                "Microsoft.PowerShell.Management\\New-Item -Path "
                "('Variable:' + "
                + character_built_name(
                    "PSNativeCommandUseErrorActionPreference"
                )
                + ") -Value $false -Force | Out-Null"
            ),
            "character-built SessionState preference writer": (
                "$ExecutionContext.SessionState.PSVariable.Set("
                + character_built_name("ErrorActionPreference")
                + ", 'SilentlyContinue')"
            ),
            "qualified Remove-Item removes native preference": (
                "Microsoft.PowerShell.Management\\Remove-Item -LiteralPath "
                "('Variable:' + "
                + character_built_name(
                    "PSNativeCommandUseErrorActionPreference"
                )
                + ")"
            ),
            "qualified Copy-Item weakens native preference": (
                "Microsoft.PowerShell.Management\\Copy-Item -LiteralPath "
                "Variable:WhatIfPreference -Destination ('Variable:' + "
                + character_built_name(
                    "PSNativeCommandUseErrorActionPreference"
                )
                + ")"
            ),
            "SessionState removes native preference": (
                "$ExecutionContext.SessionState.PSVariable.Remove("
                + character_built_name(
                    "PSNativeCommandUseErrorActionPreference"
                )
                + ")"
            ),
        }
        preference_writer_mutations = {
            name: text.replace(
                VERIFICATION_NOT_COMPLETE,
                snippet + "\n" + VERIFICATION_NOT_COMPLETE,
                1,
            )
            for name, snippet in preference_writer_snippets.items()
        }
        for name, mutated in writer_mutations.items():
            fences = powershell_fence_bodies(mutated)
            with self.subTest(snapshot=name):
                with self.assertRaises(AssertionError):
                    assert_powershell_fence_snapshot(self, fences)

        before_download_snippets = {
            "braced early success assignment": (
                "$" + "{verificationSucceeded} = $true"
            ),
            "scoped early success assignment": (
                "$script:verificationSucceeded = $true"
            ),
            "verification returns before proofs": "return",
            "verification trap continues after proof failures": "trap { continue }",
            "global error preference is weakened": (
                '$global:ErrorActionPreference = "SilentlyContinue"'
            ),
            "script error preference is weakened": (
                '$script:ErrorActionPreference = "SilentlyContinue"'
            ),
            "global native preference is weakened": (
                "$global:PSNativeCommandUseErrorActionPreference = $false"
            ),
            "script native preference is weakened": (
                "$script:PSNativeCommandUseErrorActionPreference = $false"
            ),
        }
        before_download_mutations = {
            name: text.replace(
                download,
                "    " + snippet + "\n" + download,
                1,
            )
            for name, snippet in before_download_snippets.items()
        }
        conditional_mutations = {
            name: wrap_executable(text, snippet, "if ($false) {", "}")
            for name, snippet in {
                "provenance proof is conditional": (
                    "    " + PROVENANCE_COMMANDS[0]
                ),
                "server digest gate is conditional": server_digest_gate,
                "payload digest gate is conditional": payload_digest_gate,
                "cleanup temporary-root guard is conditional": (
                    cleanup_temp_root_guard
                ),
                "cleanup download guard is conditional": cleanup_download_guard,
            }.items()
        }
        short_circuit_mutations = {
            name: wrap_executable(text, snippet, "$false -and $(", ")")
            for name, snippet in {
                "provenance proof is short-circuited": (
                    "    " + PROVENANCE_COMMANDS[0]
                ),
                "cleanup deletion is short-circuited": cleanup_removal,
            }.items()
        }
        commented_throw_mutations = {
            name: text.replace(
                snippet,
                snippet.replace("throw ", "# throw ", 1),
                1,
            )
            for name, snippet in {
                "server digest failure is commented out": (
                    '        throw "four server digest checks did not complete"'
                ),
                "payload digest failure is commented out": (
                    '        throw "exactly three payload checksum bindings '
                    'were not proved"'
                ),
                "cleanup containment failure is commented out": (
                    '            throw "cleanup path is not a unique contained child"'
                ),
                "cleanup temporary-root failure is commented out": (
                    '            throw "system temporary directory became a reparse point"'
                ),
                "cleanup download failure is commented out": (
                    '            throw "cleanup path is a reparse point"'
                ),
            }.items()
        }

        mutations = {
            **writer_mutations,
            **preference_writer_mutations,
            **before_download_mutations,
            **conditional_mutations,
            **short_circuit_mutations,
            **commented_throw_mutations,
            "verification error preference is weakened": text.replace(
                "    " + RELEASE_VERIFICATION_COMMANDS[-1],
                '    $ErrorActionPreference = "SilentlyContinue"\n'
                + "    "
                + RELEASE_VERIFICATION_COMMANDS[-1],
                1,
            ),
            "provenance proof follows success with comment spoof": (
                proof_after_success
            ),
            "notes proof follows success": proof_after_success_flag,
            "server digest failure is in an unreachable elseif": (
                server_digest_throw_in_else_if
            ),
            "cleanup download guard is inverted": text.replace(
                cleanup_download_guard,
                '''        if (-not ($downloadItem.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            throw "cleanup path is a reparse point"
        }''',
                1,
            ),
            "cleanup download failure is in the else clause": text.replace(
                cleanup_download_guard,
                cleanup_download_guard_else,
                1,
            ),
            "cleanup download guard follows deletion": text.replace(
                cleanup_download_guard + "\n" + cleanup_removal,
                cleanup_removal + "\n" + cleanup_download_guard,
                1,
            ),
            "cleanup deletion is in an always-true elseif": text.replace(
                cleanup_removal,
                "        # deletion moved",
                1,
            ).replace(
                cleanup_failure_branch,
                "    } elseif ($true) {\n"
                + cleanup_removal
                + "\n"
                + cleanup_failure_branch,
                1,
            ),
            "cleanup deletion is duplicated in an always-true elseif": (
                text.replace(
                    cleanup_failure_branch,
                    "    } elseif ($true) {\n"
                    + cleanup_removal
                    + "\n"
                    + cleanup_failure_branch,
                    1,
                )
            ),
            "cleanup containment checks a decoy path": (
                mismatched_cleanup_data_flow
            ),
            "global cleanup path is substituted": text.replace(
                "    " + VERIFICATION_COMPLETE,
                "    "
                + VERIFICATION_COMPLETE
                + "\n    $global:downloadPath = $tempRoot",
                1,
            ),
            "script cleanup path is substituted": text.replace(
                "    " + VERIFICATION_COMPLETE,
                "    "
                + VERIFICATION_COMPLETE
                + "\n    $script:downloadPath = $tempRoot",
                1,
            ),
        }

        for name, mutated in mutations.items():
            with self.subTest(mutation=name):
                with self.assertRaises(AssertionError):
                    assert_evidence_retention_contract(self, mutated)

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

    def test_v015_evidence_rejects_completed_state_mutations(self) -> None:
        text = EVIDENCE.read_text(encoding="utf-8")
        self.assertIn(EVIDENCE_COMPLETED_STATE, text)
        mutations = {
            "mutable": ("as immutable", "as mutable"),
            "draft": ("non-draft", "draft"),
            "prerelease": ("non-prerelease", "prerelease"),
            "not latest": ("the latest release", "not the latest release"),
        }
        for name, (old, new) in mutations.items():
            with self.subTest(mutation=name):
                mutated = text.replace(old, new, 1)
                with self.assertRaises(AssertionError):
                    assert_evidence_contract(self, mutated)

    @unittest.skipUnless(POWERSHELL, "PowerShell 7 is required to parse release commands")
    def test_every_powershell_fence_parses(self) -> None:
        text = RUNBOOK.read_text(encoding="utf-8")
        fences = powershell_fence_bodies(text)
        self.assertEqual(len(fences), EXPECTED_POWERSHELL_FENCES)
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
