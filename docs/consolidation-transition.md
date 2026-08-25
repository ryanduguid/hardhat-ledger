# Consolidation transition

This repository remains the compatible source for the ten published `subcontractor-accounting-skills` entrypoints through the `v0.1.5` recovery release. The proposed next home is a broader `ryanduguid/australian-accounting-skills` pack. That destination is a plan, not a current installation claim.

## Compatibility contract

The transition must preserve all ten skill names, their front matter, current-source checks, standalone safety boundary and human-review gates. Existing Claude marketplace, Codex marketplace and Skills CLI installs must keep working until the destination passes the same checks and has a published replacement release.

Installing both packs at once would create duplicate skill names. The migration documentation must therefore tell users to remove or disable this pack before enabling the replacement pack. Renaming the skills to avoid that collision would break existing prompts and automation and is out of scope.

## Phases and gates

1. **Repair here.** Publish `v0.1.5` only after the local manifest, Claude installation, Codex validation, Skills CLI discovery, unit-test and standalone-safety checks pass. Keep this repository active and do not mark it deprecated in the recovery release.
2. **Copy into the broader pack.** Bring the ten skill directories across without changing their names or weakening their boundaries. Record the source commit and compare a file inventory or content hashes so the destination can prove what changed during integration.
3. **Validate the destination.** Require exact discovery of all ten skills through the destination's supported Claude, Codex and Skills CLI paths. Re-run every fabricated card in `validation/`, including the standalone safety card, and review any destination-specific cross-references.
4. **Announce the replacement.** After the destination release is available and verified, prepare a separate deprecation release here. Change installation guidance to the replacement pack, explain the duplicate-name constraint and retain a rollback link to the last compatible release.
5. **Archive only by decision.** Archive this repository only after a documented observation period and explicit owner approval. Do not delete releases, move tags or remove the compatibility source.

## Rollback

If destination discovery, behaviour or documentation regresses, keep this repository unarchived and direct users back to the latest verified `subcontractor-accounting-skills` release. A failed consolidation must not force a skill rename or a tag rewrite.

## Completion evidence

The consolidation is complete only when the destination records:

- the source commit and exact ten-skill inventory;
- passing Claude install, Codex plugin validation and Skills CLI discovery;
- passing static tests and all fabricated validation cards;
- an independent review of client-data, consequential-action and professional-judgement boundaries;
- replacement and rollback instructions; and
- the owner's separate approval for this repository's deprecation or archival state.
