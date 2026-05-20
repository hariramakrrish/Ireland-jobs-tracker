#!/usr/bin/env python3
"""
Generate tailored PDF resumes for every job in web/data/jobs.json.

Primary path  : Google Gemini API (gemini-2.5-flash-lite) with the elite
                recruiter system prompt generates unique bullets / skills /
                projects per job, using the stored JD + title + company.
                Requires GEMINI_API_KEY env var.

Fallback path : Static role-based content banks (no API key needed). Used when
                the API key is absent or the API call fails.

Layout: Vishnu-format, Times font, A4.
"""
import os, re, json, time
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                 Table, TableStyle, HRFlowable, PageBreak)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE   = os.path.join(ROOT, "web", "data", "jobs.json")
RESUME_DIR  = os.path.join(ROOT, "web", "resumes")
os.makedirs(RESUME_DIR, exist_ok=True)

BLACK = colors.HexColor("#000000")

# ── Try to import google-genai (optional dep) ─────────────────────────────────
try:
    from google import genai as _genai
    from google.genai import types as _genai_types
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


# ── Elite recruiter system prompt (sent on every Gemini call) ─────────────────
ELITE_SYSTEM_PROMPT = """You are an elite, executive-level technical recruiter specializing in matching software engineers and data analysts with high-tier banking, fintech, and enterprise tech positions. Your task is to analyze the user's canonical profile (HARI_PROFILE) and a specific Job Description (JD), then output perfectly tailored resume content.

CRITICAL WRITING STYLE RULES:
1. NO AI FLUFF OR BUZZWORDS: Absolutely never use the words 'spearheaded', 'leveraged', 'leveraging', 'utilized', 'utilising', 'testament', 'revolutionized', 'fostered', 'dynamic', 'robust', 'driven', 'cutting-edge', or 'proven track record'. If you use any of these, the generation is a failure.

1b. NEVER NAME THE HIRING COMPANY ANYWHERE IN THE RESUME. The JD is from a target company — do NOT mention that company's name in experience bullets, skills, or project names/bullets. Phrases like "customers on the Chalk platform", "built for Stripe", "JP Morgan Risk Engine" are dead giveaways. Hari worked at HCL Technologies, not at the hiring company. Refer to customers/products only in generic terms ("enterprise customers", "the ML platform", "internal feature store", etc.).
2. NATURAL BULLET WRITING: Lead each bullet with a strong past-tense verb, never repeating a starting verb in the same resume. Where a metric is plausible, include it — but do NOT force a number into every bullet. Forced metrics on every line read as AI-generated; real engineers measure some of their work, not all of it. Aim for ~50% of bullets carrying a specific metric, the rest describing scope/responsibility cleanly without a number.
3. ABSOLUTE TRUTH: Anchor all bullet points and projects directly to the 5 real experience domains explicitly detailed in HARI_PROFILE (HCL enterprise SWE, HCL financial-services operations dashboard, HCL ERP/business-systems support, MSc Data Analytics, Power BI). Never hallucinate client names, tech stacks, or metrics not grounded in his real background.
4. ATS KEYWORD MATCHING — SKILLS ARRAY MUST BE COMPLETE: The skills array is the ATS keyword sink — it MUST contain EVERY technical skill, tool, language, framework, methodology, or named technology mentioned in the JD, in the JD's exact spelling (no synonyms). This is the one place where 100% JD coverage is required, even for the JD points that experience bullets deliberately skip under the 75-80% rule. If the JD names TypeScript, Node.js, NestJS, Rust, Kubernetes, PostgreSQL, Power BI, ML Ops — every one of those goes into the skills array. The experience bullets can be selective; the skills array cannot.

5. DOMAIN ISOLATION — CRITICAL ANTI-LEAKAGE RULE:
   You are GLOBALLY FORBIDDEN — for EVERY JD, including banking/payments/fintech
   JDs — from using ANY of these terms anywhere in the output: "SWIFT", "MT103",
   "MT/MX", "MT 103", "ISO 20022", "ISO20022", "SEPA", "PSD2", "Open Banking",
   "tokenization", "cross-border payments", "instant payments", "BFSI". These
   are over-specific banking-standard names that are not credible for a
   3.5-year engineer and make the resume sound fabricated.

   Reframe the HCL work generically as what it actually was: production
   support and feature work on a financial-services operations dashboard
   (Java/Spring Boot, Python automation, SQL across PostgreSQL/Oracle/MySQL,
   AWS, Linux, Jenkins, Splunk/Dynatrace observability, incident response,
   change management). It is fine to say "financial-services dashboard",
   "payments operations dashboard", "transaction monitoring", "reconciliation
   workflows", "audit trails", "regulatory/GDPR-aware production environment"
   — those describe the work without name-dropping standards.

   If the JD's domain is not Power BI / data analytics / BI dashboards, do not
   lead with Power BI / Tableau / DAX. They go in skills only if the JD
   genuinely calls for analytics.

   For IoT, cloud-platform, frontend, or generic-backend roles, reframe HCL
   work as the GENERIC engineering it actually was (Java/Python/Spring Boot/
   Linux/AWS/SQL/CI/CD/production support) without naming the banking client.

6. PROJECT-DOMAIN MATCH: Both projects in the 'projects' array must be on-topic
   for the JD. For an IoT / device backend JD, both projects should be about
   distributed systems, real-time networking, event-driven backends, device
   fleet management, etc. — NOT "Payment Processing and Reconciliation". Invent
   project names and bullets that match the JD's domain, anchored to plausibly-
   extended HCL/SWE work.

FEW-SHOT TRAINING EXAMPLES:

Example 1 (Payments operations dashboard — banking JD)
- JD Requirement: 'Experience handling financial message queues, payment workflows, or transaction monitoring.'
- POOR AI OUTPUT: 'Leveraged SWIFT messaging and ISO 20022 standards to handle financial data safely and dynamically.'  ← FORBIDDEN: never name SWIFT, MT103, ISO 20022, SEPA, PSD2.
- POOR AI OUTPUT 2: 'Built consumers for a payments dashboard, sustaining 99.9% processing uptime across high-volume workflows.'  ← FORBIDDEN: 99.9% is a banned metric (HC-4).
- EXCELLENT TAILORED OUTPUT: 'Built fault-tolerant Java consumers for a payments operations dashboard, parsing inbound transaction messages and surfacing alerting for ~3,200 failed payments per week across the team's monitored queues.'

Example 2 (Data Engineering / Optimization — analytics JD)
- JD Requirement: 'Strong SQL skills and ability to optimize database query performance for large datasets.'
- POOR AI OUTPUT: 'Spearheaded the optimization of SQL database queries to make data processing fast.'
- EXCELLENT TAILORED OUTPUT: 'Refactored inefficient relational database queries and implemented strategic indexing, reducing analytical report execution times by 34% across core ERP database clusters.'

Example 3 (IoT / Device Backend — NON-banking JD, demonstrates domain isolation)
- JD Requirement: 'Device identity, authentication and security; large-scale Linux device fleet management; TypeScript (Node.js / NestJS), PostgreSQL, Rust, Kubernetes.'
- POOR AI OUTPUT (banking-leakage failure): 'Implemented device identity, authentication, and security using ISO 20022 and SEPA standards to ensure 100% compliance.'  ← ISO 20022 and SEPA are BANKING standards, completely irrelevant to IoT device auth. This is the exact failure mode to avoid.
- EXCELLENT TAILORED OUTPUT: 'Designed mutual-TLS device identity and certificate rotation for a 5,000-node Linux controller fleet, integrating short-lived tokens issued by a NestJS auth service backed by PostgreSQL, eliminating credential drift incidents across rolling fleet updates.'

Example 4 (ML feature platform — customer-facing engineering JD, demonstrates HC-1 + HC-2 compliance)
- JD: 'Forward Deployed Engineer at an ML feature-platform startup. Build feature pipelines for customers in fraud, recommendations, healthcare. Work pre-sales and post-sales with customer engineering teams. Python, SQL, ML/MLOps a plus.'

- POOR AI OUTPUT (HC-1 + HC-2 failure — dashboards default, no model, weak customer signal):
    bullets[0]: 'Built interactive Power BI dashboards for stakeholders, improving decision-making speed by 20%.'
    bullets[1]: 'Engineered Python pipelines to ingest data for ML model training.'
    bullets[2]: 'Collaborated with cross-functional teams to deliver features.'
    projects[0]: 'Customer Feature Pipeline Implementation — built a Python pipeline to ingest data for ML training, integrated with AWS, collaborated with client leads.'
    projects[1]: 'Interactive Sales Dashboard — Power BI dashboard, DAX measures, published to stakeholders.'
  ← FAILS HC-1: no model is actually trained anywhere, no AUC / precision / accuracy. FAILS HC-2: only "cross-functional teams" and "client leads" — too vague.

- EXCELLENT TAILORED OUTPUT (passes HC-1 + HC-2):
    bullets[0]: 'Acted as primary technical contact during onboarding for three enterprise customers, gathering feature-pipeline requirements directly with their data science teams and translating them into Python implementations.'  ← HC-2 ✓
    bullets[1]: 'Trained a gradient-boosted classifier (scikit-learn) on a ~280k-row labelled transactions dataset to flag suspicious activity for an internal anti-abuse workflow, reaching ~0.86 AUC on held-out data.'  ← HC-1 ✓
    bullets[2]: 'Built Python feature pipelines on AWS Lambda + S3 to power downstream ML scoring, handling roughly 3,500 events/sec at the peak hour and replacing a brittle scheduled-batch job.'
    bullets[3]: 'Ran post-sales technical demos and walkthrough sessions for two customer engineering teams adopting our internal ML platform, including pair-debugging integration issues during their first month in production.'  ← HC-2 ✓
    bullets[4]: 'Designed and shipped REST APIs in Java Spring Boot for cross-service data exchange between the feature store and consumer applications, including request validation and circuit-breaker patterns.'
    bullets[5]: 'Wrote production runbooks and internal documentation that the customer onboarding team now uses to bring new clients live in ~10 days instead of 4+ weeks.'  ← HC-2 ✓
    bullets[6]: 'Containerised the feature-pipeline services with Docker and deployed them to a Kubernetes cluster (EKS), wiring up Helm chart configuration and basic resource limits for predictable rollout.'  ← HC-5 7th-bullet ✓

    projects[0] (Customer Onboarding Playbook for an ML Feature Store):
      'Worked directly with two pilot customers to design and ship a guided onboarding flow for an internal ML feature store, including SDK examples, debug tooling, and a checklist that compressed time-to-first-feature from ~6 weeks to 9 days.'
      'Built a Python CLI to validate customer feature definitions against the platform schema before submission, catching ~70% of schema errors at write time instead of at training time.'
      'Documented common integration patterns and ran two follow-up workshops with the customer data teams to upskill their internal engineers.'  ← HC-2 ✓ (customer-facing project)

    projects[1] (Fraud-Detection Model on Transaction Features):
      'Engineered a feature pipeline in Python and SQL to extract behavioural signals (velocity, geo-distance, device-fingerprint) from a transaction log of roughly 1.1M records.'
      'Trained a LightGBM classifier on the resulting features, tuning class weights to handle the 1:140 fraud imbalance and reaching ~0.91 AUC / 0.46 F1 on a held-out month.'  ← HC-1 ✓ (real model + real metrics)
      'Packaged the model behind a FastAPI inference endpoint with input validation, p95 latency around 180ms, and basic feature-drift logging.'

OUTPUT CONFIGURATION:
You must return your output strictly in a raw JSON object matching the keys: 'bullets' (array of exactly 7 strings), 'skills' (array of 5-7 strings, each in the format "<b>Category</b>  –  item1, item2, item3."), and 'projects' (array of exactly 2 objects, each with keys 'title' (string) and 'bullets' (array of 3 strings)). Do not wrap the JSON in markdown code blocks or add any conversational introduction or conclusion text."""

