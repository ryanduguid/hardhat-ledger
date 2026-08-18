# Contributing

These skills describe how an agent should work through the accounting for an
Australian contracting business: progress claims, retentions, work in progress,
and the regimes that sit on top of them for a mining-services or earthmoving
subcontractor. They encode workflow and tie-out discipline, and they stop where
professional judgement starts. Nothing here is tax, accounting or legal advice.

## Data boundary

- Keep client data out of the repository. The `.gitignore` blocks `input/`,
  `output/`, `clients/`, `exports/`, `contracts/`, `claims/` and the common
  export extensions, including `.aba`, `.myox`, `.ofx` and `.qif`.
- Fabricate your examples. A principal's name, a site, an ABN, a contract number
  or a claim schedule lifted from real work is client data however realistic it
  looks. Head contract terms are usually confidential as well.

## Writing a skill

- Send the agent to the primary source for anything that changes: fuel tax
  credit rates, the Coal LSL levy percentage, payroll tax rates and thresholds,
  effective life determinations, statutory timeframes and lodgment dates.
  Hardcode a current figure and the skill goes wrong later without saying so.
- Reach every step from the inputs the skill asks for. A step that needs a
  contract, a plant register or a payment history the skill never requested is
  broken rather than thorough.
- State the jurisdiction. Security of payment, payroll tax and retention trust
  rules differ by state, and a skill that says "the Act" without naming it will
  be applied to the wrong one.
- Keep the scope fence visible. Say what the skill declines to decide, and where
  a human signs off. Contract interpretation and eligibility conclusions belong
  to a person.
- Prefer a tie-out to an assertion. If a step produces a number, say what that
  number must agree with.

## Local verification

Python 3.10 or newer. The tests need the packages pinned in
[requirements-test.txt](requirements-test.txt).

```bash
python -m pip install --disable-pip-version-check --no-deps --requirement requirements-test.txt
python -m unittest discover -s tests -v
```

The suite checks skill metadata and structure. Add a test when your change
introduces a rule a reader could get wrong.

## Pull requests

Cite the provision, ruling or official page behind any technical change, and
give its date. When you alter a rule, search for every other place that states
or polices it. The same rule tends to appear in a checklist, a tie-out and a
worked example.

For a potential security vulnerability, follow [SECURITY.md](SECURITY.md)
rather than opening an issue.
