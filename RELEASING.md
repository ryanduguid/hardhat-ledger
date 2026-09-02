# Release procedure

## Published v0.1.5 baseline

The immutable `v0.1.5` release is the completed recovery baseline:

- Hardhat commit: `0cd5478c0aa412813cd1b0a182f365250d823c93`
- Annotated tag object: `b690d7e0a155e0574840b47e977a70855a775a89`
- Policy commit: `f180faa567e95669224211d0282b3b437fe79ea9`
- Release run: `32865033315`

The release passed the dependency-aware unit, fabricated-validation and Skills
CLI gates. Its exact notes and four-asset inventory, local and server digests,
three payload checksum bindings, four provenance attestations, two SPDX v2.3
attestations, release verification and all four asset verifications passed.
The annotated tag and live `main` both resolved to the recorded Hardhat commit.

`v0.1.5` must never be created, moved, rerun or replaced. Do not edit its tag,
release body or assets. A later correction requires a new reviewed version.
The frozen `v0.1.0` tag and the protected, unpublished `v0.1.4` tag are also
ineligible release candidates.

## Future release procedure

Run every block below in one PowerShell 7.4 or newer session on a clean checkout of remote `main`. Blocks 2 to 5 rely on variables and error preferences set in block 1, and the local gates in block 1 also need Python with requirements-test.txt installed and Node.js (`npx`) with network access for the Skills CLI check. Do not
build or upload release assets locally. The caller's single privileged job
must delegate to the full-commit-pinned `release-skills.yml`; read-only local
and shared verification must complete before the tag is approved.

### 1. Bind and verify the release candidate

Replace only the reviewed new version and the literal separately approved
Hardhat commit. The first block rejects every protected historical version,
binds local and API `main`, checks both policy pins, requires the exact four
successful checks, runs the local gates and proves that neither the candidate
tag nor release exists.

```powershell
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
if ($PSVersionTable.PSVersion -lt [version]"7.4") {
    throw "PowerShell 7.4 or newer is required"
}
$repo = "ryanduguid/hardhat-ledger"
$releaseTag = "v0.1.6" # Replace with the reviewed new version.
$expectedPolicySha = "3ff09b654a17b9a3b55548e25e6108ee582b00c4"
$protectedTags = @("v0.1.0", "v0.1.4", "v0.1.5")
if ($releaseTag -notmatch '^v[0-9]+\.[0-9]+\.[0-9]+$' -or $protectedTags -ccontains $releaseTag) {
    throw "releaseTag must be a new semantic version"
}
git fetch origin main --tags

$immutableReleaseState = gh api `
    -H "X-GitHub-Api-Version: 2026-03-10" `
    "repos/$repo/immutable-releases" |
    ConvertFrom-Json
if (-not $immutableReleaseState.enabled) {
    throw "immutable releases are not enabled"
}

$approvedSha = "REPLACE_WITH_THE_SEPARATELY_APPROVED_40_CHARACTER_COMMIT_SHA"
if ($approvedSha -notmatch '^[0-9a-f]{40}$') {
    throw "approvedSha must be the literal separately approved commit"
}
$originMainSha = git rev-parse origin/main
$apiMainSha = gh api "repos/$repo/git/ref/heads/main" --jq '.object.sha'
$localHeadSha = git rev-parse HEAD
if ($originMainSha -cne $approvedSha -or $apiMainSha -cne $approvedSha) {
    throw "remote main does not equal the approved commit"
}
if ($localHeadSha -cne $approvedSha) {
    throw "local HEAD does not equal the approved commit"
}
if (git status --porcelain) {
    throw "the release checkout is not clean"
}

$releaseWorkflow = (git show "${approvedSha}:.github/workflows/release.yml") -join "`n"
$verifyWorkflow = (git show "${approvedSha}:.github/workflows/verify.yml") -join "`n"
$releasePolicyPins = [regex]::Matches(
    $releaseWorkflow,
    'release-skills\.yml@([0-9a-f]{40})'
)
$verifyPolicyPins = [regex]::Matches(
    $verifyWorkflow,
    'verify-skills\.yml@([0-9a-f]{40})'
)
if ($releasePolicyPins.Count -ne 1 -or $verifyPolicyPins.Count -ne 1) {
    throw "the workflow policy pins are not unique"
}
if (
    $releasePolicyPins[0].Groups[1].Value -cne $expectedPolicySha -or
    $verifyPolicyPins[0].Groups[1].Value -cne $expectedPolicySha
) {
    throw "the workflow policy pins do not equal the approved policy commit"
}