# ═══════════════════════════════════════════════════════════════════
# HARI'S PROFILE  (injected into every AI prompt)
# ═══════════════════════════════════════════════════════════════════
HARI_PROFILE = """
Candidate: Hariramakrrishnan Ramachandran
Location: Dublin, Ireland  |  Visa: Stamp 1G (eligible to work full-time)

Work Experience (3.5 years total):
  HCL Technologies, Chennai, India — Software Engineer  (Sep 2021 – Jan 2025)
  Day-to-day responsibilities:
    • Production support & monitoring of enterprise Java/.NET applications using
      Splunk, CloudWatch, Dynatrace — SLA management, P1/P2 incident response
    • Python scripting for automation, data pipelines, ETL, and scheduled reporting
    • SQL (PostgreSQL, MySQL, Oracle) — ad-hoc queries, data validation, schema changes
    • Java Spring Boot — feature work, bug fixes, REST API development on existing services
    • AWS — EC2, S3, Lambda, CloudWatch; Docker (containerisation basics)
    • CI/CD — Jenkins pipelines, Git branching, code reviews
    • Jira, Confluence — ticketing, defect tracking, Agile/Scrum ceremonies
    • Linux — log analysis, shell scripting, cron jobs

  Financial-Services domain experience at HCL (describe generically — never
  name SWIFT, MT/MX, MT103, ISO 20022, SEPA, PSD2, Open Banking, tokenization):
    • Worked on a payments operations dashboard supporting a financial-services
      client — production support, transaction-flow monitoring, and operational
      alerting for failed/stuck payment messages.
    • Production environments with strict SLAs, audit trails, and regulatory /
      GDPR awareness.
    • Cross-functional collaboration with operations teams and business analysts
      for requirements gathering, UAT support, and post-implementation triage.
    • Familiarity with payments processing flows, reconciliation workflows,
      and transaction monitoring (described in generic terms, no standard names).

  ERP & Enterprise Business Systems exposure at HCL:
    • Supported and integrated with enterprise business systems including ERP
      modules and operational platforms used by the banking client.
    • Change-control management for system configuration updates, UAT coordination,
      and post-go-live support across interconnected systems.
    • Cross-system integrations via REST APIs and database-level data flows
      across PostgreSQL / Oracle / MySQL.

  MSc in Data Analytics (NCI, Dublin) — coursework & applied skills:
    • Power BI — dashboards, DAX measures, data modelling, Power Query for ETL,
      published reports for business stakeholders.
    • Tableau — interactive dashboards and data visualisation.
    • R / RStudio — statistical analysis, regression, hypothesis testing.
    • Python data stack — pandas, NumPy, scikit-learn for analytics & modelling.
    • SQL / data warehousing / ETL — applied across coursework projects.
    • Statistical methods, exploratory data analysis, A/B testing, time-series.
    • Machine learning fundamentals — supervised / unsupervised, evaluation metrics.
    • Big-data exposure — Hadoop / Spark concepts via MSc curriculum.
    • Business Intelligence theory and applied dashboard development.

Education:
  • MSc in Data Analytics — National College of Ireland, Dublin (COMPLETED Feb 2026)
  • Bachelor of Engineering (BE) in Computer Science — SNS College of Technology, Coimbatore, India (2021)

Certifications:
  • IELTS Academic: Band 7/9
  • Full Stack Java Spring Boot & Angular (Great Learning)
  • Web Development — University of California, Davis (Coursera)
  • Python Programming — University of Michigan (Coursera)

Key technologies:
  Python, Java, SQL, Spring Boot, REST APIs, AWS (EC2/S3/Lambda/CloudWatch),
  Docker, Linux, Git, Jenkins, Jira, Confluence, PostgreSQL, MySQL, Oracle,
  Splunk, Dynatrace, pandas, NumPy, scikit-learn, Flask, FastAPI, React, Angular,
  Power BI, Tableau, R / RStudio, DAX, Power Query, data modelling, data warehousing,
  payments operations dashboards, transaction monitoring, reconciliation workflows,
  ERP integration support, change-management.
"""

# ═══════════════════════════════════════════════════════════════════
# STATIC FALLBACK CONTENT BANKS
# ═══════════════════════════════════════════════════════════════════
CERTS = [
    "IELTS Academic: Overall Band Score <b>7 out of 9</b>, issued by IELTS Official, Test Date: 28/AUG/2023",
    "<b>Full Stack: Java Spring Boot</b> and Angular  (Great Learning)",
    "Certificate of Completion in Web Development from <b>University of California</b>, Davis (Coursera)",
    "Certificate of Completion in Python programming from <b>University of Michigan</b> (Coursera)",
]

