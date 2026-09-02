# Hardhat Ledger

```
+----------------------------------------------------------------------+
|                            hardhat-ledger                            |
+----------------------------------------------------------------------+
|        Cross-runtime skills for AU subcontractor ledgers             |
+----------------------------------+-----------------------------------+
| DR  what it gives you            | CR  what it needs                 |
+----------------------------------+-----------------------------------+
| progress claim schedules         | a job or tracking dimension       |
| retention ledger tracking        | standard CSV ledger exports       |
| flags legal calls for review     | -                                 |
+----------------------------------+-----------------------------------+
```

[![Verify](https://github.com/ryanduguid/hardhat-ledger/actions/workflows/verify.yml/badge.svg)](https://github.com/ryanduguid/hardhat-ledger/actions/workflows/verify.yml) [![License: MIT](https://img.shields.io/badge/License-MIT-4F485E.svg?labelColor=04001F)](LICENSE)

> [!WARNING]
> Hardhat Ledger is deprecated. Use
> [Australian Accounting Skills v0.2.0](https://github.com/ryanduguid/australian-accounting-skills/releases/tag/v0.2.0)
> for maintained installations. That release includes these ten contracting
> skills and nine Australian public-practice skills.

Claude Code skills for Australian subcontractor accounting: progress claims,
retentions, work in progress and over/under-billing, contract cost tracking, and
the regimes a mining-services or earthmoving subcontractor lives with.

The v0.1.6 compatibility release keeps the `subcontractor-accounting-skills`
plugin ID, the `ryanduguid-contracting` marketplace, all ten skill names and
the existing release asset name. It changes migration guidance and release
policy pins without changing a skill.

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

## Migrate to Australian Accounting Skills

Remove or disable `subcontractor-accounting-skills@ryanduguid-contracting`
before you install the replacement. Both packs contain the same ten contracting
skill names. Never enable both packs at once.

### Claude Code plugin

```
/plugin marketplace add ryanduguid/australian-accounting-skills
/plugin install australian-accounting-skills@ryanduguid
```

### Codex plugin

```bash
codex plugin marketplace add ryanduguid/australian-accounting-skills
codex plugin add australian-accounting-skills@ryanduguid
```

### Any agent, via the skills CLI

```bash
npx skills add ryanduguid/australian-accounting-skills
```

Add `-g` to install into `~/.claude/skills` instead, `-a claude-code` to target
one agent, and `-l` to list the skills without installing anything.

### By hand

```bash
git clone --branch v0.2.0 --depth 1 https://github.com/ryanduguid/australian-accounting-skills
mkdir -p ~/.claude/skills
cp -r australian-accounting-skills/.claude/skills/* ~/.claude/skills/
```

PowerShell:

```powershell
git clone --branch v0.2.0 --depth 1 https://github.com/ryanduguid/australian-accounting-skills
New-Item -ItemType Directory -Force "$HOME/.claude/skills"
Copy-Item -Recurse australian-accounting-skills/.claude/skills/* "$HOME/.claude/skills/"
```

### Roll back to Hardhat Ledger v0.1.5

Use the immutable
[v0.1.5 release](https://github.com/ryanduguid/hardhat-ledger/releases/tag/v0.1.5)
if the replacement fails one of your workflows. Disable Australian Accounting
Skills before restoring this pack. The repository and its release assets stay
available throughout the observation period.

## Skills

### The contracting core

| Skill | Use it for |
|---|---|
| `progress-claim-preparation` | Build or review a payment claim: measured work, variations, materials, retention withheld, GST, reference dates |
| `retention-schedule` | Retentions withheld and released by contract, defects liability expiry, trust obligations, tie-out to the ledger |
| `wip-over-under-billing` | Contract assets and liabilities under AASB 15. The skill is the workflow; [TheWIPTally](https://github.com/ryanduguid/TheWIPTally) does the arithmetic |
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

## Sibling command-line tool

`wip-over-under-billing` names [TheWIPTally](https://github.com/ryanduguid/TheWIPTally)
(`wip-tally schedule`) rather than asking the agent to invent cost-to-cost
arithmetic. The skill still owns unit of account, the over-time versus
point-in-time test, and engagement-lead conclusions. Review aid, not a
determination.

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

The repository's [GitHub Releases](https://github.com/ryanduguid/hardhat-ledger/releases) page is the canonical release history. A separate changelog is intentionally not maintained.

Releases package all 10 discoverable skills and the marketplace metadata as
deterministic UTC/LF source archives. Each release includes SHA-256 checksums,
an SPDX 2.3 SBOM, and GitHub build and SBOM attestations. The marketplace
deliberately has no pinned version that could make discovery stale. The tag
workflow delegates to a full-commit-pinned, dependency-aware shared skill-pack
verifier and release policy, so consumer tests do not run with release
authority and the privileged job starts from a fresh checkout.

These remain review-schedule skills rather than SG or TPAR calculators or final
tax, accounting or legal advice. Use requires current-source checks and
qualified human review. [RELEASING.md](RELEASING.md) defines the operator gate,
and [the v0.1.5 notes](docs/releases/v0.1.5.md) preserve the last compatible
rollback evidence.

Australian Accounting Skills v0.2.0 now owns maintained releases for all ten
skill names. The [consolidation transition](docs/consolidation-transition.md)
records the verified replacement, duplicate-name constraint, observation and
rollback conditions.

## Verification

Python 3.10 or newer, plus PowerShell 7.4 or newer (`pwsh`) for the
release-runbook tests. The tests need the packages pinned in
[requirements-test.txt](requirements-test.txt).

```bash
python -m pip install --disable-pip-version-check --no-deps --requirement requirements-test.txt
python -m unittest discover -s tests -v
python scripts/validate_validation.py
```

The nine fabricated cards in `validation/`, the portable boundary inside every
standalone skill and the shared rule in `.claude/rules/accounting-safety.md`
are the safety gates for this pack. See [DISCLAIMER.md](DISCLAIMER.md).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). For a potential security vulnerability,
follow [SECURITY.md](SECURITY.md).