$requiredChecks = @(
    "verify",
    "shared conformance / verify skill-pack consumer",
    "Analyze (actions)",
    "Analyze (python)"
)
$checkRuns = gh api "repos/$repo/commits/$approvedSha/check-runs?per_page=100" |
    ConvertFrom-Json
foreach ($requiredCheck in $requiredChecks) {
    $matchingChecks = @($checkRuns.check_runs | Where-Object name -CEQ $requiredCheck)
    if (
        $matchingChecks.Count -ne 1 -or
        $matchingChecks[0].status -cne "completed" -or
        $matchingChecks[0].conclusion -cne "success"
    ) {
        throw "required check is not uniquely successful: $requiredCheck"
    }
}

python -m pip install --isolated --disable-pip-version-check --no-input --no-deps --requirement requirements-test.txt
python -B -m unittest discover -s tests -v
python scripts/validate_validation.py
python tests/verify_skills_cli.py

$candidateTag = git ls-remote --tags origin "refs/tags/$releaseTag"
if ($candidateTag) {
    throw "candidate tag already exists"
}
$nativeErrorPreference = $PSNativeCommandUseErrorActionPreference
try {
    $PSNativeCommandUseErrorActionPreference = $false
    $candidateReleaseError = gh api "repos/$repo/releases/tags/$releaseTag" 2>&1
    $candidateReleaseExit = $LASTEXITCODE
} finally {
    $PSNativeCommandUseErrorActionPreference = $nativeErrorPreference
}
if ($candidateReleaseExit -eq 0 -or "$candidateReleaseError" -notmatch 'HTTP 404') {
    throw "candidate release absence was not proved"
}
```

### 2. Obtain approval and create one annotated tag

A different human must inspect and approve the literal `$approvedSha` from the
first block after all gates pass. Record that approval outside the shell. Then
re-enter the approved value and create one annotated tag without force. If the
workflow fails, preserve its evidence and request a new decision. Do not move
the tag, rerun publication or upload assets manually.

```powershell
$confirmedApprovedSha = Read-Host "Re-enter the separately approved full commit SHA"
if ($confirmedApprovedSha -cne $approvedSha) {
    throw "the separate approval does not match approvedSha"
}

git fetch origin main --tags
$postApprovalImmutableReleaseState = gh api `
    -H "X-GitHub-Api-Version: 2026-03-10" `
    "repos/$repo/immutable-releases" |
    ConvertFrom-Json
if (-not $postApprovalImmutableReleaseState.enabled) {
    throw "immutable releases were disabled after approval"
}
$postApprovalOriginMainSha = git rev-parse origin/main
$postApprovalApiMainSha = gh api "repos/$repo/git/ref/heads/main" --jq '.object.sha'
$postApprovalHeadSha = git rev-parse HEAD
if (
    $postApprovalOriginMainSha -cne $approvedSha -or
    $postApprovalApiMainSha -cne $approvedSha
) {
    throw "remote main changed after approval"
}
if ($postApprovalHeadSha -cne $approvedSha) {
    throw "local HEAD changed after approval"
}
$postApprovalStatus = git status --porcelain
if ($postApprovalStatus) {
    throw "the release checkout changed after approval"
}
$postApprovalTag = git ls-remote --tags origin "refs/tags/$releaseTag"
if ($postApprovalTag) {
    throw "candidate tag appeared after approval"
}
$nativeErrorPreference = $PSNativeCommandUseErrorActionPreference
try {
    $PSNativeCommandUseErrorActionPreference = $false
    $postApprovalReleaseError = gh api "repos/$repo/releases/tags/$releaseTag" 2>&1
    $postApprovalReleaseExit = $LASTEXITCODE
} finally {
    $PSNativeCommandUseErrorActionPreference = $nativeErrorPreference
}
if ($postApprovalReleaseExit -eq 0 -or "$postApprovalReleaseError" -notmatch 'HTTP 404') {
    throw "post-approval release absence was not proved"
}

