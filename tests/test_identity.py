from __future__ import annotations

import unittest

from filter.dedup import remove_duplicates
from filter.identity import content_key, job_identity, legacy_emailed_hash, source_job_id


def job(title="Graduate Analyst", company="Acme Ltd", url="", market="UK"):
    return {"title": title, "company": company, "url": url, "target_market": market}


class IdentityTests(unittest.TestCase):
    def test_indeed_listings_keep_their_jk_id(self):
        self.assertEqual(
            source_job_id("https://uk.indeed.com/viewjob?jk=8c471ae67870aae6"),
            "indeed:8c471ae67870aae6",
        )
        self.assertNotEqual(
            source_job_id("https://uk.indeed.com/viewjob?jk=aaa"),
            source_job_id("https://uk.indeed.com/viewjob?jk=bbb"),
        )

    def test_linkedin_id_ignores_slug_and_tracking(self):
        self.assertEqual(
            source_job_id("https://www.linkedin.com/jobs/view/4483472327"),
            "linkedin:4483472327",
        )
        self.assertEqual(
            source_job_id("https://uk.linkedin.com/jobs/view/graduate-analyst-at-acme-4483472327?trk=x"),
            "linkedin:4483472327",
        )

    def test_indeed_without_id_is_not_identifiable_by_url(self):
        self.assertEqual(source_job_id("https://uk.indeed.com/viewjob"), "")

    def test_content_key_ignores_case_punctuation_and_company_suffix(self):
        self.assertEqual(
            content_key(job("Graduate Analyst", "Acme Ltd")),
            content_key(job("graduate analyst", "ACME")),
        )
        self.assertNotEqual(content_key(job(market="UK")), content_key(job(market="TR")))

    def test_identity_survives_url_tracking_changes(self):
        self.assertEqual(
            job_identity(job(url="https://www.linkedin.com/jobs/view/1?trk=a")),
            job_identity(job(url="https://www.linkedin.com/jobs/view/1?trk=b")),
        )

    def test_dedup_keeps_distinct_indeed_jobs_and_drops_cross_source_copies(self):
        jobs = [
            job("Data Analyst", "A", "https://uk.indeed.com/viewjob?jk=1"),
            job("Reporting Analyst", "B", "https://uk.indeed.com/viewjob?jk=2"),
            job("Data Analyst", "A Ltd", "https://www.linkedin.com/jobs/view/9"),
            job("Other", "C", "https://uk.indeed.com/viewjob?jk=2"),
        ]
        unique, duplicates = remove_duplicates(jobs)
        self.assertEqual([j["title"] for j in unique], ["Data Analyst", "Reporting Analyst"])
        self.assertEqual(len(duplicates), 2)
        self.assertTrue(all(j["reject_reason"] == "duplicate" for j in duplicates))

    def test_missing_jobspy_fields_become_empty_text(self):
        # JobSpy returns a missing company as pandas NaN (a float), which is truthy.
        from services.jobspy_search import normalize_jobspy_row

        row = {"title": "Data Analyst", "company": float("nan"), "location": None,
               "job_url": "https://example.com/a", "site": "linkedin",
               "description": float("nan"), "date_posted": float("nan")}
        job = normalize_jobspy_row(row, "Data Analyst", "UK")
        for field in ("company", "location", "description", "date_posted"):
            self.assertEqual(job[field], "", field)
        self.assertEqual(len(legacy_emailed_hash(job)), 64)


if __name__ == "__main__":
    unittest.main()
