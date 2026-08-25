# Release procedure

This repository uses an operator-gated release process. `v0.1.0` is frozen,
and `v0.1.4` is an immutable failed tag. Never move, delete, recreate, rerun
or attach replacement assets to either tag. Release run 32839062910 stopped
before publication, so the recovery version is `v0.1.5`.

The caller uses the full-commit-pinned `release-skills.yml` adapter in
`ryanduguid/release-policy`. It performs dependency-aware conformance in a
read-only job, then `publish-archives.yml` performs attestation and publication
from a fresh checkout. Do not build, upload or publish assets by hand.

## 1. Verify the exact release commit

Merge the reviewed release pull request, then work from a clean checkout of
the remote default branch. Confirm that the proposed commit is exactly current
`main`, that Verify, shared conformance and CodeQL passed for that SHA, and that
both workflow calls are pinned to
`f180faa567e95669224211d0282b3b437fe79ea9`.

Run the local gates in this order:

```powershell
python -m pip install --isolated --disable-pip-version-check --no-input --no-deps --requirement requirements-test.txt
python -B -m unittest discover -s tests -v
python scripts/validate_validation.py
python tests/verify_skills_cli.py
```

Before a tag is considered, prove the failed-tag invariant and that the
recovery version is unused. Both release API calls below must return HTTP 404:

```powershell
git fetch origin main --tags
if ((git rev-parse 'v0.1.4^{commit}') -ne '2f29bb51957888b1f427be44a7a0866ed4f4f5e5') { throw 'v0.1.4 changed' }
gh api repos/ryanduguid/hardhat-ledger/releases/tags/v0.1.4
if ($LASTEXITCODE -eq 0) { throw 'v0.1.4 release exists' }
if (git ls-remote --tags origin refs/tags/v0.1.5) { throw 'v0.1.5 tag exists' }
gh api repos/ryanduguid/hardhat-ledger/releases/tags/v0.1.5
if ($LASTEXITCODE -eq 0) { throw 'v0.1.5 release exists' }
```

## 2. Enable and read back immutable releases

An authenticated owner or administrator must enable Immutable releases in
Settings before creating the tag, then read the setting back. The workflow has
release permissions, not repository-administration authority.

```powershell
gh api --method PUT -H "X-GitHub-Api-Version: 2026-03-10" repos/ryanduguid/hardhat-ledger/immutable-releases
gh api -H "X-GitHub-Api-Version: 2026-03-10" repos/ryanduguid/hardhat-ledger/immutable-releases --jq '{enabled, enforced_by_owner}'
```

Stop unless `enabled` is `true`.

## 3. Create one annotated tag at exact current main

Only after explicit approval for the exact merged SHA, create and push one
annotated `v0.1.5` tag:

```powershell
git fetch origin main --tags
$releaseSha = git rev-parse origin/main
$apiMainSha = gh api repos/ryanduguid/hardhat-ledger/git/ref/heads/main --jq '.object.sha'
if ($releaseSha -ne $apiMainSha) { throw 'origin/main does not match the GitHub API' }
git tag -a v0.1.5 $releaseSha -m 'v0.1.5'
if ((git cat-file -t refs/tags/v0.1.5) -ne 'tag') { throw 'v0.1.5 is not annotated' }
if ((git rev-parse 'refs/tags/v0.1.5^{commit}') -ne $releaseSha) { throw 'tag target mismatch' }
git push origin refs/tags/v0.1.5
```

Never force-push a release tag. If the release workflow fails, preserve its
candidate or draft evidence and seek a new decision rather than rerunning,
editing the tag or uploading assets.

## 4. Verify the published release

Confirm that `v0.1.5` is immutable, non-draft and latest; that its notes match
the committed `RELEASE_NOTES.md`; and that it has exactly these assets:

```text
SHA256SUMS
subcontractor-accounting-skills-0.1.5.spdx.json
subcontractor-accounting-skills-0.1.5.tar.gz
subcontractor-accounting-skills-0.1.5.zip
```

Download the assets, compare local and server SHA-256 digests with
`SHA256SUMS`, and verify all four provenance attestations and both archive SPDX
attestations. The signer must be
`ryanduguid/release-policy/.github/workflows/publish-archives.yml` at the exact
pinned policy SHA. Re-prove that `v0.1.4` still peels to
`2f29bb51957888b1f427be44a7a0866ed4f4f5e5` and has no release.

Do not replace an immutable release. Correct any later issue with a new
reviewed version.
