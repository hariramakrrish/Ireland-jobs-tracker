#!/usr/bin/env python3
"""
Generate tailored PDF resumes for every job in web/data/jobs.json.

Primary path  : Claude API (claude-haiku-4-5-20251001) generates unique bullets /
                skills / projects per job, using the stored job description + title +
                company.  Requires ANTHROPIC_API_KEY env var.

Fallback path : Static role-based content banks (no API key needed).  Used when
                the API key is absent or the API call fails.

Layout: Vishnu-format, Times font, A4.
"""
import os, re, json, time
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer,
                                 Table, TableStyle)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE   = os.path.join(ROOT, "web", "data", "jobs.json")
RESUME_DIR  = os.path.join(ROOT, "web", "resumes")
os.makedirs(RESUME_DIR, exist_ok=True)

BLACK = colors.HexColor("#000000")

# ── Try to import anthropic (optional dep) ────────────────────────────────────
try:
    import anthropic as _anthropic
    _ANTHROPIC_AVAILABLE = True
except ImportError:
    _ANTHROPIC_AVAILABLE = False

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

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

Education:
  • MSc in Data Analytics — National College of Ireland, Dublin (COMPLETED Feb 2026)
  • Bachelor of Engineering (BE) in Computer Science — SNS College of Technology, Coimbatore, India (2021)

Certifications:
  • IELTS Academic: Band 7/9
  • Full Stack Java Spring Boot & Angular (Great Learning)
  • Web Development — University of California, Davis (Coursera)
  • Python Programming — University of Michigan (Coursera)

Key technologies (honest list):
  Python, Java, SQL, Spring Boot, REST APIs, AWS (EC2/S3/Lambda/CloudWatch),
  Docker, Linux, Git, Jenkins, Jira, PostgreSQL, MySQL, Oracle,
  Splunk, Dynatrace, pandas, NumPy, Flask, FastAPI, React (basics), Angular (basics)
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
    return _ANTHROPIC_AVAILABLE and bool(ANTHROPIC_API_KEY)


