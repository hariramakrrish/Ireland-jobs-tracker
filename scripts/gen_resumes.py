#!/usr/bin/env python3
"""
Generate tailored PDF resumes for every job in web/data/jobs.json
that doesn't already have a PDF in web/resumes/.
Uses Vishnu-format layout with Times font.
"""
import os, re, json
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

def slug(text):
    text = re.sub(r"[^a-z0-9\s]", "", text.lower().strip())
    return re.sub(r"\s+", "_", text)[:40]

# ═══════════════════════════════════════════════════════════════════
# ROLE CONTENT BANKS
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
        "<b>MLOps &amp; Experimentation</b>  –  MLflow, model versioning, experiment tracking, cross-validation.",
        "<b>Databases</b>  –  PostgreSQL, MySQL, MongoDB; query optimisation and data modelling.",
        "<b>Cloud &amp; DevOps</b>  –  AWS (S3, SageMaker), Docker, Jenkins, CI/CD pipelines.",
        "<b>Development Practices</b>  –  Agile/Scrum, Git, statistical analysis, data storytelling.",
    ],
    "projects": [
        ("Predictive Customer Churn Model (HCL Technologies)", [
            "Developed a gradient boosting model to predict customer churn with 87% AUC, enabling proactive identification of at-risk segments and reducing churn-related revenue loss.",
            "Built end-to-end feature engineering pipelines using pandas and NumPy, reducing model training time by 35% and improving reproducibility across experiments.",
            "Deployed the model as a REST API using Flask on AWS EC2, enabling real-time inference integrated with downstream CRM and operational decision tools.",
        ]),
        ("Time-Series Demand Forecasting (HCL Technologies)", [
            "Built a time-series forecasting model using Prophet and scikit-learn to predict transaction volumes four weeks in advance, enabling operations teams to plan resource capacity proactively.",
            "Automated model retraining with a Jenkins CI/CD pipeline and tracked artefacts in MLflow, ensuring full reproducibility and version control of model outputs.",
        ]),
    ],
},
"ai_ml": {
    "bullets": [
        "Developed and deployed <b>machine learning and deep learning models</b> using Python (TensorFlow, PyTorch, scikit-learn), improving prediction accuracy by 22% on production datasets.",
        "Built and optimised <b>MLOps pipelines</b> integrating model training, versioning, and deployment on AWS SageMaker with Docker and MLflow, reducing model release cycles from weeks to days.",
        "Designed <b>NLP text classification pipelines</b> using Hugging Face Transformers, automating support ticket categorisation and reducing manual triage effort by 60%.",
        "Developed and maintained <b>backend services in Java and Spring Boot</b> to expose ML model outputs via RESTful APIs, enabling real-time inference for downstream enterprise applications.",
        "Worked with <b>PostgreSQL and MongoDB</b> to design efficient data pipelines supporting model training and evaluation, handling millions of records with optimised query performance.",
        "Implemented <b>feature stores and data versioning</b> practices, ensuring consistency between training and production datasets and improving model reliability across deployment cycles.",
        "Collaborated with product teams and data engineers in an <b>Agile/Scrum</b> environment to scope, build, and ship AI/ML features with measurable business impact.",
        "Monitored model performance in production using <b>drift detection and automated alerting</b>, enabling timely retraining and maintaining model quality over time.",
    ],
    "skills": [
        "<b>AI &amp; Machine Learning</b>  –  TensorFlow, PyTorch, scikit-learn, Hugging Face Transformers, LLMs.",
        "<b>MLOps</b>  –  AWS SageMaker, MLflow, model versioning, drift detection, automated retraining.",
        "<b>Programming Languages</b>  –  Python (advanced), Java, SQL.",
        "<b>Python Ecosystem</b>  –  pandas, NumPy, Flask, FastAPI, feature engineering.",
        "<b>Backend &amp; APIs</b>  –  Java Spring Boot, REST APIs, microservices, API design.",
        "<b>Cloud &amp; DevOps</b>  –  AWS (EC2, S3, Lambda, SageMaker), Docker, Kubernetes, Jenkins, CI/CD.",
        "<b>Development Practices</b>  –  Agile/Scrum, Git, experiment tracking, statistical analysis.",
    ],
    "projects": [
        ("ML-Powered Recommendation Engine (HCL Technologies)", [
            "Developed a collaborative filtering recommendation engine using Python and scikit-learn, improving user engagement metrics by 18% in A/B testing across 50,000+ active users.",
            "Deployed the model as a real-time REST API on AWS SageMaker, achieving sub-100ms inference latency integrated with the core Java Spring Boot application backend.",
            "Implemented automated model retraining triggered by data drift thresholds, ensuring recommendation quality was maintained as user behaviour patterns evolved.",
        ]),
        ("NLP Text Classification Pipeline (HCL Technologies)", [
            "Built an NLP pipeline using Hugging Face Transformers and PyTorch to classify support tickets automatically, reducing manual triage time by 60% and improving SLA compliance.",
            "Integrated the fine-tuned model into a Spring Boot microservice via REST API, enabling seamless consumption by downstream Java applications.",
        ]),
    ],
},
"prod_support": {
    "bullets": [
        "Managed <b>end-to-end production incident response</b> across mission-critical enterprise applications, achieving average MTTR under 30 minutes and maintaining <b>99.9% system availability</b> SLA targets.",
        "Performed <b>root cause analysis (RCA)</b> on P1/P2 production incidents using log analysis, query profiling, and distributed tracing tools, producing actionable remediation plans to prevent recurrence.",
        "Coordinated <b>cross-functional war rooms</b> with development, infrastructure, and business teams during major incidents, driving structured resolution in high-pressure environments.",
        "Maintained and enhanced <b>Java Spring Boot and Python-based backend services</b>, applying patches, hotfixes, and configuration changes to resolve production defects with minimal downtime.",
        "Developed <b>automated monitoring and alerting solutions</b> using Datadog, Grafana, and PagerDuty, reducing false-positive alert noise by 40% and improving incident detection accuracy.",
        "Worked with <b>PostgreSQL, MySQL, and Oracle databases</b> to diagnose slow queries, lock contention, and data integrity issues, resolving production data incidents within agreed SLAs.",
        "Maintained detailed <b>runbooks, incident logs, and post-mortem documentation</b>, enabling knowledge transfer and reducing resolution time for recurring incident patterns by 35%.",
        "Collaborated with development teams in an <b>Agile/DevOps</b> environment to implement production hardening improvements, CI/CD pipeline checks, and pre-release smoke testing frameworks.",
    ],
    "skills": [
        "<b>Production Support</b>  –  P1/P2 incident management, RCA, MTTR optimisation, SLA compliance, runbook creation.",
        "<b>Monitoring &amp; Alerting</b>  –  Datadog, Grafana, Splunk, PagerDuty, CloudWatch, log analysis and triage.",
        "<b>Programming Languages</b>  –  Java, Python, SQL, Bash scripting for incident automation and tooling.",
        "<b>Databases</b>  –  PostgreSQL, MySQL, Oracle; query diagnostics, lock analysis, data integrity checks.",
        "<b>Cloud &amp; Infrastructure</b>  –  AWS (EC2, CloudWatch, S3), Linux, Docker, Kubernetes.",
        "<b>Backend &amp; APIs</b>  –  Java Spring Boot, REST APIs, microservices; hotfix deployment and service management.",
        "<b>Development Practices</b>  –  ITIL, Agile/DevOps, Git, Jira, incident documentation, on-call support.",
    ],
    "projects": [
        ("Production Incident Automation Framework (HCL Technologies)", [
            "Built a Python-based incident automation tool integrated with PagerDuty and Jira, auto-creating tickets, assigning on-call engineers, and populating RCA templates — reducing manual overhead by 40% per incident.",
            "Implemented automated pre-checks and health-validation scripts triggered post-deployment, catching 80% of configuration-related production issues before user impact.",
            "Developed a Grafana dashboard consolidating application health, error rates, and SLA metrics, enabling the support team to identify degradation trends within minutes of occurrence.",
        ]),
        ("Database Incident Triage & Optimisation (HCL Technologies)", [
            "Diagnosed and resolved critical PostgreSQL lock contention and slow-query incidents causing production degradation, applying targeted index optimisations and query rewrites that improved throughput by 35%.",
            "Created standardised database runbooks covering common incident patterns, enabling L1 engineers to self-resolve 30% of recurring database incidents without escalation.",
        ]),
    ],
},
"it_support": {
    "bullets": [
        "Provided <b>Level 1 and Level 2 IT support</b> for 300+ end users across hardware, software, and network issues, maintaining an average resolution time under 2 hours and achieving <b>95% SLA compliance</b>.",
        "Managed user accounts, access provisioning, and endpoint configurations using <b>Active Directory, Azure AD</b>, and ServiceNow, ensuring secure and compliant IT operations.",
        "Diagnosed and resolved complex issues across <b>Windows Server, Linux, and macOS</b> environments, reducing recurring incident rates by 25% through root cause analysis and documentation.",
        "Developed <b>Java and Python automation scripts</b> to streamline common IT workflows including password resets and account provisioning, reducing Level 1 ticket volume by 35%.",
        "Maintained and optimised <b>network infrastructure</b> including DNS, DHCP, VPN, and LAN/WAN configurations, supporting reliable connectivity for distributed and remote users.",
        "Administered <b>Microsoft 365, SharePoint, and Teams</b> environments, supporting collaboration tools, licence management, and endpoint security policy enforcement.",
        "Worked with <b>PostgreSQL and MySQL databases</b> to run diagnostic queries, support internal tooling, and maintain data integrity across IT operations platforms.",
        "Contributed to <b>CI/CD pipeline maintenance</b> and backend deployments using Java Spring Boot, bridging IT operations and software engineering to support DevOps practices.",
    ],
    "skills": [
        "<b>IT Support</b>  –  Level 1/2 support, Active Directory, Azure AD, ServiceNow, ITIL, SLA management.",
        "<b>Operating Systems</b>  –  Windows Server (2016/2019), Linux (Ubuntu, CentOS), macOS.",
        "<b>Networking</b>  –  TCP/IP, DNS, DHCP, VPN, LAN/WAN, network diagnostics and troubleshooting.",
        "<b>Cloud &amp; Productivity</b>  –  Microsoft 365, Azure, Teams, SharePoint, AWS (EC2, S3).",
        "<b>Programming &amp; Scripting</b>  –  Java, Python, Bash; automation of IT workflows and tooling.",
        "<b>Databases</b>  –  PostgreSQL, MySQL; diagnostic queries and data integrity checks.",
        "<b>Development Practices</b>  –  Agile/Scrum, Git, Jira, documentation, CI/CD pipeline support.",
    ],
    "projects": [
        ("IT Helpdesk Automation Tool (HCL Technologies)", [
            "Developed a Java and Python-based automation tool integrated with ServiceNow via REST API to auto-resolve common Level 1 tickets including password resets and account unlocks, reducing ticket volume by 35%.",
            "Designed automated SLA monitoring and escalation workflows, alerting engineers before breach thresholds and improving overall SLA compliance from 88% to 95%.",
        ]),
        ("Endpoint Monitoring Dashboard (HCL Technologies)", [
            "Built an internal monitoring dashboard using Python and PostgreSQL to track endpoint health and uptime across 200+ devices, alerting the IT team to issues proactively.",
            "Configured automated health-check scripts with Bash and Cron, reducing undetected outage duration by 50% and improving visibility of the endpoint estate.",
        ]),
    ],
},
}

