from __future__ import annotations

import unittest

from app_config import AppConfig
from filter import FilterConfig, filter_jobs
from filter.experience import required_years
from filter.location import LocationMatcher
from filter.normalizer import normalize_job
from services.cv_template import parse_cv, render_cv
from services.document_generator import ApplicationDraft, escape_latex, ground_draft
from services.grounding import risky_vocabulary, unsupported_terms, vocabulary
from services.jobspy_search import build_queries, scrape_arguments
from services.scoring import JobAssessment, Requirement, applicable_rate


CV = r"""\documentclass{article}
\begin{document}
\begin{center}
    {\Large \textbf{Old Name}} \\[0.2cm]
    Turkey \textbar \quad old@example.com
\end{center}
\section{Professional Summary}
Data graduate who automated reporting.
\section{Professional Experience}
\entry{Sales Executive}{2026}
{Field Sales}{London, UK}
\begin{itemize}
    \item Converted customer interest into agreements.
\end{itemize}
\vspace{6pt}
\entry{Engineering Intern}{2023}
{Amadeus}{Istanbul}
\begin{itemize}
    \item Reduced manual reporting effort by 80\% using Python automation.
    \item Built Excel reporting outputs for operations.
\end{itemize}
\section{Education}
\entry{MSc Data Science}{2025}
{University of Sussex}{Brighton}
\begin{itemize}
    \item Built forecasting models.
\end{itemize}
\section{Additional Information}
\begin{itemize}
    \item Full right to work in the UK (Graduate Visa)
\end{itemize}
\end{document}
"""

CONTACT = {"name": "New Name", "address": "Istanbul, Türkiye", "phone": "", "email": "a@b.c", "linkedin": "", "right_to_work": ""}


def job(location="Istanbul, Türkiye", title="Junior Data Analyst", market="TR", **extra):
    return {
        "title": title,
        "company": "Acme",
        "location": location,
        "target_market": market,
        "url": f"https://www.linkedin.com/jobs/view/{abs(hash((title, location)))}",
        "source": "linkedin",
        "description": "Junior data analyst role using SQL and Excel reporting.",
        **extra,
    }


class MarketTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = AppConfig.load("profile/user_config.example.json")
        cls.uk, cls.tr = cls.config.markets

    def test_istanbul_is_strict_but_accepts_country_wide_and_remote(self):
        matcher = LocationMatcher(FilterConfig.for_market(self.config, self.tr))
        for location, expected in [
            ("Istanbul, Istanbul, Türkiye", True),
            ("Ataşehir, İstanbul", True),
            ("Türkiye", True),
            ("Remote, Turkey", True),
            ("", True),
            ("Ankara, Türkiye", False),
            ("İzmir", False),
            ("London, England, UK", False),
        ]:
            with self.subTest(location=location):
                self.assertEqual(matcher.is_target_location(normalize_job(job(location))), expected)

    def test_job_from_another_market_is_rejected(self):
        matcher = LocationMatcher(FilterConfig.for_market(self.config, self.uk))
        self.assertFalse(matcher.is_target_location(normalize_job(job("London", market="TR"))))

    def test_turkish_titles_and_rejects(self):
        accepted, rejected = filter_jobs(
            [
                job(title="Yeni Mezun Veri Analisti"),
                job(title="Kıdemli İş Analisti"),
                job(title="Veri Analisti Stajyer"),
            ],
            FilterConfig.for_market(self.config, self.tr),
        )
        self.assertEqual([j["title"] for j in accepted], ["Yeni Mezun Veri Analisti"])
        self.assertIn("level:yeni mezun", accepted[0]["quality_flags"])
        self.assertEqual({j["reject_reason"].split(":")[0] for j in rejected}, {"title_reject"})

    def test_domain_title_rejects_skip_ai_and_programme_titles(self):
        filters = self.config.filters.model_copy(update={
            "title_hard_reject": ["senior"],
            "title_domain_reject": ["developer", "finance", "muhasebe"],
            "title_domain_exceptions": ["ai", "automation", "programme"],
        })
        config = self.config.model_copy(update={"filters": filters})
        titles = ["Junior Python Developer", "Junior AI & Automation Developer", "Junior Finance Analyst",
                  "Finance Graduate Programme", "Junior Muhasebe Uzmanı", "Junior Data Analyst"]
        accepted, rejected = filter_jobs(
            [job(title=t, location="London", market="UK") for t in titles],
            FilterConfig.for_market(config, self.uk),
        )
        self.assertEqual(
            {j["title"] for j in accepted},
            {"Junior AI & Automation Developer", "Finance Graduate Programme", "Junior Data Analyst"},
        )
        self.assertTrue(all(j["reject_reason"].startswith("title_domain_reject:") for j in rejected))

    def test_years_of_experience_hard_reject(self):
        _, rejected = filter_jobs(
            [job(description="Junior analyst. En az 5 yıl deneyim gerekmektedir.")],
            FilterConfig.for_market(self.config, self.tr),
        )
        self.assertEqual(rejected[0]["reject_reason"], "experience_years:5")

    def test_required_years_reads_escapes_ranges_and_alternatives(self):
        for text, expected in [
            (r"* 2\+ years experience in data analysis", 2),
            (r"has 1\-2 years commercial experience", 1),
            ("0-2 years of experience", 0),
            ("alaninda en az 1 yıl deneyimli", 1),
            (r"* 1\+ years of experience (or strong academic/project background)", None),
            ("start your career with two years of hands-on learning", None),
        ]:
            with self.subTest(text=text):
                self.assertEqual(required_years(text), expected)

    def test_tr_queries_use_market_levels_and_extras(self):
        expanded = self.tr.model_copy(update={"queries": None, "extra_queries": ["Veri Analisti"]})
        queries = build_queries(self.config.search, expanded)
        self.assertIn("Junior Business Analyst", queries)
        self.assertNotIn("Graduate Business Analyst", queries)
        self.assertIn("Veri Analisti", queries)
        self.assertEqual(build_queries(self.config.search, self.tr), self.tr.queries)


    def test_market_overrides_sources_and_result_count(self):
        search = self.config.search
        tr = self.tr.model_copy(update={"hours_old": None})
        plain = scrape_arguments("Veri Bilimci", search, tr.model_copy(update={"sources": None, "results_per_query": None}))
        self.assertEqual(plain["site_name"], search.sources)
        self.assertEqual(plain["results_wanted"], search.results_per_query)
        self.assertNotIn("google_search_term", plain)

        market = tr.model_copy(update={"sources": ["linkedin", "google"], "results_per_query": 25})
        custom = scrape_arguments("Veri Bilimci", search, market)
        self.assertEqual(custom["site_name"], ["linkedin", "google"])
        self.assertEqual(custom["results_wanted"], 25)
        # Google Jobs ignores search_term/location and needs one natural-language query.
        self.assertEqual(custom["google_search_term"], "Veri Bilimci jobs near Istanbul, Turkey in the last 3 days")

    def test_explicit_market_queries_replace_role_level_expansion(self):
        market = self.uk.model_copy(update={"queries": ["Data Analyst", "data analyst", "RPA Analyst"]})
        self.assertEqual(build_queries(self.config.search, market), ["Data Analyst", "RPA Analyst"])

    def test_level_is_not_repeated_inside_role(self):
        search = self.config.search.model_copy(update={"target_roles": ["Graduate Analyst"], "level_terms": ["Graduate", "Junior"]})
        self.assertEqual(build_queries(search), ["Junior Graduate Analyst", "Graduate Analyst"])