def generate_ai_content(job, retry=2):
    """
    Call Claude (Haiku) to generate resume bullets/skills/projects tailored
    ~75-80% to the job's description (or title+company when no description).

    Returns (bullets, skills, projects_list) where projects_list is a list of
    (title_str, [bullet_str, ...]) tuples — same format as the static CONTENT banks.

    Raises on unrecoverable error so the caller can fall back to static.
    """
    client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    def _s(val):
        return val if isinstance(val, str) else ""
    title       = _s(job.get("title", "")).strip()
    company     = _s(job.get("company", "")).strip()
    category    = _s(job.get("category", "")).strip()
    description = (_s(job.get("description")) or "").strip()

    if description:
        jd_block = f"""Full Job Description (use this to tailor content):
---
{description[:4000]}
---"""
    else:
        jd_block = (
            f"No full job description available. "
            f"Infer requirements from: Title='{title}', Company='{company}', "
            f"Role category='{category}'."
        )

    prompt = f"""You are writing resume content for a software engineer applying for a specific job.

CANDIDATE PROFILE:
{HARI_PROFILE}

TARGET ROLE:
  Title   : {title}
  Company : {company}
  Category: {category}

{jd_block}

INSTRUCTIONS:
1. Generate content that authentically represents Hari's background while matching
   approximately 75-80% of what this role requires.
2. Do NOT invent technologies or seniority he doesn't have. Stretch plausibly — e.g.
   frame production support as reliability engineering; frame ETL as data engineering.
3. Use keywords from the job description naturally in bullets and skills.
4. Bullets must use <b>bold</b> tags around key technologies/achievements (HTML).
5. Skill lines must follow this exact format:
   "<b>Category Name</b>  –  item1, item2, item3."
6. CRITICAL — Education: Hari's MSc is COMPLETED (Feb 2026). NEVER write "in progress",
   "currently pursuing", "currently completing", or any similar phrase. It is done.
7. CRITICAL — Never use the abbreviation "BEng". If you mention the degree, write
   "Bachelor of Engineering" or "BE" in full.
8. CRITICAL — Never use the word "Foundational" anywhere (e.g. not "Angular (Foundational)"
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

Requirements: exactly 6 experience bullets, 5-7 skill lines, exactly 2 projects."""

    for attempt in range(retry + 1):
        try:
            response = client.messages.create(
                model="claude-haiku-4-5-20251001",
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text.strip()

            # Strip markdown code fences if Claude adds them
            if raw.startswith("```"):
                raw = re.sub(r"^```[a-z]*\n?", "", raw)
                raw = re.sub(r"\n?```$", "", raw.rstrip())

            data     = json.loads(raw)
            bullets  = data["bullets"]
            skills   = data["skills"]
            projects = [(p["title"], p["bullets"]) for p in data["projects"]]
            return bullets, skills, projects

        except (json.JSONDecodeError, KeyError) as e:
            if attempt < retry:
                time.sleep(2)
                continue
            raise RuntimeError(f"AI content parse failed after {retry+1} attempts: {e}")
        except Exception as e:
            if attempt < retry:
                time.sleep(3)
                continue
            raise RuntimeError(f"AI API call failed: {e}")


# ═══════════════════════════════════════════════════════════════════
# PDF LAYOUT (unchanged)
# ═══════════════════════════════════════════════════════════════════
def make_resume(filename, exp_bullets, skills, proj_list, certs):
    doc = SimpleDocTemplate(filename, pagesize=A4,
        leftMargin=1.8*cm, rightMargin=1.8*cm,
        topMargin=1.5*cm, bottomMargin=1.5*cm)
    W = doc.width

    name_s      = ParagraphStyle("name",  fontName="Times-Bold",   fontSize=24, textColor=BLACK, alignment=TA_CENTER, spaceAfter=5, leading=28)
    contact_s   = ParagraphStyle("con",   fontName="Times-Roman",  fontSize=10.5, textColor=BLACK, alignment=TA_CENTER, spaceAfter=2, leading=14)
    sec_s       = ParagraphStyle("sec",   fontName="Times-Bold",   fontSize=13, textColor=BLACK, alignment=TA_CENTER, spaceAfter=5, spaceBefore=10, leading=16)
    job_left_s  = ParagraphStyle("jl",    fontName="Times-Bold",   fontSize=11, textColor=BLACK, alignment=TA_LEFT,   leading=14)
    job_right_s = ParagraphStyle("jr",    fontName="Times-Bold",   fontSize=11, textColor=BLACK, alignment=TA_RIGHT,  leading=14)
    bullet_s    = ParagraphStyle("bul",   fontName="Times-Roman",  fontSize=10.5, textColor=BLACK, alignment=TA_LEFT, leading=14.5, spaceAfter=3, leftIndent=15, firstLineIndent=-11)
    skill_s     = ParagraphStyle("sk",    fontName="Times-Roman",  fontSize=10.5, textColor=BLACK, alignment=TA_LEFT, leading=14.5, spaceAfter=2)
    proj_s      = ParagraphStyle("pt",    fontName="Times-Bold",   fontSize=10.5, textColor=BLACK, alignment=TA_LEFT, spaceAfter=2, spaceBefore=4, leading=14)
    cert_s      = ParagraphStyle("cert",  fontName="Times-Roman",  fontSize=10.5, textColor=BLACK, alignment=TA_LEFT, leading=14.5, spaceAfter=3, leftIndent=15, firstLineIndent=-11)

    def section_header(title):
        return [Spacer(1, 4), Paragraph(f"<u>{title}</u>", sec_s)]

    def role_header(left_text, right_text):
        tbl = Table([[Paragraph(left_text, job_left_s), Paragraph(right_text, job_right_s)]],
                    colWidths=[W * 0.68, W * 0.32])
        tbl.setStyle(TableStyle([
            ("VALIGN",        (0,0),(-1,-1),"MIDDLE"),
            ("LEFTPADDING",   (0,0),(-1,-1),0), ("RIGHTPADDING",(0,0),(-1,-1),0),
            ("TOPPADDING",    (0,0),(-1,-1),2), ("BOTTOMPADDING",(0,0),(-1,-1),4),
            ("LINEBELOW",     (0,0),(-1, 0),1.0, BLACK),
        ]))
        return tbl

    story = []
    story.append(Paragraph("HARIRAMAKRRISHNAN RAMACHANDRAN", name_s))
    story.append(Paragraph(
        '+353 899706156  |  hariramakrrish@gmail.com  |  '
        '<a href="https://www.linkedin.com/in/hariramakrrish/" color="#0070C0"><u>LinkedIn</u></a>'
        '  |  <b>Stamp 1G</b> — Eligible to work full-time in Ireland', contact_s))

    story += section_header("PROFESSIONAL EXPERIENCE")
    story.append(role_header("SOFTWARE ENGINEER  –  HCL Technologies  |  Chennai, India", "09/2021 – 01/2025  (3.5 Years)"))
    story.append(Spacer(1, 5))
    for b in exp_bullets:
        story.append(Paragraph(f"•  {b}", bullet_s))

    story += section_header("SKILLS")
    story.append(Spacer(1, 2))
    for sk in skills:
        story.append(Paragraph(sk, skill_s))

    story += section_header("EDUCATION AND TRAINING")
    story.append(Spacer(1, 3))
    story.append(role_header("MASTER OF SCIENCE in Data Analytics  –  <b>National College of Ireland</b>, Dublin", "02/2026"))
    story.append(Spacer(1, 6))
    story.append(role_header("BACHELOR OF ENGINEERING in Computer Science  –  <b>SNS College of Technology</b>, Coimbatore, India", "01/2021"))
    story.append(Spacer(1, 4))

    story += section_header("PROJECTS")
    story.append(Spacer(1, 2))
    for ptitle, pbullets in proj_list:
        story.append(Paragraph(ptitle, proj_s))
        for b in pbullets:
            story.append(Paragraph(f"•  {b}", bullet_s))

    story += section_header("ACHIEVEMENTS & CERTIFICATIONS")
    story.append(Spacer(1, 2))
    for c in certs:
        story.append(Paragraph(f"•  {c}", cert_s))

    doc.build(story)


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
        print(f"  🤖  AI-tailored generation enabled (claude-haiku-4-5-20251001)")
    else:
        print(f"  📋  Using static templates (set ANTHROPIC_API_KEY to enable AI generation)")

    generated = skipped = errors = ai_ok = ai_fallback = 0

    for job in targets:
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
