# Post-release hardening implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden the release caller contract and replace obsolete v0.1.5 creation guidance with tested post-release and future-release verification instructions.

**Architecture:** Keep GitHub release behaviour in the exact-pinned shared policy and make the Hardhat caller declarative. Treat the operator guide's PowerShell fences as executable artefacts: parse every fence and pressure-test the safety and identity controls that previously failed review.

**Tech Stack:** GitHub Actions YAML, Python 3.12 `unittest`, PyYAML 6.0.3, PowerShell 7, GitHub CLI.

**Spec:** `docs/superpowers/specs/2026-08-26-post-release-hardening-design.md`

## Global constraints

- Start from exact Hardhat Ledger commit `0cd5478c0aa412813cd1b0a182f365250d823c93` on branch `fix/post-release-hardening`.
- Keep both reusable workflow calls pinned to `f180faa567e95669224211d0282b3b437fe79ea9`.
- Keep `artifact-stem: subcontractor-accounting-skills` and `skills-verification-mode: subcontractor-accounting-v1` unchanged.
- Do not change `VERSION`, either concrete manifest, `RELEASE_NOTES.md`, any skill, any validation card or `.claude/rules/accounting-safety.md`.
- Do not change either protected tag or the immutable v0.1.5 release, assets, attestations or repository settings.
- Use Australian English and no em dashes in original prose.
- No push, pull request, merge, tag or release is authorised.

---

### Task 1: Close caller workflow activation gaps

**Files:**

- Modify: `.github/workflows/release.yml`
- Modify: `tests/test_release_workflow.py`

**Interfaces:**

- Consumes: the exact reusable release and verification adapters at policy commit `f180faa567e95669224211d0282b3b437fe79ea9`
- Produces: one release job and two verification jobs whose complete activation and execution contracts are enforced by parsed YAML tests

- [ ] **Step 1: Refactor the test assertions into one parsed contract helper**

In `tests/test_release_workflow.py`, load both workflows with
`yaml.BaseLoader` and add a helper that asserts these literal structures:

```python
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
```

Keep the existing exact policy pins, inputs and permissions. Replace the
partial local Verify checks with one literal equality assertion over all six
steps, including both action commit pins, `persist-credentials: "false"`,
Python `3.12` and the four exact commands.

- [ ] **Step 2: Add mutation tests before changing the workflow**

Add a table-driven test that deep-copies the parsed production workflows and
proves the helper rejects each mutation independently:

```python
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
```

For each mutation, use `with testcase.assertRaises(AssertionError)` around
`assert_workflow_contract`. The unmodified production structures must pass the
same helper.

- [ ] **Step 3: Run the focused tests and confirm RED**

Run:

```powershell
python -B -m unittest tests.test_release_workflow -v
```

Expected: the production contract fails because `.github/workflows/release.yml`
still contains the extra `refuse-frozen` job. The failure must name the job-set
mismatch, not a Python or YAML error.

- [ ] **Step 4: Remove only the redundant caller-owned guard**

Delete this block from `.github/workflows/release.yml`:

```yaml
  refuse-frozen:
    if: github.ref_name == 'v0.1.0'
    runs-on: ubuntu-latest
    steps:
      - name: v0.1.0 is frozen
        run: |
          echo "v0.1.0 is frozen and must never be rebuilt or replaced." >&2
          exit 1
```

Do not change the `release` job. The exact pinned `release-skills.yml` adapter
continues to own the frozen-tag refusal.

- [ ] **Step 5: Run focused and complete tests and confirm GREEN**

Run:

```powershell
python -B -m unittest tests.test_release_workflow -v
python -B -m unittest discover -s tests -v
git diff --check
```

Expected: all workflow tests pass, the complete suite passes with no warnings,
and `git diff --check` exits 0.

- [ ] **Step 6: Commit Task 1**

```powershell
git add .github/workflows/release.yml tests/test_release_workflow.py
git commit -m "test: close release workflow activation gaps"
```

---

### Task 2: Publish accurate release evidence and a fail-closed future procedure

**Files:**

- Create: `tests/test_release_runbook.py`
- Modify: `RELEASING.md`
- Modify: `docs/releases/v0.1.5.md`

