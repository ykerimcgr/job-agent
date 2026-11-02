from __future__ import annotations

from datetime import datetime
import json
from pathlib import Path
import tempfile
import unittest
from zoneinfo import ZoneInfo

from app_config import AppConfig, ConfigError


EXAMPLE_PATH = Path("profile/user_config.example.json")


class AppConfigTests(unittest.TestCase):
    def test_example_config_loads_with_expected_defaults(self):
        config = AppConfig.load(EXAMPLE_PATH)
        self.assertEqual([m.code for m in config.markets], ["UK", "TR"])
        self.assertEqual(config.selection.max_jobs, 10)
        self.assertEqual(config.filters.advanced.min_pre_score, 5)

    def test_config_without_markets_defaults_to_uk(self):
        raw = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        del raw["markets"]
        raw["market"] = "UK"  # legacy key still accepted
        config = self._load(raw)
        self.assertEqual([m.code for m in config.markets], ["UK"])

    def test_market_contact_overrides_and_right_to_work(self):
        config = AppConfig.load(EXAMPLE_PATH)
        uk, tr = config.markets
        profile = {"name": "N", "current_location": "Turkey", "right_to_work": "UK Graduate Visa"}
        self.assertEqual(config.contact_context(profile, uk)["right_to_work"], "UK Graduate Visa")
        tr_contact = config.contact_context(profile, tr)
        self.assertEqual(tr_contact["right_to_work"], "")
        self.assertEqual(tr_contact["address"], "Istanbul, Türkiye")

    def test_unknown_fields_fail_fast(self):
        raw = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        raw["search"]["typo_field"] = 1
        with self.assertRaisesRegex(ConfigError, "search.typo_field"):
            self._load(raw)

    def test_contact_overrides_replace_extracted_fields_only_when_non_empty(self):
        raw = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        raw["candidate"]["contact_overrides"] = {
            "name": "Example Candidate",
            "address": "Manchester, United Kingdom",
            "email": "",
        }
        config = self._load(raw)
        merged = config.merge_profile(
            {
                "name": "Old Name",
                "email": "candidate@example.com",
                "current_location": "London",
            }
        )
        self.assertEqual(merged["name"], "Example Candidate")
        self.assertEqual(merged["email"], "candidate@example.com")
        self.assertEqual(merged["current_location"], "Manchester, United Kingdom")

    def test_invalid_target_roles_fail_fast(self):
        raw = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        raw["search"]["target_roles"] = []
        with self.assertRaisesRegex(ConfigError, "search.target_roles"):
            self._load(raw)

    def test_invalid_regex_fails_fast(self):
        raw = json.loads(EXAMPLE_PATH.read_text(encoding="utf-8"))
        raw["filters"]["soft_reject_regex"] = ["["]
        with self.assertRaisesRegex(ConfigError, "Invalid regex"):
            self._load(raw)

    def test_schedule_uses_london_timezone_and_force_bypasses_window(self):
        config = AppConfig.load(EXAMPLE_PATH)
        monday_ten = datetime(2026, 7, 27, 10, 0, tzinfo=ZoneInfo("Europe/London"))
        monday_noon = datetime(2026, 7, 27, 12, 0, tzinfo=ZoneInfo("Europe/London"))
        sunday_ten = datetime(2026, 7, 26, 10, 0, tzinfo=ZoneInfo("Europe/London"))
        self.assertTrue(config.schedule.should_run(monday_noon))
        self.assertFalse(config.schedule.should_run(monday_ten))  # every 3 hours from 09:00
        self.assertFalse(config.schedule.should_run(sunday_ten))
        self.assertTrue(config.schedule.should_run(sunday_ten, force=True))

    def _load(self, raw: dict) -> AppConfig:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "config.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            return AppConfig.load(path)


if __name__ == "__main__":
    unittest.main()
