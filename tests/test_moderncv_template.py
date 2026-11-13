from __future__ import annotations

import unittest

from services.cv_template import parse_cv, render_cv
from services.document_generator import ApplicationDraft, escape_latex, ground_draft


CV = r"""%% Comment mentioning Kubernetes, which is not a skill of the candidate.
\documentclass[11pt,a4paper,sans]{moderncv}
\name{Old}{Name}
\address{Istanbul, Turkey}{}{}
\phone[mobile]{+90 000}
\email{old@example.com}
\begin{document}
\makecvtitle

\vspace{6pt}
\small{Data graduate who cut manual effort by 80\% at Amadeus.}

\section{Core Competencies}
\vspace{1pt}
\begin{itemize}

\item \textbf{Process Automation}: Python-based automation of manual reporting.

\item \textbf{Tools}: Python, SQL/MySQL, Microsoft Excel.

\end{itemize}

\section{Professional Experience}
\vspace{3pt}
\begin{itemize}

\item{\cventry{Mar 2026 - Apr 2026}{Sales Executive}{Field Sales}{London, UK}{}{\vspace{1pt}
\begin{itemize}
    \item Converted customer interest into agreements.
\end{itemize}}}

\vspace{3pt}

\item{\cventry{Jun 2023 - Aug 2023}{Engineering Intern}{Sabanc\i{} Tech}{Istanbul, Turkey}{}{\vspace{1pt}
\begin{itemize}
    \item Reduced manual reporting effort by 80\% using Python automation.
    \item Built Excel reporting outputs and validation pipelines for analysts.
\end{itemize}}}

\end{itemize}

\section{Projects}
\vspace{1pt}
\begin{itemize}

\item{\cventry{Mar 2026}{Job Automation System}{Independent project}{}{}{\vspace{1pt}
\begin{itemize}
    \item Built an LLM-based scoring system with the OpenAI API.
\end{itemize}}}

\end{itemize}

\section{Education}
\vspace{1pt}
\begin{itemize}

\item{\cventry{2024 - 2025}{MSc Data Science}{University of Sussex}{Brighton, UK}{}{\vspace{1pt}
Dissertation on forecasting with deep learning.
}}

\end{itemize}

\section{Languages}
\vspace{1pt}
\begin{itemize}
\item {Turkish (native), English (fluent).}
\end{itemize}

\section{Additional Information}
\vspace{1pt}
\begin{itemize}
\item {Full right to work in the UK (Graduate Visa).}
\end{itemize}

\end{document}
"""

CONTACT = {"name": "Yusuf Kerim Ciger", "address": "Istanbul, Türkiye", "phone": "+90 111", "email": "new@example.com", "linkedin": "", "right_to_work": ""}
JOB = {"title": "Junior Data Analyst", "company": "Acme", "location": "Istanbul", "description": "SQL and Excel reporting."}