**Interfaces:**

- Consumes: the one-job caller contract from Task 1 and the immutable v0.1.5 evidence at Hardhat commit `0cd5478c0aa412813cd1b0a182f365250d823c93`
- Produces: parseable PowerShell instructions for future releases and a historical v0.1.5 evidence record that never asks an operator to recreate the release

- [ ] **Step 1: Create the runbook contract test before changing documentation**

Create `tests/test_release_runbook.py` with a helper that reads
`RELEASING.md`, extracts every `powershell` fence and parses each fence through
PowerShell's language parser:

```python
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


def assert_runbook_contract(testcase: unittest.TestCase, text: str) -> None:
    testcase.assertIn("## Published v0.1.5 baseline", text)
    testcase.assertIn("## Future release procedure", text)
    testcase.assertNotIn("recovery version is `v0.1.5`", text)
    testcase.assertNotIn("isLatest", text)
    testcase.assertIn("body,databaseId,isDraft,isImmutable,isPrerelease,tagName,assets", text)
    testcase.assertIn("repos/$repo/releases/latest", text)
    testcase.assertIn("[guid]::NewGuid()", text)
    testcase.assertIn("[IO.FileAttributes]::ReparsePoint", text)
    testcase.assertIn("repos/$repo/git/ref/tags/$releaseTag", text)
    testcase.assertIn("repos/$repo/git/tags/$tagObjectSha", text)
    testcase.assertIn("$tagCommitSha -cne $approvedSha", text)
    testcase.assertIn("$remoteMainSha -cne $approvedSha", text)


class ReleaseRunbookTests(unittest.TestCase):
    def test_runbook_has_fail_closed_release_contract(self) -> None:
        assert_runbook_contract(self, RUNBOOK.read_text(encoding="utf-8"))

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
```

Extend `assert_runbook_contract` so it also verifies:

- `$PSNativeCommandUseErrorActionPreference = $true` precedes the first
  `git fetch` or `gh api`
- all expected HTTP 404 probes capture `$LASTEXITCODE`, require `HTTP 404` and
  restore native-command termination in `finally`
- candidate tags `v0.1.0`, `v0.1.4` and `v0.1.5` are rejected
- release state compares both `databaseId` and `tagName` with the latest API
  response
- cleanup occurs in `finally` and repeats the containment and reparse-point
  checks before `Remove-Item -LiteralPath`
- the exact four asset names, four provenance checks, two SPDX checks,
  `gh release verify` and four `gh release verify-asset` calls remain required

Add mutation cases that remove or replace one safety marker at a time and
assert that the helper rejects each altered document.

- [ ] **Step 2: Run the focused runbook tests and confirm RED**

Run:

```powershell
python -B -m unittest tests.test_release_runbook -v
```

Expected: the contract test fails because the current guide still describes
v0.1.5 as an unused recovery version and lacks the future-release, latest API,
fresh-directory and post-publication tag identity controls. PowerShell parsing
must not be the cause of the failure.

- [ ] **Step 3: Rewrite `RELEASING.md` around the published baseline**

Start with `## Published v0.1.5 baseline` and record the exact Hardhat commit,
tag object, policy commit, run number and passed acceptance categories. State
that `v0.1.5` must never be created, moved, rerun or replaced.

Add `## Future release procedure`. Its first operational fence starts exactly
with:

```powershell
$ErrorActionPreference = "Stop"
$PSNativeCommandUseErrorActionPreference = $true
$repo = "ryanduguid/hardhat-ledger"
$releaseTag = "v0.1.6" # Replace with the reviewed new version.
$expectedPolicySha = "f180faa567e95669224211d0282b3b437fe79ea9"
$protectedTags = @("v0.1.0", "v0.1.4", "v0.1.5")
if ($releaseTag -notmatch '^v[0-9]+\.[0-9]+\.[0-9]+$' -or $protectedTags -ccontains $releaseTag) {
    throw "releaseTag must be a new semantic version"
}
git fetch origin main --tags
```