CONTENT["qa_testing"] = {
    "bullets": [
        "Designed, created, executed, and maintained <b>structured test cases</b> covering functional, regression, integration, and smoke testing across enterprise Java and Python-based applications, identifying and logging defects with clear reproduction steps.",
        "Contributed to the development of <b>test plans, test scripts, and test management documentation</b>, ensuring traceability between requirements, test coverage, and defect resolution throughout the project lifecycle.",
        "Performed <b>pre-release smoke testing and health-validation checks</b> triggered post-deployment, catching 80% of configuration-related defects before reaching end users and reducing production incident rates significantly.",
        "Logged, tracked, and supported the resolution of defects using <b>Jira</b>, maintaining accurate defect status reporting and communicating testing progress, risks, and outcomes to the project team and stakeholders through clear written reports.",
        "Executed <b>User Acceptance Testing (UAT) activities</b> in collaboration with business stakeholders, validating that delivered features met agreed functional requirements and contributing to formal sign-off processes.",
        "Developed <b>Python and SQL-based automated test scripts</b> to validate data integrity, API responses, and system behaviour, reducing manual regression effort by 35% and improving test repeatability across release cycles.",
        "Worked with <b>PostgreSQL, MySQL, and Oracle databases</b> to perform data validation testing, verify query outputs, and ensure data integrity across integrated systems in support of end-to-end testing activities.",
        "Collaborated with development, infrastructure, and business teams in an <b>Agile/Scrum</b> environment to understand requirements, clarify acceptance criteria, and deliver comprehensive test coverage aligned with sprint goals.",
    ],
    "skills": [
        "<b>Testing Types</b>  –  Functional, regression, integration, smoke, performance, and User Acceptance Testing (UAT).",
        "<b>Test Management</b>  –  Test plan creation, test case design, execution tracking, defect logging, and test summary reporting.",
        "<b>Defect &amp; Project Tools</b>  –  Jira, Confluence; defect lifecycle management, RAID/RACI tracking, stakeholder reporting.",
        "<b>Test Automation</b>  –  Python scripting for automated test execution, SQL-based data validation, API testing.",
        "<b>Databases</b>  –  PostgreSQL, MySQL, Oracle; data integrity checks, query validation, and test data management.",
        "<b>Programming Languages</b>  –  Python, SQL, Java, Bash; used for scripting and test automation tooling.",
        "<b>Development Practices</b>  –  Agile/Scrum, Git, CI/CD pipeline testing, pre-release validation, documentation.",
    ],
    "projects": [
        ("Pre-Release Test Automation Framework (HCL Technologies)", [
            "Designed and implemented a Python-based automated pre-release testing suite integrated with CI/CD pipelines, executing health-validation checks and smoke tests post-deployment and catching 80% of configuration defects before user impact.",
            "Developed structured test scripts covering API response validation, database integrity checks, and end-to-end workflow verification, reducing manual regression effort by 35% across release cycles.",
            "Maintained test execution evidence and produced weekly test summary reports communicated to project leads and stakeholders, ensuring clear visibility of defect status and release readiness.",
        ]),
        ("Defect Analysis & Data Validation Testing (HCL Technologies)", [
            "Designed and executed SQL-based data validation test cases across PostgreSQL and Oracle environments, identifying data integrity issues and logging defects with full reproduction steps and impact analysis.",
            "Collaborated with development and business teams in Agile sprints to review requirements, define acceptance criteria, and contribute to UAT execution and formal sign-off activities for enterprise application features.",
        ]),
    ],
}

