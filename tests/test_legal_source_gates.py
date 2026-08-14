"""Regression gates for the reviewed legal and tax source boundaries."""

from __future__ import annotations

import unittest
from pathlib import Path


REPOSITORY = Path(__file__).resolve().parents[1]
SKILLS = REPOSITORY / ".claude" / "skills"


def skill_text(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


class LegalSourceGateTests(unittest.TestCase):
    def test_nsw_mining_coverage_uses_primary_act_and_judgment(self) -> None:
        text = skill_text("progress-claim-preparation")

        self.assertIn(
            "https://legislation.nsw.gov.au/view/whole/html/inforce/current/act-1999-046",
            text,
        )
        self.assertIn(
            "https://www.caselaw.nsw.gov.au/decision/175b4bf54ee486b38a0338e5",
            text,
        )
        self.assertIn("s 5(2)(b)", text)
        self.assertIn("[101]-[112]", text)
        self.assertIn("[147]-[150]", text)
        self.assertIn("construction lawyer", text)
        self.assertIn("do not authorise an autonomous coverage conclusion", text)
        self.assertNotIn("Every NSW section number below comes from", text)
        self.assertNotIn("Commentary on Cadia", text)

    def test_nsw_retention_rule_preserves_guidance_conflict(self) -> None:
        text = skill_text("retention-schedule")

        self.assertIn(
            "https://legislation.nsw.gov.au/view/whole/html/inforce/current/act-1999-046",
            text,
        )
        self.assertIn(
            "https://legislation.nsw.gov.au/view/whole/html/inforce/current/sl-2020-0504",
            text,
        )
        self.assertIn(
            "https://www.nsw.gov.au/housing-and-construction/compliance-and-regulation/"
            "security-of-payment/retention-money",
            text,
        )
        self.assertIn("10 business days", text)
        self.assertIn("14 days", text)
        self.assertIn("cl 9(3)", text)
        self.assertIn("cl 20A", text)
        self.assertIn("1 July 2019", text)
        self.assertIn("in-force instrument as the controlling source", text)
        self.assertIn(
            "Never direct or authorise a withdrawal from a statutory trust account",
            text,
        )
        self.assertNotIn("its text was not read", text)
        self.assertNotIn("annual account review report survives is unresolved", text)

    def test_contractor_skill_uses_current_statutory_pathways(self) -> None:
        text = skill_text("contractor-super-tpar")

        required_sources = (
            "https://www.legislation.gov.au/C2004A04402/latest/text",
            "https://www.legislation.gov.au/C2025A00057/latest/text",
            "https://www.legislation.gov.au/C1953A00001/latest/text",
            "https://www.legislation.gov.au/F2017L01227/latest/text",
            "https://www.ato.gov.au/law/view/document?docid=TXR/TR20234/NAT/ATO/00001",
            "https://www.ato.gov.au/law/view/document?docid=SGR/SGR20052/NAT/ATO/00001",
            "https://softwaredevelopers.ato.gov.au/TPRS",
        )
        for source in required_sources:
            with self.subTest(source=source):
                self.assertIn(source, text)

        self.assertIn("s 10A(1)(d)", text)
        self.assertIn("1 July 2026", text)
        self.assertIn("Schedule 1 Division 405", text)
        self.assertIn("reg 70", text)
        self.assertIn("at least half", text)
        self.assertIn("materials-only supply", text)
        self.assertIn("no mechanical percentage", text)
        self.assertIn("genuine contract only with an interposed entity", text)
        self.assertIn("Do not conclude that a worker is or is not an employee", text)
        self.assertIn("Do not lodge the TPAR", text)
        self.assertNotIn("Building and construction is not in the Act at all", text)
        self.assertNotIn("whether payday super has commenced", text)
        self.assertNotIn("The worker carries the onus", text)

    def test_source_review_records_scope_and_no_client_data(self) -> None:
        review = (
            REPOSITORY / "docs" / "source-review-2026-08-15.md"
        ).read_text(encoding="utf-8")

        self.assertIn("## Scope and decision boundary", review)
        self.assertIn("## Controlling source order", review)
        self.assertIn("## NSW security of payment coverage", review)
        self.assertIn("## NSW retention-money trusts", review)
        self.assertIn("## Contractor superannuation and reporting", review)
        self.assertIn("No client records, identifiers or credentials were used", review)


if __name__ == "__main__":
    unittest.main()