Bind `$approvedSha`, API `main`, local `origin/main`, both workflow policy pins
and the exact successful check names before allowing tag creation. Wrap only
the expected release-absence API probe with temporary native-command error
suppression:

```powershell
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

Require a separate human approval for the literal `$approvedSha`, then create
one annotated tag without force.

- [ ] **Step 4: Add supported post-publication state and identity checks**

Query only supported `gh release view` fields and prove latest status with the
REST API:

```powershell
$release = gh release view $releaseTag --repo $repo --json body,databaseId,isDraft,isImmutable,isPrerelease,tagName,assets | ConvertFrom-Json
$latest = gh api "repos/$repo/releases/latest" | ConvertFrom-Json
if ($release.isDraft -or $release.isPrerelease -or -not $release.isImmutable) {
    throw "release state is not final and immutable"
}
if ([int64]$release.databaseId -ne [int64]$latest.id -or $release.tagName -cne $latest.tag_name) {
    throw "release is not the latest published release"
}
```

Create the download directory with `[guid]::NewGuid()`, resolve the system
temporary directory and child path, reject reparse points and use `try` and
`finally` so cleanup repeats the same checks. Inside `try`, verify exact notes,
the exact four assets, all four server digests, the three payload checksum
bindings, four provenance attestations, two SPDX attestations, the release and
each asset.

After publication, live-query the annotated tag object and current `main`:

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
```

Finish by re-proving the protected `v0.1.4` commit and HTTP 404 release
absence. Do not include `isLatest` anywhere.

- [ ] **Step 5: Convert `docs/releases/v0.1.5.md` to completed evidence**

Record these exact identities:

```text
Hardhat commit: 0cd5478c0aa412813cd1b0a182f365250d823c93
Annotated tag object: b690d7e0a155e0574840b47e977a70855a775a89
Policy commit: f180faa567e95669224211d0282b3b437fe79ea9
Release run: 32865033315
```

Record the verified asset digests:

```text
SHA256SUMS                                      a6c26561592fa3df5c2675bd3801ca3c7af2034ce4a47bd804af703f983e944c
subcontractor-accounting-skills-0.1.5.spdx.json 2abebc84ed705aecd81517f1c14226a76deb3cb4528f5c60f5fc3937e9d903cf
subcontractor-accounting-skills-0.1.5.tar.gz     5aaf15b93cb06fc67e39b1fcc270dca0a6d20e5cc85cadd597a46fc810962d13
subcontractor-accounting-skills-0.1.5.zip        231784a4decc64760318ba1033f6da03a8938dbda6142d4351f60f510b8e6419
```

State that four provenance attestations, two SPDX v2.3 attestations,
`gh release verify` and all four `verify-asset` checks passed. Preserve the
unchanged v0.1.4 and accounting-content boundaries.

- [ ] **Step 6: Run focused and complete verification and confirm GREEN**

Run:

```powershell
python -B -m unittest tests.test_release_runbook -v
python -B -m unittest discover -s tests -v
python scripts/validate_validation.py
python tests/verify_skills_cli.py
git diff --check
```

Then run a direct PowerShell parse over every fenced command and confirm there
are no parser errors. Compare the branch with the fixed base and require an
empty diff for these protected paths:

```powershell
git diff --exit-code 0cd5478c0aa412813cd1b0a182f365250d823c93 -- VERSION RELEASE_NOTES.md plugins/subcontractor-accounting-skills/.claude-plugin/plugin.json plugins/subcontractor-accounting-skills/.codex-plugin/plugin.json plugins/subcontractor-accounting-skills/skills validation/cases .claude/rules/accounting-safety.md
```

- [ ] **Step 7: Commit Task 2**

```powershell
git add RELEASING.md docs/releases/v0.1.5.md tests/test_release_runbook.py
git commit -m "docs: harden post-release verification"
```

---

## Final acceptance and review

After both task reviews pass, rerun every command in Task 2 Step 6 at exact
clean `HEAD`. Generate one whole-branch review package for
`0cd5478c0aa412813cd1b0a182f365250d823c93..HEAD` and obtain an independent
Standards and Spec review. Stop before any remote mutation and present the
literal reviewed head for a separate publication decision.