class ScoringTests(unittest.TestCase):
    @staticmethod
    def assessment(statuses, level="junior", years=None, blockers=(), role="direct"):
        return JobAssessment(
            role_match=role,
            role_level=level,
            years_required=years,
            work_model="hybrid",
            blockers=list(blockers),
            requirements=[
                Requirement(requirement=f"r{i}", importance=imp, status=st, evidence="")
                for i, (imp, st) in enumerate(statuses)
            ],
            strengths=[],
            gaps=[],
            application_angle="",
            reasoning="",
        )

    def test_rate_spreads_with_evidence(self):
        full = self.assessment([("must", "met"), ("must", "met"), ("nice", "met")])
        half = self.assessment([("must", "met"), ("must", "missing"), ("nice", "partial")])
        self.assertEqual(applicable_rate(full, 3), 100)
        self.assertEqual(applicable_rate(half, 3), 50)

    def test_seniority_years_and_blockers_cut_the_rate(self):
        base = [("must", "met"), ("nice", "met")]
        self.assertEqual(applicable_rate(self.assessment(base, level="senior"), 3), 65)
        self.assertEqual(applicable_rate(self.assessment(base, years=5), 3), 80)
        self.assertEqual(applicable_rate(self.assessment(base, blockers=["SC clearance"]), 3), 40)

    def test_off_target_roles_fall_below_selection(self):
        full = [("must", "met"), ("nice", "met")]
        self.assertEqual(applicable_rate(self.assessment(full, role="adjacent"), 3), 85)
        self.assertEqual(applicable_rate(self.assessment(full, role="unrelated"), 3), 45)


class CvTemplateTests(unittest.TestCase):
    def setUp(self):
        self.template = parse_cv(CV)

    def test_parse_finds_entries_and_locks(self):
        blocks = {b.heading.split(" | ")[0]: b for b in self.template.blocks}
        self.assertTrue(blocks["Sales Executive"].droppable)
        self.assertFalse(blocks["MSc Data Science"].droppable)
        self.assertFalse(blocks["Additional Information"].editable)
        self.assertEqual(self.template.summary, "Data graduate who automated reporting.")

    def test_render_drops_entries_reorders_bullets_and_sets_header(self):
        sales, intern = self.template.blocks[0], self.template.blocks[1]
        b_reduce, b_excel = intern.bullets
        tex = render_cv(
            self.template,
            summary="Data graduate focused on reporting automation.",
            block_plans={
                sales.id: (False, []),
                intern.id: (True, [(b_excel.id, "Built Excel reporting for operations teams."), (b_reduce.id, b_reduce.text)]),
            },
            contact=CONTACT,
            escape=escape_latex,
        )
        self.assertNotIn("Sales Executive", tex)
        self.assertNotIn("Old Name", tex)
        self.assertIn(r"\textbf{New Name}", tex)
        self.assertIn("Istanbul, Türkiye", tex)
        self.assertLess(tex.index("operations teams"), tex.index(r"80\%"))
        self.assertIn(r"80\% using Python", tex)  # unchanged bullet keeps its original LaTeX
        # The right-to-work bullet was the only item: the whole list goes, so it still compiles.
        self.assertNotIn("Graduate Visa", tex)
        self.assertEqual(tex.count(r"\begin{itemize}"), tex.count(r"\end{itemize}"))
        self.assertEqual(tex.count(r"\begin{itemize}"), 2)