git tag -a $releaseTag $approvedSha -m $releaseTag
if ((git cat-file -t "refs/tags/$releaseTag") -cne "tag") {
    throw "release tag is not annotated"
}
$localTagCommitSha = git rev-parse "refs/tags/$releaseTag`^{commit}"
if ($localTagCommitSha -cne $approvedSha) {
    throw "release tag does not target the approved commit"
}
git push origin "refs/tags/$releaseTag"
```

### 3. Prove the published state and asset inventory

Wait for the release workflow to finish. Query only supported `gh release
view` fields, prove the REST latest identity and compare the published notes
and case-sensitive asset names with the committed contract.

```powershell
$release = gh release view $releaseTag --repo $repo --json body,databaseId,isDraft,isImmutable,isPrerelease,tagName,assets | ConvertFrom-Json
$latest = gh api "repos/$repo/releases/latest" | ConvertFrom-Json
if ($release.isDraft -or $release.isPrerelease -or -not $release.isImmutable) {
    throw "release state is not final and immutable"
}
if ([int64]$release.databaseId -ne [int64]$latest.id -or $release.tagName -cne $latest.tag_name) {
    throw "release is not the latest published release"
}
function ConvertTo-Lf([string]$Text) {
    return $Text.Replace("`r`n", "`n")
}
$expectedNotes = Get-Content -LiteralPath RELEASE_NOTES.md -Raw
$releaseBodyLf = ConvertTo-Lf $release.body
$expectedNotesLf = ConvertTo-Lf $expectedNotes
if ($releaseBodyLf -cne $expectedNotesLf) {
    throw "published notes differ from RELEASE_NOTES.md"
}

$releaseVersion = $releaseTag.Substring(1)
$checksumAsset = "SHA256SUMS"
$spdxAsset = "subcontractor-accounting-skills-$releaseVersion.spdx.json"
$tarAsset = "subcontractor-accounting-skills-$releaseVersion.tar.gz"
$zipAsset = "subcontractor-accounting-skills-$releaseVersion.zip"
$expectedAssets = @($checksumAsset, $spdxAsset, $tarAsset, $zipAsset)
$actualAssets = @($release.assets | ForEach-Object name)
if ($actualAssets.Count -ne 4) {
    throw "release does not contain exactly four assets"
}
$assetDifference = Compare-Object `
    ($actualAssets | Sort-Object -CaseSensitive) `
    ($expectedAssets | Sort-Object -CaseSensitive) `
    -CaseSensitive
if ($assetDifference) {
    throw "release asset inventory differs"
}
```

### 4. Download, verify and clean up safely

Create a unique child of the system temporary directory. The block proves
containment and rejects reparse points both before verification and again in
`finally` immediately before deletion. Any unexpected path state stops cleanup
and leaves the evidence for inspection.

