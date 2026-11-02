from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from app_config import AppConfig
import main
from services.document_generator import render_cover_letter_tex
from services.email_sender import send_job_email


class DocumentsEmailPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = AppConfig.load("profile/user_config.example.json")

    def test_cover_letter_uses_candidate_name_without_hardcoded_author(self):
        tex = render_cover_letter_tex(
            {
                "opening": "A role-specific opening.",
                "key_fit": [{"requirement": "Excel", "evidence": "Used in reporting."}],
                "closing": "Thank you for your consideration.",
            },
            {
                "name": "Example Candidate",
                "address": "Manchester, UK",
                "phone": "000",
                "email": "candidate@example.com",
                "linkedin": "linkedin.com/in/example",
            },
        )
        self.assertIn("Example Candidate", tex)
        self.assertNotIn("Yusuf Ciger", tex)

    @patch("services.email_sender.mark_job_items_as_emailed")
    @patch("services.email_sender.smtplib.SMTP_SSL")
    def test_smtp_failure_does_not_mark_jobs_as_emailed(self, smtp_ssl, mark_emailed):
        smtp_ssl.side_effect = RuntimeError("smtp unavailable")
        profile = {"name": "Example Candidate", "email": "candidate@example.com"}
        with patch.dict(
            os.environ,
            {"EMAIL_ADDRESS": "sender@example.com", "EMAIL_PASSWORD": "secret"},
            clear=False,
        ):
            sent = send_job_email(
                {"UK": [self._job_item()]},
                [],
                profile,
                self.config,
            )
        self.assertFalse(sent)
        mark_emailed.assert_not_called()

    @patch("services.email_sender.mark_job_items_as_emailed")
    @patch("services.email_sender.smtplib.SMTP_SSL")
    def test_successful_email_marks_jobs_as_emailed(self, smtp_ssl, mark_emailed):
        smtp = smtp_ssl.return_value.__enter__.return_value
        profile = {"name": "Example Candidate", "email": "candidate@example.com"}
        with patch.dict(
            os.environ,
            {"EMAIL_ADDRESS": "sender@example.com", "EMAIL_PASSWORD": "secret"},
            clear=False,
        ):
            sent = send_job_email(
                {"UK": [self._job_item()]},
                [],
                profile,
                self.config,
            )
        self.assertTrue(sent)
        smtp.login.assert_called_once()
        smtp.send_message.assert_called_once()
        mark_emailed.assert_called_once()

    def test_runtime_validation_reports_missing_credentials_before_work(self):
        with tempfile.TemporaryDirectory() as directory:
            cv_path = Path(directory) / "master_cv.tex"
            cv_path.write_text("CV", encoding="utf-8")
            with (
                patch.object(main, "CV_PATH", cv_path),
                patch.dict(os.environ, {}, clear=True),
            ):
                with self.assertRaisesRegex(ValueError, "OPENAI_API_KEY"):
                    main.validate_runtime(self.config)

    @patch("main.send_job_email")
    @patch("main.generate_documents_for_top_jobs")
    @patch("main.load_existing_top_jobs", return_value={"UK": []})
    @patch("main.select_top_jobs", return_value=[])
    @patch("main.score_jobs_batch", return_value=[])
    @patch("main.filter_out_emailed_jobs", return_value=[])
    @patch("main.filter_jobs", return_value=([], []))
    @patch("main.fetch_all_jobs_with_jobspy", return_value=[])
    @patch(
        "main.load_or_extract_profile",
        return_value=({"name": "Example Candidate"}, "profile-hash", "cv"),
    )
    def test_empty_run_skips_documents_and_email(
        self,
        _profile,
        _fetch,
        _filter,
        _fresh,
        _score,
        _select,
        _existing,
        generate_documents,
        send_email,
    ):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (
                patch.object(main, "OUTPUT_DIR", root),
                patch.object(main, "JOBSPY_DIR", root / "Jobspy"),
                patch.object(main, "UK_DIR", root / "UK"),
                patch.object(main, "HISTORY_DIR", root / "history"),
            ):
                result = main.run_pipeline_once(
                    config=self.config,
                    perform_preflight=False,
                )
        self.assertEqual(result["top_jobs"], {"UK": []})
        self.assertFalse(result["email_sent"])
        generate_documents.assert_not_called()
        send_email.assert_not_called()

    @staticmethod
    def _job_item():
        return {
            "job": {
                "title": "Finance Analyst",
                "company": "Example Ltd",
                "url": "https://example.com/job",
            },
            "score_result": {
                "application_decision": {
                    "applicable_rate": 80,
                    "decision": "strong_apply",
                }
            },
        }


if __name__ == "__main__":
    unittest.main()
