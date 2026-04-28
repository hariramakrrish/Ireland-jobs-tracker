#!/usr/bin/env python3
"""Seed web/data/jobs.json from the existing 55 tracked jobs."""
import json, os, re, hashlib
from datetime import datetime

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE = os.path.join(ROOT, "web", "data", "jobs.json")
os.makedirs(os.path.dirname(JOBS_FILE), exist_ok=True)

def slug(text):
    text = re.sub(r"[^a-z0-9\s]", "", text.lower().strip())
    return re.sub(r"\s+", "_", text)[:40]

def job_id(company, title):
    return hashlib.md5(f"{slug(company)}_{slug(title)}".encode()).hexdigest()[:10]

jobs_raw = [
    (1,  "Java / Backend", "Mastercard",                  "Lead Software Engineer",               "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aafkz4qdgdyk",  "Indeed"),
    (2,  "Java / Backend", "Optum",                       "Senior Software Engineer",             "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aayjpflvd9pc",  "Indeed"),
    (3,  "Java / Backend", "Optum",                       "Lead Software Engineer",               "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aawtqrmqg22v",  "Indeed"),
    (4,  "Java / Backend", "TCS",                         "Senior Blockchain Java Developer",     "Dublin, Ireland",   "Feb 2026", "https://to.indeed.com/aaywvrcxjsnj",  "Indeed"),
    (5,  "Java / Backend", "National Facilities Direct",  "Senior Backend Engineer",              "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aaxl446gldkf",  "Indeed"),
    (6,  "Java / Backend", "Work Fusion",                 "Java Developer",                       "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aa9rw8v2c9sw",  "Indeed"),
    (7,  "Java / Backend", "Version 1",                   "Java Developer",                       "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aa44xrqrrg8q",  "Indeed"),
    (8,  "Full Stack",     "Virtu Financial",             "Full Stack Developer",                 "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aaqvhdn9j8xb",  "Indeed"),
    (9,  "Full Stack",     "RWS",                         "Full Stack Developer",                 "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aalh9pz6n8yg",  "Indeed"),
    (10, "Java / Backend", "Equifax",                     "Software Engineer",                    "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aa7lrhwsngph",  "Indeed"),
    (11, "Python",         "Clio",                        "Software Developer",                   "Dublin, Ireland",   "Mar 2026", "https://to.indeed.com/aawpg8xk482n",  "Indeed"),
    (12, "Java / Backend", "iCIMS",                       "Associate Software Engineer",          "Dublin, Ireland",   "Feb 2026", "https://to.indeed.com/aajzcbcvhksk",  "Indeed"),
    (13, "Python",         "Klaviyo",                     "Lead Software Engineer - Amplify",     "Dublin, Ireland",   "Jan 2026", "https://to.indeed.com/aa6yvv6thqys",  "Indeed"),
    (14, "Full Stack",     "PlayStation",                 "Graduate Engineer",                    "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aawpkwp7qzsn",  "Indeed"),
    (15, "Java / Backend", "Mastercard",                  "Senior Site Reliability Engineer",     "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aawqvxmpm8xn",  "Indeed"),
    (16, "Data Analyst",   "GRANITE DIGITAL",             "Senior Performance & Web Analyst",     "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aa9jrzqtrt47",  "Indeed"),
    (17, "Data Analyst",   "Indeed Co",                   "Global Senior Client Analyst",         "Dublin, Ireland",   "Mar 2026", "https://to.indeed.com/aagjhnxxmwvn",  "Indeed"),
    (18, "Data Analyst",   "Optum",                       "Senior Data Analyst",                  "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aambnjymgr2x",  "Indeed"),
    (19, "Data Analyst",   "Optum",                       "Principal Data Analyst",               "Dublin, Ireland",   "Mar 2026", "https://to.indeed.com/aabrwkj9tmfg",  "Indeed"),
    (20, "Data Analyst",   "Optum",                       "Senior Business Systems Analyst",      "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aal4nz8q4rkd",  "Indeed"),
    (21, "Data Analyst",   "Culligan",                    "Business Systems Support Analyst",     "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aahp6fyyfjtr",  "Indeed"),
    (22, "Data Scientist", "Optum",                       "Senior Data Scientist",                "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aa6dbqrsrtql",  "Indeed"),
    (23, "Data Scientist", "Optum",                       "Data Scientist 1",                     "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aampnzjnsdnm",  "Indeed"),
    (24, "Data Scientist", "Workday",                     "Data Scientist",                       "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aanm24c9t9gf",  "Indeed"),
    (25, "Data Scientist", "Grand Intelligence",          "Founding AI Data Scientist",           "Dublin, Ireland",   "Feb 2026", "https://to.indeed.com/aalc94gwhs49",  "Indeed"),
    (26, "Data Scientist", "Fortray Global Services",     "Data and AI Analyst",                  "Dublin, Ireland",   "Nov 2025", "https://to.indeed.com/aa48w6ngqztp",  "Indeed"),
    (27, "Data Scientist", "Optum",                       "Principal Data Scientist",             "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aag2mpgghwk4",  "Indeed"),
    (28, "AI / ML",        "JPMorganChase",               "Lead AI ML Ops Engineer",              "Dublin, Ireland",   "Feb 2026", "https://to.indeed.com/aaywsmxc7wmd",  "Indeed"),
    (29, "AI / ML",        "Tether Operations",           "Machine Learning Engineer",            "Remote, Ireland",   "Mar 2026", "https://to.indeed.com/aaxn4m969y8x",  "Indeed"),
    (30, "AI / ML",        "PayPal",                      "Staff Machine Learning Engineer",      "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aafxjzwrnhpw",  "Indeed"),
    (31, "AI / ML",        "Optum",                       "Senior Data Engineer",                 "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aadbnyhmbtpf",  "Indeed"),
    (32, "AI / ML",        "Optum",                       "Principal Data Scientist AI",          "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aazx97wtl2zf",  "Indeed"),
    (33, "IT Support",     "PFH Technology Group",        "IT Support Engineer",                  "Dublin, Ireland",   "Apr 2026", "https://to.indeed.com/aadv29btp2k9",  "Indeed"),
    (34, "IT Support",     "Convergint",                  "GSOC Support Specialist",              "Dublin, Ireland",   "Nov 2025", "https://to.indeed.com/aa6s9ldk278q",  "Indeed"),
    (35, "IT Support",     "Mastercard",                  "Lead Site Reliability Engineer",       "Dublin, Ireland",   "Mar 2026", "https://to.indeed.com/aal92mbv9khq",  "Indeed"),
    (36, "Java / Backend", "INIT Group",                  "Java Backend Software Developer",      "Maynooth, Ireland", "Apr 2026", "https://ie.linkedin.com/jobs/view/java-backend-software-developer-at-init-group-4393523210", "LinkedIn"),
    (37, "Java / Backend", "Apple",                       "Java Backend Developer IS&T",          "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/java-backend-developer-is-t-retail-systems-at-apple-4385930940", "LinkedIn"),
    (38, "Java / Backend", "Altimetrik",                  "Mid-Senior Java Developer",            "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/mid-senior-java-developer-at-altimetrik-4393532595", "LinkedIn"),
    (39, "Full Stack",     "Berkley Group",               "Full Stack Java Developer",            "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/full-stack-java-developer-at-berkley-group-4395284972", "LinkedIn"),
    (40, "Java / Backend", "Infoplus Technologies",       "Java Software Engineer",               "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/java-software-engineer-at-infoplus-technologies-uk-limited-4404092383", "LinkedIn"),
    (41, "Java / Backend", "Elevate Partners",            "Java Developer",                       "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/java-developer-at-elevate-partners-4404099720", "LinkedIn"),
    (42, "Java / Backend", "Twilio",                      "Software Engineer",                    "Ireland",           "Apr 2026", "https://ie.linkedin.com/jobs/view/software-engineer-at-twilio-4404522390", "LinkedIn"),
    (43, "Java / Backend", "Paysafe",                     "Backend Engineer Java",                "Dublin, Ireland",   "Feb 2026", "https://ie.linkedin.com/jobs/view/backend-engineer-java-at-paysafe-4359181592", "LinkedIn"),
    (44, "Full Stack",     "Stripe",                      "Full Stack Engineer",                  "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/full-stack-engineer-collaboration-at-stripe-4402604343", "LinkedIn"),
    (45, "Java / Backend", "Citi",                        "Software Engineer",                    "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/software-engineer-at-citi-4402330066", "LinkedIn"),
    (46, "AI / ML",        "Docusign",                    "Machine Learning Engineer",            "Dublin, Ireland",   "Mar 2026", "https://ie.linkedin.com/jobs/view/machine-learning-engineer-at-docusign-4377628100", "LinkedIn"),
    (47, "AI / ML",        "eBay",                        "Junior AI ML Agent Engineer",          "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/junior-ai-ml-agent-engineer-at-ebay-4399772123", "LinkedIn"),
    (48, "AI / ML",        "Accenture UK & Ireland",      "AI ML Engineer",                       "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/ai-ml-engineer-at-accenture-uk-ireland-4394476892", "LinkedIn"),
    (49, "AI / ML",        "Deel",                        "AI ML Engineer Python",                "Ireland",           "Mar 2026", "https://ie.linkedin.com/jobs/view/ai-ml-engineer-python-at-deel-4387381555", "LinkedIn"),
    (50, "AI / ML",        "Mastercard",                  "AI Engineer II",                       "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/ai-engineer-ii-at-mastercard-4400844558", "LinkedIn"),
    (51, "Python",         "Fruition Group Ireland",      "Python Developer",                     "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/python-developer-at-fruition-group-ireland-4403370192", "LinkedIn"),
    (52, "Data Analyst",   "Unijobs",                     "Data Analyst",                         "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/data-analyst-at-unijobs-4404553546", "LinkedIn"),
    (53, "Python",         "Randstad Digital",            "Python Developer",                     "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/python-developer-at-randstad-digital-4399985261", "LinkedIn"),
    (54, "IT Support",     "Irish Cancer Society",        "Desktop Support Engineer",             "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/desktop-support-engineer-at-irish-cancer-society-4401657362", "LinkedIn"),
    (55, "IT Support",     "Astreya",                     "Service Desk Analyst",                 "Dublin, Ireland",   "Apr 2026", "https://ie.linkedin.com/jobs/view/service-desk-analyst-at-astreya-4403941608", "LinkedIn"),
]

jobs = []
for (num, cat, company, title, loc, posted, url, source) in jobs_raw:
    jobs.append({
        "id":        job_id(company, title),
        "num":       num,
        "category":  cat,
        "company":   company,
        "title":     title,
        "location":  loc,
        "source":    source,
        "posted":    posted,
        "apply_url": url,
        "resume":    f"hari_{slug(company)}_{slug(title)}.pdf",
        "status":    "Not Applied",
        "added":     datetime.now().strftime("%Y-%m-%d"),
    })

with open(JOBS_FILE, "w") as f:
    json.dump(jobs, f, indent=2)

print(f"✅  Seeded {len(jobs)} jobs → {JOBS_FILE}")
