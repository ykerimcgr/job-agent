from __future__ import annotations

import unittest

from app_config import AppConfig, SearchConfig
from filter import filter_jobs
from filter.config import FilterConfig
from filter.location import LocationMatcher
from filter.normalizer import normalize_job
from services.cache import generate_scoring_cache_key
from services.job_scoring_pipeline import select_top_jobs
from services.jobspy_search import build_queries


class SearchFilterCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = AppConfig.load("profile/user_config.example.json")

    def test_queries_include_level_combinations_plain_roles_and_extras(self):
        search = self.config.search
        queries = build_queries(search)
        self.assertIn(f"{search.level_terms[0]} {search.target_roles[0]}", queries)
        self.assertIn(search.target_roles[0], queries)
        self.assertEqual(len(queries), len({query.casefold() for query in queries}))

    def test_extra_queries_are_deduplicated_case_insensitively(self):
        search = SearchConfig(
            target_roles=["Finance Analyst"],
            level_terms=["Junior"],
            extra_queries=["finance analyst", "Custom Finance Search"],
            sources=["indeed"],
        )
        self.assertEqual(
            build_queries(search),
            ["Junior Finance Analyst", "Finance Analyst", "Custom Finance Search"],
        )

    def test_title_and_description_hard_rejects(self):
        jobs = [
            self._job(title="Senior Finance Analyst"),
            self._job(description="This role requires 5+ years of experience."),
            self._job(title="Junior Finance Analyst"),
        ]
        accepted, rejected = filter_jobs(jobs, self.config)
        self.assertEqual(len(accepted), 1)
        reasons = {job["reject_reason"].split(":")[0] for job in rejected}
        self.assertIn("title_reject", reasons)
        self.assertIn("description_reject", reasons)

    def test_apprentice_regex_is_a_hard_reject(self):
        accepted, rejected = filter_jobs(
            [self._job(description="Join our degree apprenticeship programme.")],
            self.config,
        )
        self.assertFalse(accepted)
        self.assertTrue(rejected[0]["reject_reason"].startswith("description_regex_reject"))

    def test_soft_reject_reduces_score_without_immediate_rejection(self):
        clean, _ = filter_jobs([self._job(url="https://example.com/clean")], self.config)
        risky, _ = filter_jobs(
            [
                self._job(
                    url="https://example.com/risky",
                    description=(
                        "Junior finance role using Excel and financial reporting. "
                        "This is a commission opportunity."
                    ),
                )
            ],
            self.config,
        )
        self.assertTrue(clean)
        self.assertTrue(risky)
        self.assertLess(risky[0]["pre_score"], clean[0]["pre_score"])

    def test_uk_location_accepts_common_forms_and_rejects_explicit_foreign(self):
        matcher = LocationMatcher(FilterConfig.from_app_config(self.config))
        accepted_locations = [
            "London, England, UK",
            "Manchester, GB",
            "Edinburgh, Scotland",
            "Remote",
        ]
        for location in accepted_locations:
            with self.subTest(location=location):
                self.assertTrue(matcher.is_target_location(normalize_job(self._job(location=location))))
        self.assertFalse(
            matcher.is_target_location(
                normalize_job(self._job(location="Remote, United States"))
            )
        )

    def test_cache_key_changes_with_profile_and_config_fingerprint(self):
        job = self._job()
        common = {
            "prompt_version": "uk-fit-v1",
            "model": "gpt-4.1-mini",
        }
        first = generate_scoring_cache_key(job, "profile-a", "config-a", **common)
        second = generate_scoring_cache_key(job, "profile-b", "config-a", **common)
        third = generate_scoring_cache_key(job, "profile-a", "config-b", **common)
        self.assertNotEqual(first, second)
        self.assertNotEqual(first, third)

    def test_top_job_selection_uses_config_thresholds_and_uk_shape_is_external(self):
        scored = [
            self._scored(85, "strong_apply"),
            self._scored(65, "backup_option"),
            self._scored(59, "skip"),
        ]
        selected = select_top_jobs(scored, self.config)
        self.assertEqual([85, 65], [item["score_result"]["application_decision"]["applicable_rate"] for item in selected])
        self.assertEqual({"UK": selected}.keys(), {"UK"})

    @staticmethod
    def _job(**overrides):
        job = {
            "title": "Junior Finance Analyst",
            "company": "Example Ltd",
            "location": "London, England, UK",
            "target_market": "UK",
            "url": "https://example.com/job",
            "source": "indeed",
            "description": "Junior finance role using Excel and financial reporting.",
            "search_query": "Junior Finance Analyst",
        }
        job.update(overrides)
        return job

    @classmethod
    def _scored(cls, rate: int, decision: str):
        return {
            "job": cls._job(url=f"https://example.com/{rate}"),
            "score_result": {
                "status": "scored",
                "application_decision": {
                    "applicable_rate": rate,
                    "decision": decision,
                },
            },
        }


if __name__ == "__main__":
    unittest.main()