CONTENT = {
"java": {
    "bullets": [
        "Designed and developed scalable backend <b>microservices in Java 11/17 and Spring Boot</b> for high-traffic enterprise systems, contributing to a <b>25% reduction in system response time</b> across key service endpoints.",
        "Built and maintained <b>RESTful APIs</b> enabling seamless integration between internal applications and third-party systems, ensuring reliable, secure, and auditable data exchange across distributed services.",
        "Led query optimisation initiatives across <b>PostgreSQL, MySQL, and MongoDB</b>, implementing targeted indexing strategies and execution plan analysis, improving data processing efficiency by <b>40%</b>.",
        "Implemented <b>Spring Security and OAuth2</b> authentication patterns for API security, hardening service-to-service communication in line with enterprise security standards.",
        "Collaborated with cross-functional teams including QA engineers, product owners, and architects to deliver backend features in an <b>Agile/Scrum</b> environment with two-week sprint cycles.",
        "Supported application deployments on <b>AWS (EC2, S3, CloudWatch)</b> using Docker and Kubernetes, contributing to a <b>35% reduction in system downtime</b> through proactive monitoring.",
        "Drove <b>CI/CD pipeline improvements</b> using Jenkins and Git, reducing deployment lead time by 30% through automated build, test, and release workflows.",
        "Wrote comprehensive unit and integration tests using <b>JUnit and Mockito</b>, achieving over 80% code coverage and catching regression defects before production deployments.",
    ],
    "skills": [
        "<b>Technologies</b>  –  Spring Boot, Microservices architecture, REST APIs, and backend service design.",
        "<b>Programming Languages</b>  –  Proficient in Java 11/17, Python, SQL, and Bash scripting.",
        "<b>Databases</b>  –  PostgreSQL, MySQL, and MongoDB; query optimisation, indexing, and performance tuning.",
        "<b>Cloud &amp; DevOps</b>  –  AWS (EC2, S3, Lambda, CloudWatch), Docker, Kubernetes, and CI/CD pipeline management.",
        "<b>Frameworks &amp; APIs</b>  –  Spring Boot, Spring Cloud, Spring Data JPA, Spring Security, OAuth2, and API gateway.",
        "<b>Development Practices</b>  –  Agile/Scrum, Git, automated testing with JUnit and Mockito, code reviews, TDD.",
        "<b>Tools &amp; IDEs</b>  –  IntelliJ IDEA, Eclipse, Postman, Jenkins, Visual Studio Code.",
    ],
    "projects": [
        ("Customer Account Management API – Backend Development (HCL Technologies)", [
            "Designed and implemented RESTful API endpoints in Java and Spring Boot for customer account operations including profile updates, JWT-based authentication, and transaction history retrieval.",
            "Implemented input validation, exception handling, and standardised response structures across all endpoints, reducing API error rates by 20% and improving consistency for consuming teams.",
            "Wrote comprehensive unit and integration tests using JUnit and Mockito, achieving over 80% code coverage and identifying edge-case defects before production release.",
        ]),
        ("Notification & Alerting Microservice (HCL Technologies)", [
            "Built a standalone Spring Boot microservice for sending email and in-app notifications triggered by downstream service events via REST API, decoupling notification logic from core business services.",
            "Implemented retry logic and dead-letter queue handling for failed dispatches, ensuring no critical alerts were silently dropped under transient network failures.",
            "Containerised the service with Docker and validated end-to-end behaviour in a staging Kubernetes environment.",
        ]),
    ],
},
"full_stack": {
    "bullets": [
        "Developed full-stack web applications using <b>Java Spring Boot</b> (REST API backend) and <b>React/Angular</b> (frontend), delivering responsive interfaces and robust data flows for enterprise users.",
        "Designed and maintained RESTful APIs integrating backend services with third-party platforms, improving cross-system data exchange reliability and reducing integration errors by <b>30%</b>.",
        "Built reusable frontend components and implemented state management patterns, improving UI consistency and reducing development time across features by <b>25%</b>.",
        "Worked with <b>PostgreSQL and MongoDB</b> to design efficient schemas, optimise queries, and improve data retrieval speed by 40% for high-traffic transactional workloads.",
        "Implemented <b>JWT-based authentication and role-based access control (RBAC)</b> across full-stack features, ensuring secure data access at both API and UI layers.",
        "Collaborated with UX designers, product owners, and QA engineers in <b>Agile/Scrum</b> sprints to deliver end-to-end features with high quality and on schedule.",
        "Deployed applications on <b>AWS (EC2, S3)</b> with Docker containerisation; maintained Jenkins CI/CD pipelines, reducing deployment lead time by <b>35%</b>.",
        "Wrote unit and end-to-end tests using <b>JUnit, Mockito, and Jest</b>, achieving 80%+ code coverage and maintaining stable releases across frontend and backend layers.",
    ],
    "skills": [
        "<b>Backend</b>  –  Java 11/17, Spring Boot, Spring Cloud, REST APIs, Microservices, Spring Security.",
        "<b>Frontend</b>  –  React, Angular, JavaScript (ES6+), HTML5, CSS3, TypeScript.",
        "<b>Databases</b>  –  PostgreSQL, MySQL, MongoDB; query optimisation and data modelling.",
        "<b>Cloud &amp; DevOps</b>  –  AWS (EC2, S3, Lambda), Docker, Kubernetes, Jenkins, CI/CD pipelines.",
        "<b>Testing</b>  –  JUnit, Mockito, Jest, React Testing Library, TDD practices.",
        "<b>Development Practices</b>  –  Agile/Scrum, Git, code reviews, API design patterns.",
        "<b>Tools &amp; IDEs</b>  –  IntelliJ IDEA, VS Code, Postman, Jira, Confluence.",
    ],
    "projects": [
        ("Customer Portal – Full Stack Application (HCL Technologies)", [
            "Developed a full-stack customer portal using Spring Boot (REST APIs) and Angular (frontend) supporting profile management, transaction history, and real-time notification features for 10,000+ users.",
            "Implemented JWT authentication and role-based access control ensuring secure, auditable access to sensitive account data across all portal features.",
            "Deployed the application on AWS EC2 with Docker containerisation; maintained CI/CD pipeline with Jenkins, automating build and deployment to staging and production.",
        ]),
        ("Internal Admin Dashboard (HCL Technologies)", [
            "Built a responsive admin dashboard with React and Spring Boot providing real-time data views via REST APIs, reducing operational reporting time by 40% for internal teams.",
            "Designed reusable component library and state management patterns, improving UI consistency and reducing frontend development effort for new modules.",
        ]),
    ],
},
"python": {
    "bullets": [
        "Developed <b>Python-based data pipelines and ETL scripts</b> using pandas, SQLAlchemy, and PySpark to automate data extraction and transformation, reducing manual processing time by <b>45%</b>.",
        "Built <b>RESTful APIs using Flask and FastAPI</b>, integrating them with AWS services and PostgreSQL, enabling efficient data exchange between internal tools and third-party platforms.",
        "Designed and maintained backend services in <b>Java and Spring Boot</b>, contributing to a 25% improvement in system response time and supporting clean data pipelines for downstream consumers.",
        "Worked with <b>PostgreSQL, MySQL, and MongoDB</b> to optimise queries and improve data retrieval efficiency by 40% for analytics-driven workloads.",
        "Implemented <b>automated testing frameworks using pytest</b> and unittest, achieving 80%+ code coverage and significantly reducing regression defects in Python-based services.",
        "Deployed Python services on <b>AWS (EC2, Lambda, S3)</b> using Docker, and managed batch job scheduling with Jenkins and cron for reliable daily processing.",
        "Collaborated with data scientists and analysts in an <b>Agile/Scrum</b> environment to translate data requirements into robust, production-ready Python pipelines and APIs.",
        "Wrote clean, modular Python code following <b>PEP8 standards</b>, enabling maintainability and easy onboarding of new developers across the team.",
    ],
    "skills": [
        "<b>Programming Languages</b>  –  Python (advanced), Java, SQL, Bash scripting.",
        "<b>Python Ecosystem</b>  –  pandas, NumPy, Flask, FastAPI, SQLAlchemy, PySpark, pytest.",
        "<b>Backend &amp; APIs</b>  –  Spring Boot, REST API design, microservices, API integration.",
        "<b>Databases</b>  –  PostgreSQL, MySQL, MongoDB; query optimisation and schema design.",
        "<b>Cloud &amp; DevOps</b>  –  AWS (EC2, S3, Lambda), Docker, Jenkins, CI/CD pipelines.",
        "<b>Development Practices</b>  –  Agile/Scrum, Git, TDD, code reviews, clean code principles.",
        "<b>Tools</b>  –  VS Code, Jupyter Notebook, Postman, PyCharm, IntelliJ IDEA.",
    ],
    "projects": [
        ("Automated ETL Data Pipeline (HCL Technologies)", [
            "Built a Python-based ETL pipeline using pandas and SQLAlchemy to automate data extraction from multiple sources and load into PostgreSQL, reducing manual effort by 45%.",
            "Containerised the pipeline with Docker and scheduled automated daily runs via Jenkins, with error alerting and retry logic ensuring reliable and consistent data delivery.",
        ]),
        ("Internal REST API Service (HCL Technologies)", [
            "Developed a FastAPI-based REST service exposing processed internal data to downstream teams; integrated with AWS S3 for file storage and PostgreSQL for persistent data management.",
            "Implemented request validation, exception handling, and structured logging, reducing API error rates and improving observability for the operations team.",
        ]),
    ],
},
"data_analyst": {
    "bullets": [
        "Designed and maintained <b>interactive dashboards and reports</b> using SQL, Python, and Power BI, enabling business stakeholders to track KPIs and make data-driven decisions in real time.",
        "Performed end-to-end data analysis including data extraction, cleaning, statistical analysis, and visualisation using <b>Python (pandas, matplotlib, seaborn)</b>, reducing reporting cycle time by <b>30%</b>.",
        "Developed and optimised complex <b>SQL queries and stored procedures</b> in PostgreSQL and MySQL to support analytical reporting workloads, improving query execution speed by 40%.",
        "Built <b>automated data validation and reconciliation scripts</b> in Python, replacing manual weekly QA processes and reducing data quality incidents by 35%.",
        "Collaborated closely with business stakeholders and engineering teams in an <b>Agile/Scrum</b> environment to define metrics, validate data sources, and deliver analytical solutions.",
        "Worked with <b>PostgreSQL and MongoDB</b> to design efficient data models supporting high-volume analytical queries, applying indexing and partitioning strategies.",
        "Maintained <b>backend services in Java and Spring Boot</b> that powered data ingestion and transformation pipelines, enabling cleaner and more reliable data for downstream analysis.",
        "Documented analytical methodologies and KPI definitions, establishing a <b>governed data layer</b> enabling controlled self-service analytics across business functions.",
    ],
    "skills": [
        "<b>Analytics &amp; Visualisation</b>  –  Python (pandas, NumPy, matplotlib, seaborn), Power BI, Tableau, Advanced Excel.",
        "<b>SQL &amp; Databases</b>  –  PostgreSQL, MySQL, MongoDB; complex queries, stored procedures, indexing, and performance tuning.",
        "<b>Programming Languages</b>  –  Python, SQL, Java, Bash scripting.",
        "<b>Data Engineering</b>  –  ETL pipelines, data cleaning, transformation, and validation frameworks.",
        "<b>Backend</b>  –  Java Spring Boot, REST APIs, data ingestion services.",
        "<b>Cloud &amp; Tools</b>  –  AWS (S3, Redshift), Docker, Jenkins, Git, Jira.",
        "<b>Development Practices</b>  –  Agile/Scrum, data governance, documentation, statistical analysis.",
    ],
    "projects": [
        ("Business Performance Dashboard (HCL Technologies)", [
            "Designed and built an interactive Power BI dashboard consolidating data from multiple SQL sources, enabling stakeholders to monitor KPIs in real time and reduce report generation time by 30%.",
            "Automated data extraction and transformation using Python and SQL stored procedures, eliminating 10+ hours of manual weekly reporting and improving data accuracy.",
        ]),
        ("Customer Data Quality & Reporting Pipeline (HCL Technologies)", [
            "Performed exploratory data analysis and statistical profiling on customer transaction datasets (1M+ records) using Python and SQL to identify data quality issues and surface actionable insights.",
            "Built reusable data validation and cleaning scripts, reducing downstream analysis errors by 25% and improving report reliability consumed by senior leadership.",
        ]),
    ],
},
"data_scientist": {
    "bullets": [
        "Built and deployed <b>machine learning models</b> (classification, regression, clustering) using Python (scikit-learn, pandas, NumPy), generating predictive insights from large structured datasets.",
        "Designed <b>feature engineering and data preprocessing pipelines</b>, improving model accuracy by 18% through structured experimentation and cross-validation techniques.",
        "Developed a <b>customer churn prediction model</b> using gradient boosting and logistic regression, achieving 87% AUC and enabling proactive targeting of at-risk customer segments.",
        "Built and orchestrated <b>model training and evaluation pipelines</b> with MLflow experiment tracking, ensuring reproducibility and version control across model iterations.",
        "Integrated <b>model outputs into backend services</b> via REST APIs built in Java Spring Boot, enabling real-time inference and decision-support for operational teams.",
        "Worked with <b>PostgreSQL and MongoDB</b> to design efficient data extraction workflows and optimise pipeline throughput by 40% for large-scale data science projects.",
        "Collaborated with data engineers, analysts, and business stakeholders in <b>Agile/Scrum</b> sprints to translate business problems into machine learning solutions.",
        "Communicated model performance and business impact clearly to <b>technical and non-technical audiences</b>, driving informed adoption of data science recommendations.",
    ],
    "skills": [
        "<b>Machine Learning</b>  –  scikit-learn, regression, classification, clustering, gradient boosting, model evaluation.",
        "<b>Programming Languages</b>  –  Python (advanced), SQL, Java, R.",
        "<b>Python Ecosystem</b>  –  pandas, NumPy, matplotlib, seaborn, Flask, FastAPI.",
        "<b>Databases</b>  –  PostgreSQL, MySQL, MongoDB; data extraction and pipeline design.",
        "<b>Cloud &amp; MLOps</b>  –  AWS (S3, EC2, SageMaker basics), Docker, MLflow, Jenkins.",
        "<b>Development Practices</b>  –  Agile/Scrum, Git, experiment tracking, model versioning.",
        "<b>Tools</b>  –  Jupyter Notebook, VS Code, Tableau, Power BI.",
    ],
    "projects": [
        ("Customer Churn Prediction Model (HCL Technologies)", [
            "Built a gradient boosting classification model to predict customer churn risk from structured transactional data, achieving 87% AUC and enabling proactive customer retention targeting.",
            "Designed feature engineering pipeline including categorical encoding, normalisation, and lag-based temporal features, improving model accuracy by 18% over baseline.",
            "Deployed model outputs via a FastAPI REST endpoint consumed by the CRM team for real-time risk scoring at point-of-contact.",
        ]),
        ("Sales Forecasting & Demand Analysis Pipeline (HCL Technologies)", [
            "Built an end-to-end forecasting pipeline using Python and scikit-learn to predict monthly demand across product categories, reducing inventory overstock by 12%.",
            "Automated data extraction from PostgreSQL and model retraining with Jenkins, ensuring weekly updated forecasts without manual intervention.",
        ]),
    ],
},
"ai_ml": {
    "bullets": [
        "Built and fine-tuned <b>NLP and ML models</b> using Python (scikit-learn, PyTorch, Hugging Face Transformers) for classification, entity extraction, and text generation tasks.",
        "Designed <b>end-to-end ML training and inference pipelines</b> with data preprocessing, feature engineering, model evaluation, and versioning using MLflow.",
        "Developed <b>LLM-powered automation scripts</b> using OpenAI and Hugging Face APIs, reducing manual document processing time by 40% for internal operations teams.",
        "Built <b>REST APIs with FastAPI and Flask</b> to serve ML model predictions as real-time microservices, integrated into Java Spring Boot-based backend systems.",
        "Worked with <b>PostgreSQL and AWS S3</b> to manage training datasets, feature stores, and model artefacts at scale, ensuring data lineage and reproducibility.",
        "Collaborated with product and data engineering teams in <b>Agile/Scrum</b> sprints to define ML problem framing, evaluation metrics, and production deployment criteria.",
        "Automated model retraining and evaluation workflows using <b>Jenkins and Python</b>, ensuring continuously updated models without manual pipeline intervention.",
        "Applied <b>prompt engineering and RAG (Retrieval Augmented Generation)</b> patterns to ground LLM outputs in domain-specific knowledge bases, improving answer accuracy by 35%.",
    ],
    "skills": [
        "<b>Machine Learning &amp; AI</b>  –  scikit-learn, PyTorch, Hugging Face Transformers, LLM APIs, RAG, NLP.",
        "<b>Programming Languages</b>  –  Python (advanced), SQL, Java, Bash scripting.",
        "<b>Python Ecosystem</b>  –  pandas, NumPy, Flask, FastAPI, LangChain, MLflow.",
        "<b>Databases &amp; Storage</b>  –  PostgreSQL, MySQL, AWS S3, vector databases (Pinecone basics).",
        "<b>Cloud &amp; MLOps</b>  –  AWS (EC2, S3, Lambda, SageMaker basics), Docker, Jenkins, CI/CD pipelines.",
        "<b>Development Practices</b>  –  Agile/Scrum, Git, experiment tracking, model versioning, prompt engineering.",
        "<b>Tools</b>  –  Jupyter Notebook, VS Code, Postman, Jira.",
    ],
    "projects": [
        ("LLM-Powered Document Classification & Extraction (HCL Technologies)", [
            "Built an NLP pipeline using Hugging Face Transformers to classify and extract structured data from unstructured support documents, reducing manual classification effort by 40%.",
            "Applied prompt engineering with OpenAI API to generate structured summaries from long-form technical reports, improving information retrieval speed for operations teams.",
            "Deployed the pipeline as a FastAPI microservice integrated into the existing Java Spring Boot backend, enabling real-time document processing.",
        ]),
        ("ML-Driven Anomaly Detection for Operational Monitoring (HCL Technologies)", [
            "Developed an anomaly detection system using scikit-learn (Isolation Forest, LSTM) to identify system metric deviations from historical baselines, reducing alert noise by 35%.",
            "Automated model retraining with Jenkins pipelines and stored artefacts in AWS S3, ensuring continuously updated detection thresholds without manual intervention.",
        ]),
    ],
},
"prod_support": {
    "bullets": [
        "Managed end-to-end production incident response for enterprise applications, achieving <b>99.5% SLA compliance</b> through structured triage, P1/P2 escalation, and cross-team war-room coordination.",
        "Developed <b>Python and Shell automation scripts</b> for routine operational tasks including log analysis, health checks, and automated restarts, reducing manual intervention by <b>60%</b>.",
        "Monitored distributed application infrastructure using <b>Splunk, CloudWatch, and Dynatrace</b>, identifying and resolving performance degradations before SLA breach.",
        "Performed <b>root cause analysis (RCA)</b> for major production incidents, documenting findings and implementing preventive fixes to reduce recurring incident rates by <b>45%</b>.",
        "Executed <b>database maintenance operations</b> in Oracle, PostgreSQL, and MySQL including schema migrations, performance tuning, and data fix scripts in production environments.",
        "Collaborated with development, QA, and infrastructure teams during <b>change and release management</b> cycles, ensuring smooth deployments with zero unplanned downtime.",
        "Built and maintained <b>operational dashboards in Grafana</b> consolidating application health, error rates, and SLA metrics, enabling proactive issue detection and reporting.",
        "Provided <b>Tier 2/3 technical support</b> to global stakeholders, managing tickets through ServiceNow and Jira and maintaining MTTR within SLA thresholds.",
    ],
    "skills": [
        "<b>Monitoring &amp; Observability</b>  –  Splunk, CloudWatch, Dynatrace, Grafana, PagerDuty, Prometheus.",
        "<b>Scripting &amp; Automation</b>  –  Python, Shell scripting, cron jobs, automated health checks.",
        "<b>Databases</b>  –  Oracle, PostgreSQL, MySQL; schema migrations, performance tuning, data fix scripts.",
        "<b>Cloud &amp; Infrastructure</b>  –  AWS (EC2, S3, Lambda, RDS, CloudWatch), Docker, Linux administration.",
        "<b>ITSM &amp; Processes</b>  –  ServiceNow, Jira; ITIL-aligned incident, change, and problem management.",
        "<b>Development</b>  –  Java, Spring Boot, REST APIs; application debugging and log analysis.",
        "<b>Development Practices</b>  –  Agile/Scrum, SLA management, RCA documentation, runbook authoring.",
    ],
    "projects": [
        ("Production Incident Automation & SLA Management (HCL Technologies)", [
            "Designed and deployed Python-based health-check and auto-recovery scripts reducing manual incident resolution effort by 60%, maintaining 99.5% SLA compliance across 15+ enterprise services.",
            "Built a Splunk alerting framework with custom dashboards tracking error rate trends, queue depths, and service latency, enabling proactive detection of degradation before customer impact.",
        ]),
        ("AWS Infrastructure Monitoring & Reliability (HCL Technologies)", [
            "Configured CloudWatch alarms and dashboards across EC2, RDS, and application tiers, enabling proactive detection of resource contention and service degradation.",
            "Supported on-call incident rotation, contributing to structured war-room coordination during major outages and driving resolution through systematic root cause analysis.",
        ]),
    ],
},
"it_support": {
    "bullets": [
        "Provided <b>Tier 1/2 IT support</b> across 500+ end-users, resolving hardware, software, network, and account management issues through ServiceNow ticketing within SLA.",
        "Managed <b>Active Directory, O365, and Azure AD</b> user accounts including onboarding, access provisioning, group policy management, and offboarding.",
        "Diagnosed and resolved <b>Windows 10/11 and macOS desktop issues</b> including OS configuration, software installations, driver conflicts, and network connectivity problems.",
        "Supported <b>network infrastructure troubleshooting</b> including LAN/WAN connectivity, VPN access, printer configuration, and wireless network issues.",
        "Developed <b>Python and PowerShell automation scripts</b> for repetitive IT tasks including user provisioning, patch status reporting, and disk cleanup, saving 5+ hours weekly.",
        "Maintained <b>hardware asset inventory</b> using CMDB tools, tracking equipment lifecycle, warranty status, and patch compliance across the estate.",
        "Collaborated with infrastructure and security teams for <b>patch management and antivirus deployment</b>, ensuring 100% endpoint compliance across managed devices.",
        "Documented technical procedures, known-error resolutions, and escalation paths in <b>Confluence knowledge base</b>, reducing resolution time for recurring issues by 30%.",
    ],
    "skills": [
        "<b>Desktop Support</b>  –  Windows 10/11, macOS, Active Directory, O365, Azure AD, Group Policy.",
        "<b>Networking</b>  –  LAN/WAN, VPN, TCP/IP, DNS, DHCP, wireless troubleshooting.",
        "<b>ITSM &amp; Tools</b>  –  ServiceNow, Jira, Confluence; ITIL-aligned incident and change management.",
        "<b>Scripting &amp; Automation</b>  –  Python, PowerShell, Bash; user provisioning and operational automation.",
        "<b>Cloud &amp; Infrastructure</b>  –  AWS basics, Azure AD, virtualisation (VMware basics), Docker.",
        "<b>Databases</b>  –  SQL queries for asset and reporting data; PostgreSQL, MySQL basics.",
        "<b>Development Practices</b>  –  Agile/Scrum, ITIL processes, asset management, documentation.",
    ],
    "projects": [
        ("IT Support Automation & Ticketing Improvement (HCL Technologies)", [
            "Developed Python and PowerShell scripts to automate user onboarding and offboarding in Active Directory, reducing provisioning time from 2 hours to under 10 minutes.",
            "Built a ServiceNow dashboard tracking SLA compliance and ticket ageing, enabling the support manager to identify bottlenecks and improve first-call resolution by 25%.",
        ]),
        ("Asset Management & Patch Compliance Initiative (HCL Technologies)", [
            "Designed and maintained CMDB asset records for 500+ endpoints, implementing automated patch status reporting that improved compliance visibility for the security team.",
            "Wrote Bash scripts to automate disk cleanup and log rotation on Linux servers, recovering 30% disk space and reducing performance-related tickets.",
        ]),
    ],
},
"sre_devops": {
    "bullets": [
        "Managed and monitored production infrastructure on <b>AWS (EC2, S3, CloudWatch, Lambda, RDS)</b>, ensuring 99.9%+ service availability and proactive SLA compliance through alert-driven incident response.",
        "Developed <b>Python and Shell automation scripts</b> for operational tasks including health checks, log aggregation, auto-recovery, and deployment validation, reducing manual effort by <b>60%</b>.",
        "Supported <b>CI/CD pipeline operations using Jenkins and Git</b>, contributing to automated build, test, and deployment workflows that reduced release lead time by 30%.",
        "Monitored distributed systems using <b>Splunk, Dynatrace, and CloudWatch</b>; built observability dashboards tracking error rates, latency, and throughput to detect degradation before SLA breach.",
        "Participated in <b>on-call incident response</b>, performing structured triage, root cause analysis (RCA), and post-incident reviews to reduce recurring P1/P2 incident frequency by 45%.",
        "Applied <b>containerisation with Docker</b> and contributed to Kubernetes-based service deployments, ensuring consistent application behaviour across dev, staging, and production environments.",
        "Worked with development and QA teams in <b>Agile/Scrum</b> ceremonies to implement reliability improvements, define SLI/SLO targets, and drive platform stability initiatives.",
        "Maintained infrastructure runbooks and incident playbooks in <b>Confluence</b>, improving team onboarding and reducing time-to-resolve for known failure patterns by 35%.",
    ],
    "skills": [
        "<b>Cloud &amp; Infrastructure</b>  –  AWS (EC2, S3, Lambda, RDS, CloudWatch, IAM, VPC), Docker, Kubernetes basics.",
        "<b>Monitoring &amp; Observability</b>  –  Splunk, CloudWatch, Dynatrace, Grafana, Prometheus basics, PagerDuty.",
        "<b>Scripting &amp; Automation</b>  –  Python, Bash/Shell scripting, cron jobs, automated health checks and recovery.",
        "<b>CI/CD &amp; DevOps</b>  –  Jenkins, Git, automated pipelines, build/test/deploy workflows.",
        "<b>Databases</b>  –  PostgreSQL, MySQL, Oracle; operational queries, schema migrations, performance tuning.",
        "<b>SRE Practices</b>  –  SLI/SLO/SLA management, incident response, RCA, runbook authoring, on-call.",
        "<b>Development</b>  –  Java Spring Boot, REST APIs, application debugging, log analysis.",
    ],
    "projects": [
        ("Production Reliability & Incident Automation (HCL Technologies)", [
            "Designed Python-based automated health-check and self-healing scripts reducing manual incident intervention by 60%, maintaining 99.5% SLA compliance across 15+ enterprise services.",
            "Built a Splunk alerting framework with custom dashboards tracking error rates, queue depths, and service latency, enabling proactive degradation detection before user impact.",
            "Participated in on-call rotation and war-room incident coordination, contributing structured RCA documentation that reduced repeat incident occurrence by 45%.",
        ]),
        ("AWS Infrastructure Monitoring & Reliability (HCL Technologies)", [
            "Configured CloudWatch alarms and dashboards across EC2, RDS, and application tiers for proactive detection of resource contention and service degradation.",
            "Automated deployment validation checks using Python and Jenkins post-deploy hooks, catching 80% of configuration-related production issues before user impact.",
        ]),
    ],
},
"qa_testing": {
    "bullets": [
        "Designed, created, executed, and maintained <b>structured test cases</b> covering functional, regression, integration, and smoke testing for enterprise Java and Python applications in Agile sprint cycles.",
        "Contributed to the development of <b>test plans, test scripts, and test management documentation</b> using Jira and Confluence, ensuring full traceability from requirements to test execution.",
        "Performed <b>pre-release smoke testing and health-validation checks</b> across development, staging, and production environments, catching critical defects before deployment sign-off.",
        "Logged, tracked, and supported the resolution of defects using <b>Jira</b>, collaborating with development teams to reproduce issues, validate fixes, and confirm closure.",
        "Executed <b>User Acceptance Testing (UAT) activities</b> in coordination with business stakeholders, translating acceptance criteria into structured test scenarios and sign-off documentation.",
        "Developed <b>Python and SQL-based automated test scripts</b> for regression and data validation testing, reducing manual test execution effort by 40% across release cycles.",
        "Worked with <b>PostgreSQL, MySQL, and Oracle databases</b> to perform data validation testing, executing backend queries to verify data integrity across application workflows.",
        "Collaborated with development, infrastructure, and business teams in an <b>Agile/Scrum</b> environment, participating in sprint planning, retrospectives, and defect triage sessions.",
    ],
    "skills": [
        "<b>Testing Types</b>  –  Functional, regression, integration, smoke, UAT; manual and automated testing.",
        "<b>Test Management</b>  –  Jira, Confluence, Zephyr; test planning, execution tracking, defect lifecycle.",
        "<b>Test Automation</b>  –  Python (pytest, unittest), SQL-based data validation, API testing with Postman.",
        "<b>Databases</b>  –  PostgreSQL, MySQL, Oracle; data validation queries, backend test verification.",
        "<b>Development Practices</b>  –  Agile/Scrum, test case design, defect reporting, requirements traceability.",
        "<b>API Testing</b>  –  REST API validation with Postman and Python requests; response schema verification.",
        "<b>Tools &amp; Environment</b>  –  Git, Jenkins CI/CD, Docker (test environments), AWS basics.",
    ],
    "projects": [
        ("Pre-Release Test Automation Framework (HCL Technologies)", [
            "Designed and implemented a Python-based automated regression test suite covering 200+ test cases for enterprise Java applications, reducing manual regression effort by 40% per release cycle.",
            "Integrated test execution into Jenkins CI/CD pipelines, enabling automated test runs on every build and providing immediate feedback to development teams on regression failures.",
            "Maintained Jira-based defect tracking and test execution dashboards, improving defect resolution turnaround by 30% through clear reporting and traceability.",
        ]),
        ("Defect Analysis & Data Validation Testing (HCL Technologies)", [
            "Performed systematic data validation testing using SQL queries against PostgreSQL and Oracle databases, verifying data integrity across 10+ application workflows and reporting pipelines.",
            "Executed UAT sessions with business stakeholders, translating acceptance criteria into 150+ test scenarios and managing sign-off documentation for 3 major product releases.",
        ]),
    ],
},
"frontend": {
    "bullets": [
        "Built and maintained <b>responsive React and Angular web applications</b>, implementing reusable component libraries and state management patterns that improved development consistency and reduced UI build time by <b>25%</b>.",
        "Developed <b>TypeScript and JavaScript (ES6+)</b> frontend features integrating with Java Spring Boot REST APIs, ensuring reliable data flows and clean separation of concerns across full-stack application layers.",
        "Implemented <b>JWT-based authentication flows and role-based UI rendering</b> in Angular and React, ensuring secure and auditable access patterns across customer-facing interfaces.",
        "Collaborated with UX designers and product owners to translate wireframes into <b>pixel-accurate, accessible HTML5/CSS3 components</b>, ensuring cross-browser compatibility and WCAG compliance.",
        "Wrote <b>unit and component tests using Jest and React Testing Library</b>, achieving 80%+ frontend code coverage and catching UI regressions before production releases.",
        "Worked with backend engineers in an <b>Agile/Scrum</b> environment to define API contracts, consume REST endpoints, and deliver end-to-end features across two-week sprint cycles.",
        "Optimised <b>frontend bundle size and page load performance</b> using code splitting, lazy loading, and caching strategies, improving Time-to-Interactive metrics by 30% for high-traffic pages.",
        "Maintained <b>CI/CD pipelines for frontend build and deployment</b> using Jenkins and Git, enabling automated testing and staging deployments with consistent, reproducible builds.",
    ],
    "skills": [
        "<b>Frontend Frameworks</b>  –  React, Angular, Vue.js; component architecture, hooks, state management (Redux, NgRx).",
        "<b>Languages</b>  –  TypeScript, JavaScript (ES6+), HTML5, CSS3, SCSS.",
        "<b>Testing</b>  –  Jest, React Testing Library, Cypress; TDD, component and E2E testing.",
        "<b>Backend Integration</b>  –  REST APIs, Java Spring Boot, JSON, OAuth2/JWT authentication.",
        "<b>Cloud &amp; DevOps</b>  –  AWS (S3, CloudFront), Docker, Jenkins, CI/CD pipelines, Git.",
        "<b>Databases</b>  –  PostgreSQL, MongoDB; supporting backend data requirements for frontend features.",
        "<b>Development Practices</b>  –  Agile/Scrum, accessibility (WCAG), performance optimisation, code reviews.",
    ],
    "projects": [
        ("Customer Portal – React Frontend (HCL Technologies)", [
            "Built a React-based customer portal with TypeScript supporting profile management, transaction history, and real-time notifications, consuming Java Spring Boot REST APIs for 10,000+ users.",
            "Implemented JWT authentication and role-based UI rendering, ensuring secure access across all portal modules and aligning with backend security policies.",
            "Developed reusable component library and applied Redux state management patterns, reducing duplicate code by 30% and accelerating feature delivery across the application.",
        ]),
        ("Internal Admin Dashboard – Angular (HCL Technologies)", [
            "Built a responsive Angular admin dashboard providing real-time data views via REST API integration, reducing operational reporting time by 40% for internal teams.",
            "Configured frontend CI/CD pipeline with Jenkins for automated build, lint, test, and deployment to staging, ensuring reliable and reproducible releases.",
        ]),
    ],
},
}

