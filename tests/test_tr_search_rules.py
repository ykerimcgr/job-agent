from __future__ import annotations

import unittest

from app_config import AppConfig, ExtraSearch
from filter import FilterConfig, filter_jobs
from filter.location import LocationMatcher
from filter.normalizer import normalize_job
from services.jobspy_search import normalize_jobspy_row, scrape_arguments, search_plan


def job(title, location="Istanbul, Türkiye", **extra):
    return {
        "title": title,
        "company": "Acme",
        "location": location,
        "target_market": "TR",
        "url": f"https://www.linkedin.com/jobs/view/{abs(hash((title, location)))}",
        "source": "linkedin",
        "description": "Data analysis with Python and SQL for operations reporting.",
        **extra,
    }


class TurkishSearchRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        base = AppConfig.load("profile/user_config.example.json")
        filters = base.filters.model_copy(update={
            "title_hard_reject": ["senior", "manager", "yönetici"],
            "title_hard_reject_exceptions": ["graduate", "new graduates", "yardımcısı", "trainee"],
        })
        cls.config = base.model_copy(update={"filters": filters})
        cls.tr = base.markets[1].model_copy(update={
            "extra_title_hard_reject": ["temporary", "geçici"],
            "hours_old": None,
            "ai_candidate_limit": None,
            "extra_searches": [],
        })

    def reasons(self, *jobs):
        accepted, rejected = filter_jobs(list(jobs), FilterConfig.for_market(self.config, self.tr))
        return {j["title"]: j.get("reject_reason", "kept") for j in accepted + rejected}

    def test_senior_words_do_not_reject_graduate_or_assistant_titles(self):
        reasons = self.reasons(
            job("New Graduates 2027: Information Technology Manager"),
            job("Veri Bilimcisi - Model Validasyon Yönetici Yardımcısı"),
            job("Senior Data Scientist"),
            job("Operations Manager"),
        )
        self.assertFalse(reasons["New Graduates 2027: Information Technology Manager"].startswith("title_reject"))
        self.assertFalse(reasons["Veri Bilimcisi - Model Validasyon Yönetici Yardımcısı"].startswith("title_reject"))
        self.assertEqual(reasons["Senior Data Scientist"], "title_reject:senior")
        self.assertEqual(reasons["Operations Manager"], "title_reject:manager")

    def test_temporary_titles_are_rejected(self):
        reasons = self.reasons(job("Stock Control Specialist (Temporary)"), job("Geçici Planlama Uzmanı"))
        self.assertEqual(set(reasons.values()), {"title_reject:temporary", "title_reject:geçici"})

    def test_remote_listing_elsewhere_in_the_country_is_accepted(self):
        matcher = LocationMatcher(FilterConfig.for_market(self.config, self.tr))
        self.assertTrue(matcher.is_target_location(normalize_job(job("Data Analyst", "Ankara, Türkiye", is_remote=True))))
        self.assertFalse(matcher.is_target_location(normalize_job(job("Data Analyst", "Ankara, Türkiye"))))
        self.assertFalse(matcher.is_target_location(normalize_job(job("Data Analyst", "London, UK", is_remote=True))))

    def test_market_window_and_extra_searches(self):
        market = self.tr.model_copy(update={
            "hours_old": 336,
            "queries": ["Veri Bilimci", "Yeni Mezun"],
            "extra_searches": [
                ExtraSearch(location="Kocaeli, Turkey", queries=["Endüstri Mühendisi"]),
                ExtraSearch(location="Turkey", remote=True),
            ],
        })
        plan = search_plan(self.config.search, market)
        self.assertEqual(plan, [
            ("Veri Bilimci", "Istanbul, Turkey", False),
            ("Yeni Mezun", "Istanbul, Turkey", False),
            ("Endüstri Mühendisi", "Kocaeli, Turkey", False),
            ("Veri Bilimci", "Turkey", True),  # no queries of its own: the market's queries
            ("Yeni Mezun", "Turkey", True),
        ])
        args = scrape_arguments("Veri Bilimci", self.config.search, market, location="Turkey", remote=True)
        self.assertEqual((args["hours_old"], args["location"], args["is_remote"]), (336, "Turkey", True))
        plain = scrape_arguments("Veri Bilimci", self.config.search, self.tr)
        self.assertEqual(plain["hours_old"], self.config.search.hours_old)
        self.assertNotIn("is_remote", plain)

    def test_market_can_raise_the_ai_candidate_limit(self):
        from main import candidate_limit
        self.assertEqual(candidate_limit(self.config, self.tr), self.config.selection.ai_candidate_limit)
        self.assertEqual(candidate_limit(self.config, self.tr.model_copy(update={"ai_candidate_limit": 140})), 140)

    def test_remote_flag_survives_ingestion(self):
        row = {"title": "Data Analyst", "is_remote": True, "job_url": "https://example.com/1"}
        self.assertTrue(normalize_jobspy_row(row, "Data Analyst", "TR")["is_remote"])
        self.assertFalse(normalize_jobspy_row({"is_remote": float("nan")}, "x", "TR")["is_remote"])


if __name__ == "__main__":
    unittest.main()