```powershell
$tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd(
    [IO.Path]::DirectorySeparatorChar,
    [IO.Path]::AltDirectorySeparatorChar
)
$tempRootItem = Get-Item -LiteralPath $tempRoot -Force
if ($tempRootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw "system temporary directory is a reparse point"
}
$downloadPath = Join-Path `
    -Path $tempRoot `
    -ChildPath ("hardhat-ledger-release-" + [guid]::NewGuid().ToString("N"))
$resolvedDownloadPath = [IO.Path]::GetFullPath($downloadPath)
$relativeDownloadPath = [IO.Path]::GetRelativePath($tempRoot, $resolvedDownloadPath)
if (
    [IO.Path]::IsPathRooted($relativeDownloadPath) -or
    $relativeDownloadPath -eq "." -or
    $relativeDownloadPath -eq ".." -or
    $relativeDownloadPath.StartsWith("..$([IO.Path]::DirectorySeparatorChar)") -or
    $relativeDownloadPath.StartsWith("..$([IO.Path]::AltDirectorySeparatorChar)")
) {
    throw "download directory is not a unique contained child"
}
New-Item -ItemType Directory -Path $resolvedDownloadPath | Out-Null
$downloadItem = Get-Item -LiteralPath $resolvedDownloadPath -Force
if ($downloadItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw "download directory is a reparse point"
}

$verificationSucceeded = $false
try {
    gh release download $releaseTag --repo $repo --dir $resolvedDownloadPath
    $checksumPath = Join-Path $resolvedDownloadPath $checksumAsset
    $spdxPath = Join-Path $resolvedDownloadPath $spdxAsset
    $tarPath = Join-Path $resolvedDownloadPath $tarAsset
    $zipPath = Join-Path $resolvedDownloadPath $zipAsset

    $serverDigestChecks = 0
    foreach ($assetName in $expectedAssets) {
        $apiAssets = @($release.assets | Where-Object name -CEQ $assetName)
        if ($apiAssets.Count -ne 1) {
            throw "release does not contain one API asset named $assetName"
        }
        $assetPath = Join-Path $resolvedDownloadPath $assetName
        if (-not (Test-Path -LiteralPath $assetPath -PathType Leaf)) {
            throw "downloaded asset is missing: $assetName"
        }
        $localDigest = (Get-FileHash -LiteralPath $assetPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if ($apiAssets[0].digest -cne "sha256:$localDigest") {
            throw "server digest differs for $assetName"
        }
        $serverDigestChecks++
    }
    if ($serverDigestChecks -ne 4) {
        throw "four server digest checks did not complete"
    }

    $checksumLines = @(Get-Content -LiteralPath $checksumPath)
    $payloadChecksumChecks = 0
    foreach ($payloadName in @($spdxAsset, $tarAsset, $zipAsset)) {
        $payloadPath = Join-Path $resolvedDownloadPath $payloadName
        $payloadDigest = (Get-FileHash -LiteralPath $payloadPath -Algorithm SHA256).Hash.ToLowerInvariant()
        if (-not ($checksumLines -ccontains "$payloadDigest  $payloadName")) {
            throw "SHA256SUMS does not bind $payloadName"
        }
        $payloadChecksumChecks++
    }
    if ($checksumLines.Count -ne 3 -or $payloadChecksumChecks -ne 3) {
        throw "exactly three payload checksum bindings were not proved"
    }

    gh attestation verify $checksumPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha
    gh attestation verify $spdxPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha
    gh attestation verify $tarPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha
    gh attestation verify $zipPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha
    gh attestation verify $tarPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha --predicate-type "https://spdx.dev/Document/v2.3"
    gh attestation verify $zipPath --repo $repo --source-digest $approvedSha --source-ref "refs/tags/$releaseTag" --signer-workflow "ryanduguid/release-policy/.github/workflows/publish-archives.yml" --signer-digest $expectedPolicySha --predicate-type "https://spdx.dev/Document/v2.3"
    gh release verify $releaseTag --repo $repo
    gh release verify-asset $releaseTag $checksumPath --repo $repo
    gh release verify-asset $releaseTag $spdxPath --repo $repo
    gh release verify-asset $releaseTag $tarPath --repo $repo
    gh release verify-asset $releaseTag $zipPath --repo $repo
    $verificationSucceeded = $true
} finally {
    if ($verificationSucceeded -and (Test-Path -LiteralPath $downloadPath)) {
        $tempRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd(
            [IO.Path]::DirectorySeparatorChar,
            [IO.Path]::AltDirectorySeparatorChar
        )
        $resolvedDownloadPath = [IO.Path]::GetFullPath($downloadPath)
        $relativeDownloadPath = [IO.Path]::GetRelativePath($tempRoot, $resolvedDownloadPath)
        if (
            [IO.Path]::IsPathRooted($relativeDownloadPath) -or
            $relativeDownloadPath -eq "." -or
            $relativeDownloadPath -eq ".." -or
            $relativeDownloadPath.StartsWith("..$([IO.Path]::DirectorySeparatorChar)") -or
            $relativeDownloadPath.StartsWith("..$([IO.Path]::AltDirectorySeparatorChar)")
        ) {
            throw "cleanup path is not a unique contained child"
        }
        $tempRootItem = Get-Item -LiteralPath $tempRoot -Force
        if ($tempRootItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "system temporary directory became a reparse point"
        }
        $downloadItem = Get-Item -LiteralPath $resolvedDownloadPath -Force
        if ($downloadItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "cleanup path is a reparse point"
        }
        Remove-Item -LiteralPath $resolvedDownloadPath -Force -Recurse
    } elseif (-not $verificationSucceeded) {
        try {
            [Console]::Error.WriteLine(
                "release verification failed; evidence retained at literal path: $resolvedDownloadPath"
            )
        } catch {
            # Do not mask the original verification failure.
        }
    }
}
```