class GroundingTests(unittest.TestCase):
    def setUp(self):
        self.template = parse_cv(CV)
        self.known = vocabulary(self.template.plain_text)

    def test_new_numbers_tools_and_unmet_skills_are_flagged(self):
        risky = risky_vocabulary(["Experience with Tableau dashboards", "Knowledge of IFRS"], self.known)
        source = "Reduced manual reporting effort by 80% using Python automation."
        check = lambda text: unsupported_terms(text, source=source, known=self.known, risky=risky)
        self.assertEqual(check("Cut manual reporting effort by 80% through Python automation."), [])
        self.assertEqual(check("Reduced reporting effort by 90% using Python."), ["90"])
        self.assertIn("Tableau", check("Reduced reporting effort by 80% using Python and Tableau."))
        self.assertIn("dashboards", check("Automated reporting dashboards with Python."))
        # A cover letter speaks in the first person; "I" is not a claim.
        self.assertEqual(check("At Amadeus I reduced manual reporting effort by 80% using Python."), [])

    def test_ground_draft_reverts_bad_rewrites_and_keeps_good_ones(self):
        intern = self.template.blocks[1]
        b_reduce, b_excel = intern.bullets
        draft = ApplicationDraft(
            summary="Data graduate with 5 years of Tableau experience.",
            blocks=[
                {"id": intern.id, "keep": True, "bullets": [
                    {"id": b_reduce.id, "text": "Reduced manual reporting effort by 95% with Python."},
                    {"id": b_excel.id, "text": "Built Excel reporting outputs for operations."},
                    {"id": "b999", "text": "Invented bullet."},
                ]},
                {"id": self.template.blocks[0].id, "keep": False, "bullets": []},
            ],
            cover_opening="I am applying for the Junior Data Analyst role at Acme.",
            cover_key_fit=[
                {"requirement": "SQL", "evidence": "Built Excel reporting outputs for operations."},
                {"requirement": "Tableau", "evidence": "Built Tableau dashboards."},
            ],
            cover_closing="I led a team of 12 analysts.",
        )
        score = {"assessment": {"requirements": [{"requirement": "Tableau dashboards", "status": "missing"}]}}
        grounded, fixes = ground_draft(draft, self.template, job(), score)

        self.assertIsNone(grounded["summary"])
        self.assertEqual(
            grounded["block_plans"][intern.id][1],
            [(b_reduce.id, b_reduce.text), (b_excel.id, b_excel.text)],
        )
        self.assertEqual(grounded["removed_entries"], [self.template.blocks[0].heading])
        self.assertEqual([k["requirement"] for k in grounded["cover"]["key_fit"]], ["SQL"])
        self.assertIn("Acme", grounded["cover"]["opening"])
        self.assertNotIn("12", grounded["cover"]["closing"])
        self.assertTrue(fixes)

    def test_bullets_may_combine_facts_from_their_own_entry_only(self):
        sales, intern = self.template.blocks[0], self.template.blocks[1]
        b_reduce, b_excel = intern.bullets
        draft = ApplicationDraft(
            summary="Data graduate targeting the Graduate Machine Learning Engineer role at Acme.",
            blocks=[
                {"id": intern.id, "keep": True, "bullets": [
                    {"id": b_excel.id, "text": "Built Excel reporting outputs for operations and cut manual effort by 80% using Python automation."},
                    {"id": b_reduce.id, "text": "Reduced manual reporting effort by 80% with Python in 2025."},
                ]},
                {"id": sales.id, "keep": True, "bullets": [
                    {"id": sales.bullets[0].id, "text": "Converted customer interest into agreements using Python."},
                ]},
            ],
            cover_opening="I am applying for the Graduate Machine Learning Engineer 2027 role at Acme.",
            cover_key_fit=[],
            cover_closing="Thank you for your time.",
        )
        ad = job(title="Graduate Machine Learning Engineer 2027")
        grounded, _ = ground_draft(draft, self.template, ad, {"assessment": {"requirements": []}})
        plans = grounded["block_plans"]
        self.assertIn("80%", plans[intern.id][1][0][1])  # merged from a sibling bullet: kept
        self.assertEqual(plans[intern.id][1][1][1], b_reduce.text)  # 2025 is only in the Education entry: reverted
        self.assertEqual(plans[sales.id][1][0][1], sales.bullets[0].text)  # Python is only in the Amadeus entry: reverted
        self.assertIn("Machine Learning Engineer", grounded["summary"])
        self.assertIn("2027", grounded["cover"]["opening"])

    def test_cover_opening_may_name_the_employer_from_the_job_ad(self):
        draft = ApplicationDraft(
            summary="",
            blocks=[],
            cover_opening="I am applying for the Graduate Analyst scheme at InPost via targetjobs.",
            cover_key_fit=[],
            cover_closing="I would welcome the chance to bring my Tableau skills to InPost.",
        )
        ad = job(company="targetjobs UK", description="InPost is hiring graduates. Tableau preferred.")
        score = {"assessment": {"requirements": [{"requirement": "Tableau", "status": "missing"}]}}
        grounded, _ = ground_draft(draft, self.template, ad, score)
        self.assertIn("InPost", grounded["cover"]["opening"])
        self.assertNotIn("Tableau", grounded["cover"]["closing"])


if __name__ == "__main__":
    unittest.main()
