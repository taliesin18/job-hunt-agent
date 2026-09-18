import unittest

from src.agents.matcher import _parse_confidence


class ParseConfidenceTests(unittest.TestCase):
    def test_parses_a_markdown_wrapped_score_line(self):
        report, confidence, detected = _parse_confidence(
            "Strong matches\n- Skill\n\n**Confidence**: 72/100"
        )

        self.assertEqual("Strong matches\n- Skill", report)
        self.assertEqual(72, confidence)
        self.assertTrue(detected)

    def test_missing_score_is_not_treated_as_a_perfect_match(self):
        report, confidence, detected = _parse_confidence(
            "Strong matches\n- Skill\n\nWeak matches\n- Missing requirement"
        )

        self.assertIn("Weak matches", report)
        self.assertIsNone(confidence)
        self.assertFalse(detected)


if __name__ == "__main__":
    unittest.main()