CONTENT["sre_devops"] = {
    "bullets": [
        "Managed <b>end-to-end production incident response</b> across mission-critical AWS-hosted enterprise applications, achieving average MTTR under 30 minutes and maintaining <b>99.9% system availability</b> against defined SLIs, SLOs, and SLA targets.",
        "Performed <b>root cause analysis (RCA)</b> on P1/P2 production incidents using CloudWatch log analysis, distributed tracing, and query profiling, producing actionable remediation plans and post-mortem documentation to prevent recurrence.",
        "Supported <b>AWS cloud infrastructure</b> operations including EC2, S3, VPC, IAM, RDS, and CloudWatch, assisting with environment configuration, access management, and resource health monitoring.",
        "Developed <b>automated monitoring and alerting solutions</b> using Grafana, CloudWatch, and PagerDuty, reducing false-positive alert noise by 40% and improving incident detection accuracy across distributed services.",
        "Collaborated with development teams in an <b>Agile/DevOps</b> environment to support <b>CI/CD pipelines</b> for automated build, test, and deployment processes, contributing to pre-release smoke testing and deployment validation checks.",
        "Supported <b>Docker-containerised application deployments</b> and assisted with Kubernetes-based service management, contributing to environment reliability and deployment consistency.",
        "Wrote <b>Python and Bash automation scripts</b> to streamline operational workflows, implement health-validation checks post-deployment, and reduce toil by automating recurring manual tasks.",
        "Maintained detailed <b>runbooks, incident logs, and operational documentation</b>, enabling knowledge transfer and reducing resolution time for recurring incident patterns by 35%.",
    ],
    "skills": [
        "<b>Cloud &amp; Infrastructure</b>  –  AWS (EC2, S3, VPC, IAM, RDS, ELB, CloudWatch), Linux system administration.",
        "<b>Monitoring &amp; Observability</b>  –  Grafana, CloudWatch, Prometheus, PagerDuty, Datadog; log analysis and SLI/SLO tracking.",
        "<b>Containers &amp; Orchestration</b>  –  Docker, Kubernetes (EKS/AKS), container lifecycle management.",
        "<b>CI/CD &amp; Automation</b>  –  CI/CD pipeline support, Jenkins, Git, Bash and Python scripting, IaC concepts (Terraform, CloudFormation).",
        "<b>Incident Management</b>  –  P1/P2 response, RCA, MTTR optimisation, SLA compliance, runbook creation, on-call support.",
        "<b>Programming &amp; Scripting</b>  –  Python, Bash, SQL; automation of operational workflows and tooling.",
        "<b>Development Practices</b>  –  ITIL, Agile/DevOps, Git, Jira, post-mortem documentation.",
    ],
    "projects": [
        ("Production Incident Automation Framework (HCL Technologies)", [
            "Built a Python-based incident automation tool integrated with PagerDuty and Jira, auto-creating tickets, assigning on-call engineers, and populating RCA templates — reducing manual overhead by 40% per incident.",
            "Implemented automated pre-checks and health-validation scripts triggered post-deployment, catching 80% of configuration-related production issues before user impact.",
            "Developed a Grafana dashboard consolidating application health, error rates, and SLA metrics, enabling the support team to identify degradation trends within minutes of occurrence.",
        ]),
        ("AWS Infrastructure Monitoring & Reliability (HCL Technologies)", [
            "Configured CloudWatch alarms and dashboards across EC2, RDS, and application tiers, enabling proactive detection of resource contention and service degradation.",
            "Supported on-call incident rotation, contributing to structured war-room coordination during major outages and driving resolution through systematic root cause analysis and cross-functional collaboration.",
        ]),
    ],
}

