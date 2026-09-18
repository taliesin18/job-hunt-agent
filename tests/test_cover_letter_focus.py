import unittest

from src.agents.cover_letter import (
    _approved_match_evidence,
    _clean_template_scaffolding,
    _focused_job_description,
)


class CoverLetterFocusTests(unittest.TestCase):
    def test_approved_evidence_excludes_weak_and_no_match_sections(self):
        evidence = _approved_match_evidence(
            "**Strong matches**\n- SaaS application support\n\n"
            "**Moderate matches**\n- Documentation\n\n"
            "**Weak matches**\n- Embedded systems\n\n"
            "**No matches**\n- Smartcard testing"
        )

        self.assertIn("SaaS application support", evidence)
        self.assertIn("Documentation", evidence)
        self.assertNotIn("Embedded systems", evidence)
        self.assertNotIn("Smartcard testing", evidence)

    def test_focused_description_removes_job_board_chrome_and_keeps_role_content(self):
        focused = _focused_job_description(
            "Saved jobs About the role Configure SaaS workflows and support UAT. "
            "About you Strong documentation skills. Employer questions Salary expectations."
        )

        self.assertTrue(focused.startswith("About the role"))
        self.assertIn("support UAT", focused)
        self.assertNotIn("Employer questions", focused)

    def test_template_letterhead_and_note_are_removed(self):
        cleaned = _clean_template_scaffolding(
            "Candidate Name\n[Your Address]\n\nDear Hiring Manager,\n\n"
            "**Relevant implementation experience.**\n\nSincerely,\nCandidate Name\n\n"
            "Note: customize before sending.",
            "Candidate Name",
        )

        self.assertTrue(cleaned.startswith("Dear Hiring Manager,"))
        self.assertNotIn("[Your Address]", cleaned)
        self.assertNotIn("Note:", cleaned)
        self.assertNotIn("**", cleaned)


if __name__ == "__main__":
    unittest.main()