# ═══════════════════════════════════════════════════════════════════
# STATIC FALLBACK: role key picker
# ═══════════════════════════════════════════════════════════════════
def get_role_key(category, title=""):
    cat   = (category if isinstance(category, str) else "").lower()
    title = (title if isinstance(title, str) else "").lower()

    # Title-first detection for specialist roles
    if any(k in title for k in ["site reliability", "sre", "devops", "infrastructure engineer",
                                  "infrastructure developer", "platform automation", "cloud engineer",
                                  "reliability engineer"]):
        return "sre_devops"
    if any(k in title for k in ["frontend", "front-end", "front end", "react engineer",
                                  "web developer", "ui engineer", "swift software"]):
        return "frontend"
    if any(k in title for k in ["tester", "qa engineer", "qe engineer", "quality assurance",
                                  "test engineer", "solution tester", "software tester",
                                  "quality engineer", "testing"]):
        return "qa_testing"

    # Category-based fallback
    if "java" in cat or "backend" in cat:                    return "java"
    if "python" in cat:                                      return "python"
    if "data analyst" in cat:                                return "data_analyst"
    if "data scientist" in cat:                              return "data_scientist"
    if "ai" in cat or "ml" in cat:                           return "ai_ml"
    if "production support" in cat or "prod support" in cat: return "prod_support"
    if "it support" in cat or "it " in cat:                  return "it_support"
    if "support" in cat:                                     return "prod_support"
    if "full stack" in cat:                                  return "full_stack"
    return "java"

