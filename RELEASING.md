# Release procedure

This repository uses an operator-gated release process. `v0.1.0` is a frozen,
lightweight historical tag. Never move, delete, recreate or attach replacement
assets to it. Corrections start at `v0.1.1` or a later new version.

The release workflow intentionally does **not** call GitHub's repository
administration endpoint for immutable releases. Its `GITHUB_TOKEN` has release
permissions, not repository-administration authority. An owner or administrator
must enable immutability and read the setting back before creating the tag.
The `immutable-releases` endpoint is therefore an operator control, not a
workflow step.

## 1. Verify the exact release commit

Merge the reviewed release pull request, then work from a clean checkout of the
remote default branch. Confirm that the proposed commit is the exact current
`main` commit and that Verify and CodeQL/default scanning passed for that SHA.
Do not infer release readiness from pull-request checks on a different commit.

Run the local gates against that exact commit:

```powershell
python -m pip install --disable-pip-version-check --no-deps --requirement requirements-test.txt
python -m unittest discover -s tests -v
python tests/verify_skills_cli.py
python scripts/build_release.py --repository . --output-dir dist --version v0.1.1
Push-Location dist
Get-Content SHA256SUMS
Pop-Location
```

`dist` must be absent or empty before the build. Delete only this generated,
ignored directory after inspecting it; never use a broad cleanup command.

## 2. Enable and read back immutable releases

An authenticated repository owner or administrator must enable **Immutable
releases** in Settings > General > Releases, or make the equivalent API call:

```powershell
gh api --method PUT `
  -H "X-GitHub-Api-Version: 2026-03-10" `
  repos/ryanduguid/subcontractor-accounting-skills/immutable-releases
```

Read the setting back with the same administrator identity:

```powershell
gh api `
  -H "X-GitHub-Api-Version: 2026-03-10" `
  repos/ryanduguid/subcontractor-accounting-skills/immutable-releases `
  --jq '{enabled, enforced_by_owner}'
```

Stop unless `enabled` is `true`. This is a pre-tag operator gate. Do not assume
that a submitted setting change succeeded, and do not create the tag first. A
`404` readback means immutability is not enabled and is also a stop condition.
GitHub documents both the
[repository setting](https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/establish-provenance-and-integrity/prevent-release-changes)
and the
[administration API](https://docs.github.com/en/rest/repos/repos?apiVersion=2026-03-10#enable-immutable-releases).

## 3. Create one annotated tag at exact current main

Verify that neither the new tag nor a release with the same name already exists.
Resolve `origin/main` again immediately before tagging, then create an annotated
tag at that exact SHA. For `v0.1.1`:

```powershell
git fetch origin main --tags
$releaseSha = git rev-parse origin/main
$apiMainSha = gh api repos/ryanduguid/subcontractor-accounting-skills/git/ref/heads/main --jq '.object.sha'
if ($releaseSha -ne $apiMainSha) { throw "origin/main does not match the GitHub API" }
gh api repos/ryanduguid/subcontractor-accounting-skills/commits/$releaseSha/check-runs --jq '.check_runs[] | [.name, .status, .conclusion] | @tsv'
git tag -a v0.1.1 $releaseSha -m "v0.1.1"
git cat-file -t refs/tags/v0.1.1
$tagSha = git rev-parse 'refs/tags/v0.1.1^{commit}'
if ($tagSha -ne $releaseSha) { throw "annotated tag target does not match main" }
git push origin refs/tags/v0.1.1
```

`git cat-file` must return `tag`, and the peeled commit must equal both
`origin/main` and the API result. Every required check run in the listing must be
completed successfully for that exact SHA. Never force-push a release tag. The
tag push is the explicit operator authorisation for the workflow to build,
attest and publish the release.

## 4. Verify the published release

The workflow reruns the tests, builds deterministic UTC/LF ZIP and tar archives,
creates `SHA256SUMS` and an SPDX 2.3 SBOM, creates GitHub build and SBOM
attestations, uploads the exact four assets to a draft, verifies that draft, and
only then publishes it. With the operator precondition satisfied, GitHub locks
the tag and assets at publication.

Check all four assets, their checksums, the GitHub attestations and the immutable
flag:

```powershell
gh release view v0.1.1 --json tagName,isDraft,isImmutable,assets
gh release download v0.1.1 --dir dist-verify
Push-Location dist-verify
Get-FileHash -Algorithm SHA256 subcontractor-accounting-skills-v0.1.1.zip
Get-FileHash -Algorithm SHA256 subcontractor-accounting-skills-v0.1.1.tar.gz
Get-FileHash -Algorithm SHA256 subcontractor-accounting-skills-v0.1.1.spdx.json
Pop-Location
gh attestation verify dist-verify/subcontractor-accounting-skills-v0.1.1.zip --repo ryanduguid/subcontractor-accounting-skills
gh attestation verify dist-verify/subcontractor-accounting-skills-v0.1.1.tar.gz --repo ryanduguid/subcontractor-accounting-skills
gh attestation verify dist-verify/subcontractor-accounting-skills-v0.1.1.zip --repo ryanduguid/subcontractor-accounting-skills --predicate-type https://spdx.dev/Document/v2.3
gh release verify v0.1.1 --repo ryanduguid/subcontractor-accounting-skills
gh api -H "X-GitHub-Api-Version: 2026-03-10" repos/ryanduguid/subcontractor-accounting-skills/releases/tags/v0.1.1 --jq '{draft, immutable}'
```

Compare the three calculated hashes with `SHA256SUMS`. Stop and investigate any
mismatch, missing attestation, mutable release or unexpected asset. Do not
replace an immutable release; correct it with a new reviewed version.
