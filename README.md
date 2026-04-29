# AI-Powered Job Application Automation System

An end-to-end AI system that automates job discovery, evaluates job fit, and generates tailored CVs and cover letters.

---

## Contact

For any inquiries or collaboration opportunities:

- :briefcase: [LinkedIn](https://www.linkedin.com/in/yusuf-kerim-ciger/)  

- :mailbox_with_mail: [Email](mailto:ykerimciger@gmail.com)

---

## Overview

This project is not just a job scraper.

It is a complete decision-making and application preparation system that:

- Finds relevant job opportunities
- Filters out low-quality or irrelevant roles
- Uses AI to evaluate whether applying is worthwhile
- Generates tailored CVs and cover letters automatically

The goal is to replicate and automate a real-world job search workflow using AI.

---

## Features

- Scrapes job listings from LinkedIn and Indeed using JobSpy
- Filters jobs based on role, seniority, and location
- Uses LLMs to evaluate job fit and application viability
- Assigns an "applicable rate" for each opportunity
- Dynamically selects top job opportunities
- Generates tailored CVs and cover letters in LaTeX
- Supports multi-location applications (UK / Turkey)
- Implements caching to reduce API cost and improve performance
- Automatically updates top jobs over time

---

## Architecture

```()
Job Search (JobSpy)
        ↓
Filtering & Scoring (Custom Logic)
        ↓
AI Evaluation (OpenAI API)
        ↓
Top Job Selection
        ↓
CV & Cover Letter Generation (LaTeX)
```

---

## Tech Stack

- Python
- OpenAI API
- Job scraping (JobSpy)
- LaTeX (for CV and cover letter generation)
- Automation & scheduling
- JSON-based data pipelines

---

## Example Workflow

1. The system fetches job listings from multiple sources  
2. Irrelevant and senior roles are filtered out  
3. AI evaluates each job and assigns a score  
4. The best opportunities are selected dynamically  
5. Tailored CVs and cover letters are generated for top jobs  

---

## Output

For each selected job, the system generates:

- Tailored CV (`.tex` and `.pdf`)
- Tailored Cover Letter (`.tex` and `.pdf`)

Example:

```()
outputs/applications/
└── Adaptive_Financial_Consulting/
    ├── Yusuf_Ciger_CV_Adaptive_Financial_Consulting.pdf
    ├── Yusuf_Ciger_Cover_Letter_Adaptive_Financial_Consulting.pdf
```

---

## Why This Project?

Job searching is repetitive, time-consuming, and inefficient.

This project demonstrates how AI can be used to:

- Automate decision-making  
- Improve application quality  
- Reduce manual effort  
- Build intelligent pipelines instead of simple scripts  

---

## Future Improvements

- Automated job application (Selenium / Playwright)  
- Email or Telegram notifications for high-score jobs  
- Dashboard for tracking applications and performance  
- Smarter CV patching instead of full regeneration  
- Deployment to VPS for continuous execution  

---

## Disclaimer

This project is intended for educational and automation purposes.

Always review generated CVs and cover letters before submitting applications.

---

## Author

Yusuf Ciger