CONTENT["frontend"] = {
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
}

def get_role_key(category, title=""):
    cat   = category.lower()
    title = title.lower()

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

def generate_for_jobs(jobs_to_generate=None):
    """Generate PDFs. If jobs_to_generate is None, process all jobs in jobs.json."""
    if not os.path.exists(JOBS_FILE):
        print("No jobs.json found — run search_jobs.py first.")
        return

    with open(JOBS_FILE) as f:
        all_jobs = json.load(f)

    if jobs_to_generate is not None:
        targets = jobs_to_generate
    else:
        targets = all_jobs

    generated = skipped = errors = 0
    for job in targets:
        fname = os.path.join(RESUME_DIR, job["resume"])
        if os.path.exists(fname):
            skipped += 1
            continue
        rk   = get_role_key(job.get("category", "java"), job.get("title", ""))
        data = CONTENT[rk]
        try:
            make_resume(fname, data["bullets"], data["skills"], data["projects"], CERTS)
            print(f"  ✓  {job['company']} — {job['title']}")
            generated += 1
        except Exception as e:
            print(f"  ✗  {job['company']} — {job['title']}  ERROR: {e}")
            errors += 1

    print(f"\n✅  Generated: {generated}  |  Skipped (exists): {skipped}  |  Errors: {errors}")

if __name__ == "__main__":
    generate_for_jobs()
