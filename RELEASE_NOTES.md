# v0.1.5

`v0.1.5` is a release-process recovery for the protected v0.1.4 tag. Release
run 32839062910 stopped in its read-only consumer-test job because the
source-archive adapter did not install the tracked PyYAML test dependency.
Publication never started, and no v0.1.4 release or assets exist.

## Changes since v0.1.4

- use the dedicated, full-commit-pinned skill-pack release adapter;
- run the same dependency-aware conformance path on pull requests, `main` and
  the release tag; and
- retain isolated consumer testing and a fresh privileged publication checkout.

No skill or accounting content changed. The plugin name, ten-skill inventory,
validation cards, accounting rules and professional-review boundary are
unchanged from protected tag commit `2f29bb51957888b1f427be44a7a0866ed4f4f5e5`.

## Release assets

```text
subcontractor-accounting-skills-0.1.5.zip
subcontractor-accounting-skills-0.1.5.tar.gz
subcontractor-accounting-skills-0.1.5.spdx.json
SHA256SUMS
```
