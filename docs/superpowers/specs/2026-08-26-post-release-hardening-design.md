# Post-release hardening design

Status: Approved by Ryan in chat on 26 August 2026.

## Context

Hardhat Ledger `v0.1.5` is already published and immutable. Pull request 24,
remote `main` and the peeled annotated tag all resolve to
`0cd5478c0aa412813cd1b0a182f365250d823c93`. The release workflow pins the
shared skill-pack policy at
`f180faa567e95669224211d0282b3b437fe79ea9`.

The published release passed its complete acceptance audit. Release run
32865033315 succeeded, the four release assets matched their declared and
server digests, four provenance attestations and two SPDX attestations
verified, and the release and each asset passed GitHub release verification.
Protected `v0.1.4` remains unpublished and peels to
`2f29bb51957888b1f427be44a7a0866ed4f4f5e5`.

No release repair is required. The remaining work is a separate follow-up on
the commit after `v0.1.5`.

## Goals

1. Keep the caller workflow as a thin, exact-pinned adapter to the shared
   release policy.
2. Make the workflow contract tests reject renamed guard jobs, skip
   conditions and failure masking.
3. Replace the pre-publication `v0.1.5` instructions with an accurate
   published baseline and a parameterised procedure for future versions.
4. Make the documented PowerShell commands fail closed, use fields supported
   by the installed GitHub CLI and re-prove release, tag and `main` identity
   after publication.
5. Record the completed `v0.1.5` acceptance evidence without changing the
   immutable release.

## Scope

The follow-up may change:

- `.github/workflows/release.yml`
- `tests/test_release_workflow.py`
- `tests/test_release_runbook.py`
- `RELEASING.md`
- `docs/releases/v0.1.5.md`
- this specification and its implementation plan

It must not change:

- `VERSION` or either concrete plugin manifest
- `RELEASE_NOTES.md`
- any skill, validation card or accounting-safety rule
- the shared policy SHA, release adapter, permissions or verification mode
- the `v0.1.4` or `v0.1.5` tags
- the `v0.1.5` release body, assets, attestations or repository settings

No branch push, pull request, merge, tag or release is part of this change.

## Workflow contract

`.github/workflows/release.yml` has exactly one job named `release`. The
full-commit-pinned `release-skills.yml` adapter owns the frozen `v0.1.0`
refusal, so the caller does not duplicate that guard.

The release job keeps exactly:

- permissions `attestations: write`, `contents: write` and `id-token: write`
- `uses: ryanduguid/release-policy/.github/workflows/release-skills.yml@f180faa567e95669224211d0282b3b437fe79ea9`
- inputs `artifact-stem: subcontractor-accounting-skills` and
  `skills-verification-mode: subcontractor-accounting-v1`

The release job and both jobs in `.github/workflows/verify.yml` must have no
job-level `if` or `continue-on-error`. Reusable workflow jobs must not gain
local steps, runners, environments, outputs or secrets. The existing local
Verify steps, action pins, Python version and commands remain exact.

Tests parse the YAML and pressure-test realistic mutations. They must reject:

- any extra or renamed release job
- a job-level condition on `release`, `verify` or `shared-conformance`
- `continue-on-error` on any of those jobs
- any change to the exact local Verify steps

## Operator guide

`RELEASING.md` first records `v0.1.5` as an immutable published baseline. It
then gives a future-release procedure using an explicit version variable. The
procedure must reject `v0.1.0`, `v0.1.4` and `v0.1.5` as candidate tags.

Every PowerShell fence must parse under PowerShell 7. The first operational
fence sets `$ErrorActionPreference = "Stop"` and
`$PSNativeCommandUseErrorActionPreference = $true` before its first native
command. Expected HTTP 404 checks may temporarily disable native-command
termination inside `try` and restore it in `finally`; no other failure is
accepted as proof of absence.

The procedure must:

- bind the candidate to exact remote `main` and the exact policy pin
- require successful Verify, shared conformance and CodeQL checks for the
  candidate commit
- read back immutable-release status before tag creation
- prove that the candidate tag and release do not already exist
- require a separate human approval for the literal candidate SHA before an
  annotated tag is created and pushed
- query release state using supported `gh release view` fields
- prove latest-release status by comparing the release database ID and tag to
  `repos/ryanduguid/hardhat-ledger/releases/latest`
- use a unique child of the resolved system temporary directory, reject a
  reparse point and validate the path again before cleanup
- verify exact notes, the exact four assets, all local and server digests,
  checksum-to-filename bindings, four provenance attestations, two SPDX
  attestations, the release and each asset
- live-query the annotated tag object and current `main` after publication,
  requiring both to equal the approved SHA
- re-prove the protected `v0.1.4` commit and absent release

The procedure must never recommend a rerun, tag rewrite, asset replacement or
manual upload as recovery for an immutable release.

## Release record

`docs/releases/v0.1.5.md` records the completed release, including:

- Hardhat commit, tag object, shared-policy commit and workflow run
- immutable, non-draft, non-prerelease and latest status at acceptance
- the four asset names and verified SHA-256 values
- four provenance and two SPDX attestation results
- release and per-asset verification results
- the unchanged `v0.1.4` and accounting-content boundaries

The record is historical evidence. It does not instruct an operator to create,
rerun or replace `v0.1.5`.

## Acceptance

Implementation uses test-driven development. New workflow and runbook tests
must fail for the expected missing contract before the corresponding files are
changed, then pass after the smallest implementation.

Final local acceptance requires:

```text
python -B -m unittest discover -s tests -v
python scripts/validate_validation.py
python tests/verify_skills_cli.py
git diff --check
```

Every PowerShell fence in `RELEASING.md` must parse under the installed
PowerShell. The complete branch diff against
`0cd5478c0aa412813cd1b0a182f365250d823c93` must be empty for all skills,
validation cards, accounting-safety rules, version files, manifests and
`RELEASE_NOTES.md`.