class ModernCvTemplateTests(unittest.TestCase):
    def setUp(self):
        self.template = parse_cv(CV)
        self.by_title = {b.heading.split(" | ")[0]: b for b in self.template.blocks}

    def test_parse_finds_entries_summary_and_locks(self):
        sales, intern = self.by_title["Sales Executive"], self.by_title["Engineering Intern"]
        self.assertTrue(sales.droppable and intern.droppable)
        self.assertIn("Sabancı Tech", intern.heading)
        self.assertIn("Jun 2023 - Aug 2023", intern.heading)
        self.assertEqual(len(intern.bullets), 2)
        self.assertTrue(self.by_title["Job Automation System"].droppable)
        self.assertTrue(self.by_title["Core Competencies"].editable)
        self.assertFalse(self.by_title["Core Competencies"].droppable)
        self.assertFalse(self.by_title["Languages"].editable)
        self.assertFalse(self.by_title["Additional Information"].editable)
        self.assertEqual(self.template.summary, "Data graduate who cut manual effort by 80% at Amadeus.")
        self.assertTrue(all(b.bullets for b in self.template.blocks))  # no empty wrapper blocks
        self.assertNotIn("Kubernetes", self.template.plain_text)  # comments are not CV facts

    def test_render_drops_entries_sections_and_replaces_header(self):
        sales, project = self.by_title["Sales Executive"], self.by_title["Job Automation System"]
        skills = self.by_title["Core Competencies"]
        tools, automation = skills.bullets[1], skills.bullets[0]
        tex = render_cv(
            self.template,
            summary="Data graduate targeting the Junior Data Analyst role.",
            block_plans={
                sales.id: (False, []),
                project.id: (False, []),
                skills.id: (True, [(tools.id, "Tools: SQL/MySQL, Microsoft Excel, Python."), (automation.id, automation.text)]),
            },
            contact=CONTACT,
            escape=escape_latex,
        )
        self.assertNotIn("Sales Executive", tex)
        self.assertIn("Engineering Intern", tex)
        self.assertNotIn(r"\section{Projects}", tex)  # its only entry was dropped
        self.assertNotIn("Additional Information", tex)  # right-to-work removed, nothing left
        self.assertIn(r"\section{Languages}", tex)
        self.assertIn(r"\name{Yusuf Kerim}{Ciger}", tex)
        self.assertIn(r"\address{Istanbul, Türkiye}{}{}", tex)
        self.assertIn(r"\email{new@example.com}", tex)
        self.assertIn(r"\small{Data graduate targeting the Junior Data Analyst role.}", tex)
        self.assertIn(r"\item \textbf{Tools}: SQL/MySQL, Microsoft Excel, Python.", tex)  # label stays bold
        self.assertLess(tex.index(r"\textbf{Tools}"), tex.index(r"\textbf{Process Automation}"))
        self.assertEqual(tex.count(r"\begin{itemize}"), tex.count(r"\end{itemize}"))
        self.assertEqual(tex.count("{"), tex.count("}"))
        # Contact icons are font glyphs that an ATS reads as stray letters: switched off.
        self.assertLess(tex.index(r"\def\emailsymbol{}"), tex.index(r"\begin{document}"))

    def test_skill_lines_only_accept_terms_the_cv_states(self):
        skills, intern = self.by_title["Core Competencies"], self.by_title["Engineering Intern"]
        automation, tools = skills.bullets
        draft = ApplicationDraft(
            summary="",
            blocks=[
                {"id": skills.id, "keep": True, "bullets": [
                    # "validation pipelines" and "OpenAI API" are stated in other entries: allowed.
                    {"id": automation.id, "text": "Process Automation: Python-based automation and validation pipelines."},
                    # Tableau and dashboards appear nowhere in the CV: reverted.
                    {"id": tools.id, "text": "Tools: Python, SQL/MySQL, tableau dashboards."},
                ]},
                {"id": intern.id, "keep": True, "bullets": [
                    # A skill from another entry may not move into this one.
                    {"id": intern.bullets[0].id, "text": "Reduced manual reporting effort by 80% using the OpenAI API."},
                ]},
            ],
            cover_opening="", cover_key_fit=[], cover_closing="",
        )
        grounded, fixes = ground_draft(draft, self.template, JOB, {"assessment": {"requirements": []}})
        plans = grounded["block_plans"]
        self.assertIn("validation pipelines", plans[skills.id][1][0][1])
        self.assertEqual(plans[skills.id][1][1][1], tools.text)
        self.assertEqual(plans[intern.id][1][0][1], intern.bullets[0].text)

    def test_projects_may_all_be_dropped_but_experience_may_not(self):
        sales, intern, project = (self.by_title[k] for k in ("Sales Executive", "Engineering Intern", "Job Automation System"))
        draft = ApplicationDraft(
            summary="",
            blocks=[{"id": b.id, "keep": False, "bullets": []} for b in (sales, intern, project)],
            cover_opening="", cover_key_fit=[], cover_closing="",
        )
        grounded, _ = ground_draft(draft, self.template, JOB, {"assessment": {"requirements": []}})
        plans = grounded["block_plans"]
        self.assertTrue(plans[sales.id][0] and plans[intern.id][0])
        self.assertFalse(plans[project.id][0])


if __name__ == "__main__":
    unittest.main()
