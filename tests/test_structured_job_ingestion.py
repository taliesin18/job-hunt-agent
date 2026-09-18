import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import config, orchestrator
from src.api import MatchRequest, match


class StructuredJobIngestionTests(unittest.TestCase):
    def setUp(self):
        self.job = {
            "id": "job_2026-09-18_example_123",
            "company": "Example Co",
            "title": "Backend Engineer",
            "url": "https://careers.example.test/jobs/123",
            "date_saved": "2026-09-18",
            "raw_description": "Build reliable backend services using Python.",
            "required_skills": ["Python", "APIs"],
            "location": "Remote",
            "employment_type": "Full-time",
            "responsibilities": ["Build services"],
            "preferred_skills": ["Kubernetes"],
        }

    @patch("src.orchestrator.match_job")
    def test_structured_posting_is_normalized_and_saved_after_a_match(self, mock_match):
        mock_match.return_value = {"report": "Strong matches", "confidence": 72, "confidence_detected": True}
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(config, "JOB_POSTINGS_DIR", Path(temp_dir)):
            result = orchestrator.run_matching_parsed(self.job)

            self.assertTrue(result["saved"])
            self.assertEqual(result["job"]["location"], "Remote")
            self.assertEqual(result["job"]["preferred_skills"], ["Kubernetes"])
            saved = json.loads((Path(temp_dir) / f"{self.job['id']}.json").read_text(encoding="utf-8"))
            self.assertEqual(saved["raw_description"], self.job["raw_description"])

    @patch("src.orchestrator.match_job")
    def test_low_confidence_structured_posting_is_not_saved(self, mock_match):
        mock_match.return_value = {"report": "Gaps", "confidence": 20, "confidence_detected": True}
        with tempfile.TemporaryDirectory() as temp_dir, patch.object(config, "JOB_POSTINGS_DIR", Path(temp_dir)):
            result = orchestrator.run_matching_parsed(self.job)

            self.assertFalse(result["saved"])
            self.assertFalse((Path(temp_dir) / f"{self.job['id']}.json").exists())

    @patch("src.api.run_matching_parsed")
    def test_api_uses_import_path_for_a_new_structured_posting(self, mock_import):
        mock_import.return_value = {
            "job": self.job,
            "match_report": "Strong matches",
            "confidence": 72,
            "confidence_detected": True,
            "below_threshold": False,
            "saved": True,
        }

        result = match(MatchRequest(job=self.job, save_job=True))

        mock_import.assert_called_once_with(self.job)
        self.assertEqual(result["confidence_threshold"], 50)