### 5. Re-prove live identities and protected evidence

Finish with live API state, not values retained from publication. The new tag
must remain annotated at the approved commit, current `main` must still equal
that commit, and protected `v0.1.4` must remain unchanged and unpublished.

```powershell
$tagRef = gh api "repos/$repo/git/ref/tags/$releaseTag" | ConvertFrom-Json
if ($tagRef.object.type -cne "tag") { throw "release tag is not annotated" }
$tagObjectSha = $tagRef.object.sha
$tagObject = gh api "repos/$repo/git/tags/$tagObjectSha" | ConvertFrom-Json
if ($tagObject.object.type -cne "commit") { throw "annotated tag does not target a commit" }
$tagCommitSha = $tagObject.object.sha
$remoteMainSha = gh api "repos/$repo/git/ref/heads/main" --jq '.object.sha'
if ($tagCommitSha -cne $approvedSha) { throw "release tag no longer targets the approved commit" }
if ($remoteMainSha -cne $approvedSha) { throw "remote main no longer equals the approved release commit" }

$protectedTagRef = gh api "repos/$repo/git/ref/tags/v0.1.4" | ConvertFrom-Json
if ($protectedTagRef.object.type -cne "tag") { throw "protected v0.1.4 tag is not annotated" }
$protectedTagObjectSha = $protectedTagRef.object.sha
$protectedTagObject = gh api "repos/$repo/git/tags/$protectedTagObjectSha" | ConvertFrom-Json
if ($protectedTagObject.object.type -cne "commit") { throw "protected v0.1.4 tag does not target a commit" }
$protectedV014Commit = $protectedTagObject.object.sha
if ($protectedV014Commit -cne "2f29bb51957888b1f427be44a7a0866ed4f4f5e5") {
    throw "protected v0.1.4 commit changed"
}
$nativeErrorPreference = $PSNativeCommandUseErrorActionPreference
try {
    $PSNativeCommandUseErrorActionPreference = $false
    $protectedReleaseError = gh api "repos/$repo/releases/tags/v0.1.4" 2>&1
    $protectedReleaseExit = $LASTEXITCODE
} finally {
    $PSNativeCommandUseErrorActionPreference = $nativeErrorPreference
}
if ($protectedReleaseExit -eq 0 -or "$protectedReleaseError" -notmatch 'HTTP 404') {
    throw "protected v0.1.4 release absence was not proved"
}
```

If any proof fails, preserve the available evidence and stop. Do not alter an
immutable release or any protected historical tag.