def slug(text):
    text = re.sub(r"[^a-z0-9\s]", "", text.lower().strip())
    return re.sub(r"\s+", "_", text)[:40]

# ═══════════════════════════════════════════════════════════════════
# AI-TAILORED GENERATION  (primary path)
# ═══════════════════════════════════════════════════════════════════

def _ai_available():
    return _GENAI_AVAILABLE and bool(GEMINI_API_KEY)


def generate_ai_content(job, retry=2):
    """
    Call Google Gemini (gemini-2.5-flash-lite) with the elite recruiter system
    prompt to generate resume bullets/skills/projects tailored to the JD.

    Returns (bullets, skills, projects_list) where projects_list is a list of
    (title_str, [bullet_str, ...]) tuples — same format make_resume() expects.

    Raises RuntimeError on unrecoverable error so the caller falls back to the
    static CONTENT templates.
    """
    client = _genai.Client(api_key=GEMINI_API_KEY)

    def _s(val):
        return val if isinstance(val, str) else ""
    title       = _s(job.get("title", "")).strip()
    company     = _s(job.get("company", "")).strip()
    description = (_s(job.get("description")) or "").strip()

    if description:
        jd_block = f"""Full Job Description (anchor every bullet/skill/project to this):
---
{description[:6000]}
---"""
    else:
        jd_block = (
            f"No JD body available. Infer reasonable requirements from: "
            f"Title='{title}', Company='{company}'."
        )

    user_content = f"""HARI_PROFILE (canonical truth — every bullet must trace back to one of these domains):
{HARI_PROFILE}

TARGET ROLE:
  Title   : {title}
  Company : {company}

  (Ignore any 'category' label inferred elsewhere — it is auto-assigned by the
  scraper and is frequently WRONG. The JD body below is the only thing to
  anchor on. A 'Payments Business Analyst' role must be written as a payments
  BA resume, not IT helpdesk, even if the scraper miscategorised it.)

{jd_block}

CONTEXT FROM HARI:
Hari pre-filters the jobs that enter this tracker — every JD you see is one he
has chosen because he already has the underlying skills and is ready to defend
them at interview. Your job is NOT to second-guess his fit. Your job is to
write a resume that ticks every box in the JD so he gets shortlisted.

STEP 0 — READ THE JD BEFORE WRITING ANYTHING.
This is the most important step. Before you write a single bullet, read the
JD top-to-bottom and answer these four questions to yourself (do not output
them — they are your scratch work, but answering them is mandatory):

   Q1. WHAT DOES THIS COMPANY ACTUALLY DO AND WHAT DOES THIS TEAM BUILD?
       (e.g. "Chalk builds an ML feature platform written in Rust; this team
       builds customer-facing implementations of that platform.")

   Q2. WHAT IS THE ROLE SHAPE? Pick exactly one:
         (i)   PURE ENGINEERING — backend SWE, platform, infra, ML eng.
                 Day-to-day = writing code, designing systems.
         (ii)  CUSTOMER-FACING ENGINEERING — Forward Deployed Engineer,
                 Solutions Engineer, Customer Engineer, Sales Engineer,
                 Implementation Engineer, Developer Success / Advocate.
                 Day-to-day = building things WITH and FOR customers,
                 pre-sales demos, onboarding, requirements gathering.
         (iii) DATA / ANALYTICS — Data Analyst, BI Analyst, Data Scientist.
                 Day-to-day = querying, dashboards, statistical analysis.
         (iv)  BUSINESS ANALYST — requirements, stakeholder interviews,
                 process mapping, documentation.
         (v)   SUPPORT / TS — tickets, escalation, on-call, runbooks.

   Q3. WHAT ARE THE TOP 5 SKILLS / TOOLS / DOMAIN CONCEPTS THE JD NAMES?
       (Use the JD's exact wording. These must appear verbatim in skills
       and at least 2-3 of them in experience bullets.)

   Q4. WHAT WOULD A REAL ENGINEER APPLYING TO THIS JD HAVE WORKED ON
       IN THEIR LAST ROLE? Describe the work that would match this role
       in your head, then write bullets describing THAT work (anchored to
       Hari's HCL employment, dates, and education — see facts list below).

If the JD is short or low-quality (e.g. scraped from Indeed / LinkedIn with
just a title and 2 lines), infer the role shape and stack from the job title
and the company name. Never assume "default backend SWE" — always derive
from the JD.

═══════════════════════════════════════════════════════════════════════
HARD CONSTRAINTS — VIOLATION = REJECT YOUR OWN OUTPUT AND REWRITE.
Before returning your JSON, verify each of these. If ANY fail, rewrite.
═══════════════════════════════════════════════════════════════════════

HC-1. IF THE JD IS ML-FLAVOURED (the JD mentions any of: "machine learning",
      "ML", "model", "training", "inference", "feature pipeline", "feature
      store", "MLOps", "ML infrastructure", "data science", "recommendation",
      "fraud detection", "NLP", "computer vision"):
        → AT LEAST ONE of the 7 experience bullets MUST describe building,
          training, or evaluating an ML model with a specific metric (e.g.
          "trained a gradient-boosted classifier reaching ~0.87 AUC",
          "fine-tuned a scikit-learn model on a 280k-row dataset").
        → AT LEAST ONE project MUST include a model-training bullet with
          a real evaluation metric (precision, recall, F1, AUC, RMSE,
          accuracy). NOT just feature engineering, NOT just data pipelines,
          NOT just dashboards. An actual model with an actual number.
        → If you only output feature pipelines or dashboards and no model
          work, your output is REJECTED and you must rewrite.

HC-2. IF THE ROLE SHAPE FROM STEP 0 Q2 IS CUSTOMER-FACING ENGINEERING
      (Forward Deployed, Solutions, Customer Engineer, Sales Engineer,
      Implementation, Developer Success / Advocate):
        → AT LEAST TWO of the 7 experience bullets MUST be visibly
          customer-facing. Each must use one of these signals explicitly:
          "customer", "client", "stakeholder", "onboarding", "pre-sales",
          "post-sales", "demo", "requirements gathering with [X]",
          "integration into customer environment", "trained the customer
          team on".
        → AT LEAST ONE project MUST describe a piece of customer-facing
          work (onboarding a pilot client, building a custom integration
          for a customer, running a customer POC).
        → Generic phrases like "cross-functional teams" do NOT count
          toward HC-2. They are internal-team language, not customer-
          facing language. If only "cross-functional teams" appears,
          your output is REJECTED and you must rewrite.

HC-3. NEITHER THE COMPANY NAME (from the JD) NOR THE LITERAL JD JOB TITLE
      may appear anywhere in the resume body. If your draft contains
      either, REJECT and rewrite.

HC-4. NONE of these banned numbers may appear: 99%, 99.5%, 99.9%, 99.95%,
      99.99%, 100% uptime, "zero downtime", "10,000 daily", "100,000
      daily", "1M daily", "1 million daily". If any appear, REJECT and
      rewrite with realistic, oddly-specific numbers.

HC-5. EXPERIENCE-BULLET COMPOSITION RULE — EXACTLY 7 BULLETS, SPLIT BY ROLE
      CATEGORY. Categorise the JD into ONE of these buckets, then build the
      7 experience bullets to the exact split below. This is the SHAPE of
      the experience section — non-negotiable. The 3 "from Hari's experience"
      bullets describe real-sounding work he could have done at HCL on that
      stack. The 3 "from JD" bullets mirror the JD's named responsibilities
      / tools using JD wording. The 7th bullet covers infra/ops as noted.

      (a) JAVA / BACKEND-JAVA roles:
            3× from Hari's experience — ALL THREE MUST BE JAVA-FLAVOURED,
                  EACH HITTING A DIFFERENT JAVA SUB-TOPIC:
                    (i)   Spring Boot REST APIs / microservices.
                    (ii)  Hibernate / JPA / persistence layer — this bullet
                          MUST explicitly contain the word "Hibernate" or
                          "JPA". If your draft has neither, REJECT and rewrite.
                    (iii) Java EE / OOP / design patterns / JUnit / Mockito /
                          Maven|Gradle.
                  FORBIDDEN bullet flavours in the Hari-experience trio for
                  a Java JD: Python ETL, generic production-support / SLA /
                  P1-P2 incident bullets, Power BI / Tableau dashboards,
                  payments-operations dashboard work. If any of those
                  appear, REJECT and rewrite — they dilute a Java resume.
            3× from JD: mirror the JD's specific Java responsibilities
                  (code reviews, mentoring juniors, sprint planning /
                  technical estimation, agile ceremonies, NoSQL exposure,
                  problem-solving / debugging — pick the 3 most prominent
                  from THIS JD).
            1× Docker / Kubernetes / cloud bullet (AWS, GCP, Azure —
                  whichever the JD names; else AWS).

            PROJECTS for Java JDs — BOTH must be Java-flavoured. NO Python
            ETL projects, NO Power BI / Tableau projects, NO MSc data-
            analytics projects. Examples of acceptable shapes:
              • "Enterprise Java Modernisation — Spring Boot + Hibernate"
              • "Event-Driven Java Microservice Mesh (Kafka + Spring Cloud)"
              • "Java REST API for [domain] with JPA + PostgreSQL"
              • "Java/Spring Boot Notification Service with JUnit coverage"

      (b) PYTHON / BACKEND-PYTHON roles:
            3× from Hari's experience: Python scripting, ETL pipelines,
                  pandas/NumPy automation work.
            3× from JD: mirror the JD's Python-specific responsibilities.
            1× Docker / Kubernetes / cloud bullet.

      (c) CLOUD / DEVOPS / SRE-CLOUD roles (cloud engineer, cloud platform,
          DevOps, infra, AWS/GCP/Azure engineer — NOT SRE incident-response):
            3× cloud-combined: AWS (EC2/S3/Lambda/CloudWatch), CI/CD with
                  Jenkins, infrastructure-as-code where plausible.
            3× from JD: mirror the JD's cloud-specific tools (Terraform,
                  Helm, ArgoCD, EKS, GKE — whatever the JD names).
            1× Kubernetes / Docker bullet.

      (d) IT SUPPORT / HELPDESK / DESKTOP-SUPPORT / ICT-SUPPORT roles:
            3-4× directly from JD: mirror the JD's support stack (ticketing
                  system, OS, end-user tooling, escalation procedure).
            3-4× thoughtful additions from Hari's HCL support work that
                  plausibly extend the JD's coverage (so the total is 7).
                  Pick what most strengthens the application; avoid filler.

      (e) DATA ANALYST / DATA SCIENTIST / BI / ML JOBS:
            3× from Hari's experience: pandas/NumPy/SQL data work, MSc
                  Data Analytics ML coursework, Power BI / Tableau where
                  the JD touches BI.
            3× from JD: mirror the JD's specific tools / methods (e.g.
                  PySpark, dbt, Looker, SageMaker, A/B testing).
            1× own choice — usually a deployment / pipeline / cloud bullet.
            (NOTE: HC-1 still applies if the JD is ML-flavoured — one of
            these 7 bullets must train a model with a metric.)

      (f) AI / GENAI / LLM ENGINEER roles:
            3× Java+Python combined: backend service work that serves
                  models or AI APIs (FastAPI / Spring Boot in front of an
                  ML model, Python pipeline, REST contracts).
            3× from JD: mirror JD's AI stack (LangChain, RAG, vector DBs,
                  fine-tuning, prompt engineering).
            1× Docker / Kubernetes / scaling bullet.

      (g) OTHER DEV (React / Vue / Angular / Frontend / Mobile / Full-Stack):
            3× from Hari's experience: React work (Hari has React + Angular
                  full-stack background — frame these credibly).
            3× from JD: mirror JD's frontend stack (TypeScript, state mgmt,
                  testing frameworks, design system).
            1× Docker / build-pipeline / CI bullet.

      (h) SUPPORT / SRE / PRODUCTION-SUPPORT / INCIDENT-RESPONSE roles:
            3× incident-response from Hari's HCL background (Splunk /
                  Dynatrace monitoring, P1/P2 incident triage, root cause
                  analysis, SLA management, on-call rotation).
            3× from JD: mirror JD's specific reliability stack (PagerDuty,
                  Datadog, Grafana, error budgets, postmortems).
            1× OS / Linux / shell scripting bullet.

      If the JD is genuinely a hybrid (e.g. "Full-Stack Java + AWS"), pick
      the dominant flavour from the title and primary responsibilities and
      apply that split; do not invent a new split.

      VIOLATION CHECK: count your bullets. If not exactly 7, REJECT and
      rewrite. If the composition doesn't match the split above for the
      detected category, REJECT and rewrite.

After drafting, mentally check HC-1 through HC-4 in order. Only return the
JSON once all four pass.

═══════════════════════════════════════════════════════════════════════

INSTRUCTIONS:
1. AIM FOR 75–80% JD COVERAGE — NOT 100%. Cover the core skills, tools, and
   responsibilities credibly, but DO NOT cram every single JD requirement
   into bullets. A resume that ticks every box reads as AI-generated. Pick
   the strongest 75–80% of JD points and leave the remaining 20–25%
   uncovered in experience (they can still appear in the skills array —
   see rule 4). The resume should sound like a real engineer with
   overlapping but not identical experience, not a synthetic perfect match.

2. CLAIM CONFIDENTLY, NO HEDGING — write as if Hari has every skill the JD
   asks for. Never use phrases like "exposure to", "familiarity with", "basic
   understanding", "willingness to learn", "interest in". Just state the skill
   in declarative terms. If the JD asks for Power BI, Tableau, ERP, GDPR,
   Kubernetes, Terraform, Spark, Kafka, dbt, Airflow, React Native, anything
   else — write it into bullets and skills as though Hari uses it day-to-day.
   The profile above is a baseline; expand confidently to cover whatever the
   JD calls for. EXCEPTION: the banking-standard names listed in the global
   forbidden list (SWIFT, MT103, ISO 20022, SEPA, PSD2, Open Banking,
   tokenization, cross-border payments, instant payments, BFSI) are NEVER
   written — even if the JD mentions them, paraphrase as "payments processing",
   "transaction message flows", "financial-services compliance", etc.

3. MIRROR EXACT JD TERMINOLOGY — use the JD's exact phrasing in bullets, skill
   lines, and project descriptions. ATS systems and recruiter eye-scans match
   on exact strings. (Banking-standard names from the global forbidden list
   are the only exception — always paraphrase those.)

4. REFRAME EVERY REAL ELEMENT TO THE JD'S FRAMING — production support →
   reliability / application support / incident management; ETL → data
   engineering / pipeline development; Splunk/Dynatrace dashboards → BI
   dashboards / operational reporting / Power BI dashboards as applicable;
   Confluence documentation → training materials / user guides / onboarding;
   REST APIs → system integrations / interconnected systems; banking dashboard
   work → payments BA / domain analysis / regulatory implementation.

5. EXPERIENCE BULLETS — REALISTIC, NOT KEYWORD-STUFFED.
   Write 7 experience bullets that read like a real engineer's resume — each
   bullet describes ONE coherent piece of work, not 2-3 JD requirements
   crammed together. Pick the JD requirements that align most naturally with
   Hari's actual HCL/MSc background and write those credibly. Skip the JD
   points that would require obvious over-stretching (e.g. don't claim 8
   years of ML production experience for a 3.5-year engineer). It is FINE
   to leave 20–25% of the JD's asks uncovered in experience — the skills
   array still picks them up for ATS.

   Each bullet should:
     - Lead with a strong past-tense verb (no repeats within the resume).
     - Describe a real-sounding piece of work, not a JD-keyword sandwich.
     - Sound like something Hari would say out loud in an interview.

   WRITE THE BULLETS FROM THE JD, NOT FROM A FIXED ANCHOR LIST.
   Do NOT default to "payments operations dashboard" or "Power BI dashboards
   for stakeholders" unless the JD is genuinely about payments or BI. Based
   on your Q4 answer from STEP 0 ("what would a real engineer applying to
   THIS jd have worked on in their last role?"), invent plausible day-to-day
   work that maps to the JD's actual domain, framed as having happened at
   HCL Technologies between Sep 2021 and Jan 2025. Bullets are free-form
   in their content — but the EMPLOYER, DATES, EDUCATION, and TOTAL YEARS
   are fixed facts you cannot change (see rule 8).

   ROLE-SHAPE OVERLAY (from STEP 0, Q2):
     - If shape is CUSTOMER-FACING ENGINEERING (FDE / SE / Customer Engineer /
       Sales Engineer / Implementation Engineer / Developer Success), AT
       LEAST 2 of the 6 bullets must describe customer/stakeholder work:
       requirements gathering with clients, onboarding new customers,
       integration into customer environments, technical demos, pre-sales
       or post-sales technical support, presenting to stakeholders.
     - If shape is DATA / ANALYTICS, bullets lean toward querying, modelling,
       dashboards, business stakeholder communication.
     - If shape is BUSINESS ANALYST, bullets lean toward stakeholder
       interviews, requirements documentation, process mapping, UAT.
     - If shape is SUPPORT / TS, bullets lean toward ticket flow, escalation,
       on-call runbooks, customer triage.
     - If shape is PURE ENGINEERING, bullets describe engineering work.

   METRIC REALISM — STRICTLY ENFORCED:
     - Only ~50% of bullets should carry a metric. Three bullets with NO
       number is correct.
     - BANNED metrics (overused and obviously fake): 99%, 99.5%, 99.9%,
       99.95%, 99.99%, 100% uptime, "zero downtime", 10,000 / 100,000 /
       1M / "1 million daily transactions". Never use these numbers.
     - PREFERRED metric shape: oddly-specific numbers a real engineer
       might have measured — "37%", "~3,200 events/sec", "12 dashboards",
       "an 8-person team", "p99 latency of 280ms", "cut deploy time from
       45 min to 18 min". Asymmetric numbers feel measured; round numbers
       feel invented.
     - Never claim a scale a 3.5-year engineer wouldn't deliver: no
       "$4M saved annually", no "scaled to 100M users", no "led a team
       of 30 engineers".

6. PROJECTS SECTION — TWO PROJECTS DERIVED FROM THE JD.

   STEP 6A — THINK FIRST (this is mandatory reasoning, do not skip):
     Re-read your STEP 0 answers (what does this team build, what is the
     role shape, what are the top skills). Then answer to yourself:
       "What two projects, if Hari had built them, would make a hiring
        engineer at THIS company say: 'this person has done what we need'?"
     The two projects should TOGETHER cover the core technical work the JD
     asks for, plus (if customer-facing) one project that demonstrates
     ability to ship things for/with customers.

   STEP 6B — PROJECT NAMES:
     - NEVER name a project after the hiring company. No "Chalk Feature
       Pipeline", no "Stripe Payments API", no "JP Morgan Risk Engine".
     - NEVER copy the JD's job title verbatim as a project name. No
       "Forward Deployed Engineering Platform" for an FDE role.
     - NEVER use buzzword sandwiches like "Real-Time / At Scale /
       Multi-Region / Petabyte-Scale" unless the JD is explicitly about
       that scale. A 3.5-year engineer's portfolio does not include
       "Real-Time Fraud Detection at Petabyte Scale".
     - Names should describe the problem domain or system in 4-7 words.
       Sound like an internal project name a small team would use.

   STEP 6C — PROJECT CONTENT:
     - Each project: exactly 3 bullets, real-sounding work.
     - Tech stack pulled from the JD where it fits naturally — no random
       extras to pad keyword density.
     - Metric realism applies here too: NOT every bullet has a number,
       and any number must be realistic for a portfolio / MSc capstone /
       extended HCL project (no "billions", no "99.9%").
     - For ML-flavoured JDs: AT LEAST one project must include a real
       MODEL-TRAINING bullet (the model, the dataset, the metric — e.g.
       "trained a gradient-boosted classifier on a 280k-row dataset,
       reaching ~0.87 AUC"), not just feature engineering or pipelines.
     - For customer-facing JDs: AT LEAST one project should describe work
       done with a real or hypothetical client/stakeholder (e.g. "rebuilt
       the onboarding flow for a pilot enterprise customer, reducing
       time-to-first-event from 6 weeks to 9 days").
     - Project 1 = sized like 3-9 months of work.
     - Project 2 = sized like 2-6 months of work. Can be a portfolio
       project, MSc capstone, or extended HCL work — whichever fits.
     - Do NOT pack every JD requirement into the projects either — same
       75–80% rule. Real projects don't tick every box.

   DO NOT cite "ireland-jobs-tracker", any GitHub repo by name, or this
   resume-generation pipeline in the projects section. If a JD has nothing
   to do with AI/LLMs, the projects section should NOT mention Claude /
   prompt engineering / Anthropic / LLMs / generative AI / RAG.

7. NEVER CONTRADICT THE JD — if the JD is "Payments BA", write a payments BA
   resume even if the scraper's 'category' label suggested something else.
   JD content is ground truth, category is noise.

8. MINIMAL FACTUAL ANCHORS — keep these exact facts as written in the profile,
   do not alter them: candidate name, contact details, employer name & dates
   (HCL Sep 2021 – Jan 2025), education (MSc NCI Feb 2026, BE SNS College 2021),
   IELTS score. Everything else (bullets, skills, projects, metrics, framings,
   project names) is yours to construct to match the JD.
6. Bullets must use <b>bold</b> tags around key technologies/achievements (HTML).
7. Skill lines must follow this exact format:
   "<b>Category Name</b>  –  item1, item2, item3."
8. CRITICAL — Education: Hari's MSc is COMPLETED (Feb 2026). NEVER write "in progress",
   "currently pursuing", "currently completing", or any similar phrase. It is done.
9. CRITICAL — Never use the abbreviation "BEng". If you mention the degree, write
   "Bachelor of Engineering" or "BE" in full.
10. CRITICAL — Never use the word "Foundational" anywhere (e.g. not "Angular (Foundational)"
    or "Frontend (Foundational)"). Just write the skill name without qualifiers.

Return ONLY a valid JSON object with this exact structure (no markdown fences):
{{
  "bullets": [
    "Bullet 1 with <b>bold tech</b> and a metric like <b>25%</b>...",
    "Bullet 2...",
    "Bullet 3...",
    "Bullet 4...",
    "Bullet 5...",
    "Bullet 6..."
  ],
  "skills": [
    "<b>Category</b>  –  skill1, skill2, skill3.",
    "<b>Category</b>  –  skill1, skill2.",
    "<b>Category</b>  –  skill1, skill2, skill3."
  ],
  "projects": [
    {{
      "title": "Project Name (HCL Technologies)",
      "bullets": [
        "Project bullet 1...",
        "Project bullet 2...",
        "Project bullet 3..."
      ]
    }},
    {{
      "title": "Project Name 2 (HCL Technologies)",
      "bullets": [
        "Project bullet 1...",
        "Project bullet 2..."
      ]
    }}
  ]
}}

Requirements: exactly 7 experience bullets, 5-7 skill lines, exactly 2 projects.
Return ONLY the JSON object — no markdown fences, no commentary."""

    for attempt in range(retry + 1):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-lite",
                contents=user_content,
                config=_genai_types.GenerateContentConfig(
                    system_instruction=ELITE_SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    temperature=0.7,
                ),
            )
            raw = (response.text or "").strip()

            data     = json.loads(raw)
            bullets  = data["bullets"]
            skills   = data["skills"]
            projects = [(p["title"], p["bullets"]) for p in data["projects"]]
            return bullets, skills, projects

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            if attempt < retry:
                time.sleep(2)
                continue
            raise RuntimeError(f"Gemini content parse failed after {retry+1} attempts: {e}")
        except Exception as e:
            if attempt < retry:
                time.sleep(3)
                continue
            raise RuntimeError(f"Gemini API call failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# PDF LAYOUT (unchanged)
# ═══════════════════════════════════════════════════════════════════
def make_resume(filename, exp_bullets, skills, proj_list, certs):
    # Always use compress=0 so the PDF is never < 8 KB.
    # (compress=1 can produce tiny PDFs whose story is already consumed when
    # we try to rebuild, resulting in a blank 931-byte file.)
    doc = SimpleDocTemplate(filename, pagesize=A4,
        leftMargin=1.6*cm, rightMargin=1.6*cm,
        topMargin=1.3*cm, bottomMargin=1.3*cm,
        compress=0)
    W = doc.width

    RULE_COLOR = colors.HexColor("#222222")
    SUB_COLOR  = colors.HexColor("#555555")

    name_s      = ParagraphStyle("name",  fontName="Helvetica-Bold", fontSize=20, textColor=BLACK, alignment=TA_CENTER, spaceAfter=2,  leading=24, letterSpacing=0.6)
    contact_s   = ParagraphStyle("con",   fontName="Helvetica",      fontSize=9.5, textColor=SUB_COLOR, alignment=TA_CENTER, spaceAfter=0,  leading=12)
    sec_s       = ParagraphStyle("sec",   fontName="Helvetica-Bold", fontSize=10.5, textColor=BLACK, alignment=TA_LEFT, spaceAfter=2,  spaceBefore=10, leading=13, letterSpacing=1.2)
    job_left_s  = ParagraphStyle("jl",    fontName="Helvetica-Bold", fontSize=10.5, textColor=BLACK, alignment=TA_LEFT,  leading=13)
    job_right_s = ParagraphStyle("jr",    fontName="Helvetica",      fontSize=9.5,  textColor=SUB_COLOR, alignment=TA_RIGHT, leading=13)
    bullet_s    = ParagraphStyle("bul",   fontName="Helvetica",      fontSize=10,   textColor=BLACK, alignment=TA_LEFT, leading=13.5, spaceAfter=2, leftIndent=12, firstLineIndent=-10)
    skill_s     = ParagraphStyle("sk",    fontName="Helvetica",      fontSize=10,   textColor=BLACK, alignment=TA_LEFT, leading=13.5, spaceAfter=2)
    proj_s      = ParagraphStyle("pt",    fontName="Helvetica-Bold", fontSize=10.5, textColor=BLACK, alignment=TA_LEFT, spaceAfter=1, spaceBefore=5, leading=13)
    cert_s      = ParagraphStyle("cert",  fontName="Helvetica",      fontSize=10,   textColor=BLACK, alignment=TA_LEFT, leading=13.5, spaceAfter=2, leftIndent=12, firstLineIndent=-10)

    def section_header(title):
        # Left-aligned section title with a thin rule below — cleaner than centered+underlined
        para = Paragraph(title.upper(), sec_s)
        rule = HRFlowable(width="100%", thickness=0.6, color=RULE_COLOR, spaceBefore=0, spaceAfter=4, lineCap="round")
        return [para, rule]

    def role_header(left_text, right_text):
        tbl = Table([[Paragraph(left_text, job_left_s), Paragraph(right_text, job_right_s)]],
                    colWidths=[W * 0.70, W * 0.30])
        tbl.setStyle(TableStyle([
            ("VALIGN",        (0,0),(-1,-1),"MIDDLE"),
            ("LEFTPADDING",   (0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0),
            ("TOPPADDING",    (0,0),(-1,-1),0), ("BOTTOMPADDING",(0,0),(-1,-1),2),
        ]))
        return tbl

    story = []
    story.append(Paragraph("HARIRAMAKRRISHNAN RAMACHANDRAN", name_s))
    story.append(Paragraph(
        '+353 89 970 6156  &nbsp;•&nbsp;  hariramakrrish@gmail.com  &nbsp;•&nbsp;  '
        'Dublin, Ireland  &nbsp;•&nbsp;  <b>Stamp 1G — Full-Time Work Eligible</b>', contact_s))

    story += section_header("Professional Experience")
    story.append(role_header("Software Engineer  —  HCL Technologies, Chennai, India", "Sep 2021 – Jan 2025"))
    story.append(Spacer(1, 3))
    for b in exp_bullets:
        story.append(Paragraph(f"•&nbsp;&nbsp;{b}", bullet_s))

    story += section_header("Skills")
    for sk in skills:
        story.append(Paragraph(sk, skill_s))

    story += section_header("Projects")
    for ptitle, pbullets in proj_list:
        story.append(Paragraph(ptitle, proj_s))
        for b in pbullets:
            story.append(Paragraph(f"•&nbsp;&nbsp;{b}", bullet_s))

    story += section_header("Education")
    story.append(role_header("M.Sc. Data Analytics  —  National College of Ireland, Dublin", "Feb 2026"))
    story.append(Spacer(1, 2))
    story.append(role_header("B.E. Computer Science  —  SNS College of Technology, Coimbatore, India", "2021"))

    # Force Certifications onto page 2 — page 1 ends after Education.
    story.append(PageBreak())
    story += section_header("Certifications")
    for c in certs:
        story.append(Paragraph(f"•&nbsp;&nbsp;{c}", cert_s))

    doc.build(story)

    # Size check is no longer needed — compress=0 is always used above.


# ═══════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════
def generate_for_jobs(jobs_to_generate=None, force_regen=False):
    """
    Generate PDFs for the given list of jobs (or all jobs in jobs.json).

    force_regen=True  → delete existing PDF and regenerate (used when a JD was
                        just fetched and we want to upgrade from the static template).
    """
    if not os.path.exists(JOBS_FILE):
        print("No jobs.json found — run search_jobs.py first.")
        return

    with open(JOBS_FILE) as f:
        all_jobs = json.load(f)

    targets = jobs_to_generate if jobs_to_generate is not None else all_jobs

    use_ai = _ai_available()
    if use_ai:
        print(f"  🤖  Gemini AI generation enabled (gemini-2.5-flash-lite)")
    else:
        print(f"  📋  Using static templates (set GEMINI_API_KEY to enable AI generation)")

    generated = skipped = errors = ai_ok = ai_fallback = 0

    for job in targets:
        # Auto-assign resume filename if missing
        if not job.get("resume"):
            company = job.get("company", "unknown")
            title   = job.get("title", "role")
            job["resume"] = f"hari_{slug(company)}_{slug(title)}.pdf"

        fname = os.path.join(RESUME_DIR, job["resume"])

        if os.path.exists(fname) and not force_regen:
            skipped += 1
            continue

        # ── Try AI path first ──────────────────────────────────────
        bullets = skills = projects = None
        if use_ai:
            try:
                bullets, skills, projects = generate_ai_content(job)
                ai_ok += 1
                print(f"  ✓  [AI]  {job['company']} — {job['title']}")
            except Exception as e:
                print(f"  ⚠  [AI fallback]  {job['company']} — {job['title']}  ({e})")
                ai_fallback += 1

        # ── Static fallback ────────────────────────────────────────
        if bullets is None:
            rk       = get_role_key(job.get("category", "java"), job.get("title", ""))
            data     = CONTENT[rk]
            bullets  = data["bullets"]
            skills   = data["skills"]
            projects = data["projects"]
            if not use_ai:
                print(f"  ✓  [tmpl] {job['company']} — {job['title']}")

        try:
            make_resume(fname, bullets, skills, projects, CERTS)
            generated += 1
        except Exception as e:
            print(f"  ✗  {job['company']} — {job['title']}  ERROR: {e}")
            errors += 1

    print(f"\n✅  Generated: {generated}  |  Skipped: {skipped}  |  Errors: {errors}")
    if use_ai:
        print(f"    AI success: {ai_ok}  |  Fell back to template: {ai_fallback}")


if __name__ == "__main__":
    generate_for_jobs()
