# v0.1.4

`v0.1.4` repairs cross-runtime packaging and makes the safety boundary portable when a skill is installed by itself. It retains the `subcontractor-accounting-skills` plugin name and all ten skill names.

## Changes since v0.1.3

- use one canonical nested plugin payload for Claude and Codex;
- point both marketplace listings to that payload and give the Claude manifest sole ownership of its skill components;
- remove unsupported Codex manifest fields and the incorrect privacy-policy link to `SECURITY.md`;
- embed current-source, client-data, secure-output, consequential-action and professional-judgement controls in every skill;
- remove unsafe or dangling instructions for Coal LSL, payroll-tax output, BAS hand-off and the WIP schedule engine; and
- delegate releases to a full-commit-pinned shared policy that isolates consumer tests from release authority.

## Included skills

The source archives and marketplace metadata contain all 10 discoverable skills:

- `coal-lsl-levy`
- `contract-cost-tracking`
- `contracting-exports`
- `contractor-super-tpar`
- `fuel-tax-credits`
- `payroll-tax-contractors`
- `plant-and-equipment-costing`
- `progress-claim-preparation`
- `retention-schedule`
- `wip-over-under-billing`

The marketplace intentionally has no pinned plugin version, so installation and
updates follow the selected repository revision instead of stale metadata.

## Scope and review boundary

These are review-schedule skills. They help collect evidence, structure checks,
record exceptions and prepare work for review. Every use requires a fresh check
of the current primary sources and qualified human review, including registered
tax-agent, accounting or legal review where the matter requires it.

In particular, `contractor-super-tpar` is **not an SG calculator or a TPAR
calculator**. No skill gives final tax, superannuation, payroll, accounting or
legal advice, decides employee or statutory coverage, calculates a final SGC or
reporting obligation, lodges a report, serves a claim, moves trust money or
authorises a payment.

## Integrity material

The release contains deterministic source archives whose text uses LF line
endings and whose timestamps derive from the tagged commit in UTC, plus:

- `SHA256SUMS` for both archives and the SBOM;
- an SPDX 2.3 source SBOM;
- GitHub build-provenance attestations for every release asset; and
- GitHub SPDX SBOM attestations for both source archives.

Follow [the release procedure](RELEASING.md) to verify the checksums,
attestations, exact tag target and immutable-release status.

The repository remains supported in this release. A gated transition to a broader Australian accounting skill pack is documented in [the consolidation plan](docs/consolidation-transition.md).
