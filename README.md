# Hardhat Ledger

[![Verify](https://github.com/ryanduguid/hardhat-ledger/actions/workflows/verify.yml/badge.svg)](https://github.com/ryanduguid/hardhat-ledger/actions/workflows/verify.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-4F485E.svg?labelColor=04001F)](LICENSE)

Claude Code skills for Australian subcontractor accounting: progress claims,
retentions, work in progress and over/under-billing, contract cost tracking, and
the regimes a mining-services or earthmoving subcontractor lives with.

Compatibility: the Claude plugin remains `subcontractor-accounting-skills` in
the `ryanduguid-contracting` marketplace, and release asset filenames retain
that identifier.

Written independently, from scratch, in my own time and on my own equipment.
Each skill encodes the *workflow* - the steps, the tie-outs, the exceptions to
chase - rather than the technical content. Rates, thresholds and statutory
timeframes change, and they differ by state, so the skills send the agent to the
primary source instead of hardcoding figures that go stale.

## Who this is for

Accountants and finance staff working with Australian contracting businesses:
civil and earthmoving contractors, mining-services subcontractors, and trade
subcontractors claiming under a head contract. Assumes a job or tracking
dimension in the ledger; most skills work from standard CSV exports.

Two things these skills will not do. They do not decide whether a contract is
covered by a security of payment Act, and they do not conclude that a worker is
a contractor rather than an employee. Both are legal characterisations with real
consequences, and both are flagged for a person.

## Install

### Claude Code plugin

This repo is also a Claude Code plugin marketplace, so the skills install
together and update with the repo:

```
/plugin marketplace add ryanduguid/hardhat-ledger
/plugin install subcontractor-accounting-skills@ryanduguid-contracting
```

### Any agent, via the skills CLI

```bash
npx skills add ryanduguid/hardhat-ledger
```

Add `-g` to install into `~/.claude/skills` instead, `-a claude-code` to target
one agent, and `-l` to list the skills without installing anything.

### By hand

```bash
git clone https://github.com/ryanduguid/hardhat-ledger
mkdir -p ~/.claude/skills
cp -r hardhat-ledger/.claude/skills/* ~/.claude/skills/
```

PowerShell:

```powershell
git clone https://github.com/ryanduguid/hardhat-ledger
New-Item -ItemType Directory -Force "$HOME/.claude/skills"
Copy-Item -Recurse hardhat-ledger/.claude/skills/* "$HOME/.claude/skills/"
```

## Skills

### The contracting core

| Skill | Use it for |
|---|---|
| `progress-claim-preparation` | Build or review a payment claim: measured work, variations, materials, retention withheld, GST, reference dates |
| `retention-schedule` | Retentions withheld and released by contract, defects liability expiry, trust obligations, tie-out to the ledger |
| `wip-over-under-billing` | Contract assets and liabilities under AASB 15: cost to complete, progress measurement, over and under-billing |
| `contract-cost-tracking` | Job costing: committed against actual cost, labour and plant allocation, margin and budget variance |

### Mining services and earthmoving

| Skill | Use it for |
|---|---|
| `fuel-tax-credits` | FTC claims: eligible fuel, on-road against off-road against auxiliary use, apportionment, evidence, amendment window |
| `coal-lsl-levy` | Coal LSL: eligible employees, the levy return, reimbursement claims, reconciliation to payroll |
| `payroll-tax-contractors` | Relevant contract provisions, the exemptions, grouping, labour hire, and contracts that include plant |
| `plant-and-equipment-costing` | Per-machine cost and utilisation, wet against dry hire, depreciation, finance treatment |

### Paying subcontractors, and shared reference

| Skill | Use it for |
|---|---|
| `contractor-super-tpar` | Super guarantee for contractors under the extended definition, TPAR, no-ABN withholding |
| `contracting-exports` | The exports these workflows need and their parsing quirks. Reference skill for the others |

The skills cross-reference each other, so installing the full set works best.

## Scope

These skills prepare and check. They do not serve a payment claim, lodge a
return, or sign anything. Contract interpretation, eligibility conclusions and
professional judgement stay with a person.

Nothing here is tax, accounting or legal advice.

## Source assurance

The skills use current primary legislation and authoritative decisions as the
controlling sources, with regulator pages as secondary operational guidance.
Where those sources conflict, the skill records the discrepancy and sends the
coverage or action decision to a qualified person instead of resolving it
autonomously.

The focused NSW construction, retention-trust and contractor-super/TPAR review
is recorded in
[docs/source-review-2026-08-15.md](docs/source-review-2026-08-15.md).
Every source must still be checked for amendments and current status when a
skill is used.

## Releases and provenance

Starting with the planned `v0.1.1` process, new releases package all 10
discoverable skills and the marketplace metadata as deterministic UTC/LF source
archives. Each such release includes SHA-256 checksums, an SPDX 2.3 SBOM, and
GitHub build and SBOM attestations. The marketplace deliberately has no pinned
version that could make discovery stale.

These remain review-schedule skills, not SG or TPAR calculators or final tax,
accounting or legal advice. Use still requires current-source checks and
qualified human review. See [RELEASING.md](RELEASING.md) for the operator gate
and verification procedure, and
[the v0.1.1 notes](docs/releases/v0.1.1.md) for the release boundary.

## Verification

Python 3.10 or newer. The tests need the packages pinned in
[requirements-test.txt](requirements-test.txt).

```bash
python -m pip install --disable-pip-version-check --no-deps --requirement requirements-test.txt
python -m unittest discover -s tests -v
python scripts/validate_validation.py
```

The fabricated cards in `validation/` and the shared rule in
`.claude/rules/accounting-safety.md` are the australian-accounting-skills-style gates
for this pack. See [DISCLAIMER.md](DISCLAIMER.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). For a potential security vulnerability,
follow [SECURITY.md](SECURITY.md).
