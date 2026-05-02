#!/usr/bin/env python3
"""
Multi-platform Ireland job search pipeline.

Sources:
  1. LinkedIn   — worldunboxer/rapid-linkedin-scraper (FREE, structured JSON)
  2. Indeed IE  — valig/indeed-jobs-scraper (99.8% success, $0.0001/result)
  3. Glassdoor  — valig/glassdoor-jobs-scraper (99.9% success, $0.0004/result)
  4. IrishJobs  — unfenced-group/irishjobs-ie-scraper (dedicated Ireland board)
  5. Jobs.ie    — Apify RAG browser (no dedicated actor exists)
  6. Company career pages — 16 major companies with Ireland offices (RAG browser)

All sources return structured data. Deduplicates against existing jobs.json.
"""
import os, re, json, hashlib, time
from datetime import datetime
from apify_client import ApifyClient

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE   = os.path.join(ROOT, "web", "data", "jobs.json")

# ── Role categories with junior/grad/entry-level queries ─────────────────────
SEARCHES = [
    ("Java / Backend", [
        "junior java developer",
        "graduate java engineer",
        "associate software engineer java",
        "entry level backend developer",
        "graduate spring boot developer",
        "junior backend engineer",
        "software engineer java",
        "junior kotlin developer",
    ]),
    ("Python / Data / ML", [
        "junior python developer",
        "graduate python engineer",
        "entry level python developer",
        "junior data engineer",
        "graduate machine learning engineer",
        "junior AI engineer",
        "associate data scientist",
        "software engineer python",
    ]),
    ("Data Analyst", [
        "junior data analyst",
        "graduate data analyst",
        "entry level data analyst",
        "associate business analyst",
        "graduate business intelligence analyst",
        "junior SQL analyst",
        "data analyst graduate",
    ]),
    ("AI / ML", [
        "junior machine learning engineer",
        "graduate AI engineer",
        "entry level ML engineer",
        "associate machine learning engineer",
        "junior NLP engineer",
        "AI software engineer entry level",
        "graduate deep learning engineer",
    ]),
    ("Full Stack / General SWE", [
        "junior full stack developer",
        "graduate software engineer",
        "entry level software engineer",
        "associate software engineer",
        "junior react developer",
        "junior node.js developer",
        "software engineer new grad",
        "junior web developer",
    ]),
    ("IT Support", [
        "junior IT support engineer",
        "graduate IT support",
        "entry level desktop support",
        "associate service desk analyst",
        "junior helpdesk engineer",
        "IT support analyst",
        "junior systems administrator",
    ]),
    ("Production Support", [
        "junior production support engineer",
        "graduate application support engineer",
        "junior devops engineer",
        "graduate site reliability engineer",
        "associate DevOps engineer",
        "junior cloud engineer",
        "junior platform engineer",
    ]),
    ("Cloud / Infrastructure", [
        "junior cloud engineer",
        "graduate AWS engineer",
        "associate cloud developer",
        "junior Azure engineer",
        "entry level infrastructure engineer",
        "junior kubernetes engineer",
        "cloud support engineer",
    ]),
]

# Maximum results per query per source
RESULTS_PER_QUERY = 10

# ── Company career pages (RAG browser fallback) ───────────────────────────────
COMPANY_CAREER_PAGES = [
    ("Microsoft",   "https://careers.microsoft.com/v2/global/en/locations/dublin.html",               "Full Stack / General SWE"),
    ("Google",      "https://www.google.com/about/careers/applications/jobs/results?location=Dublin,+Ireland", "Full Stack / General SWE"),
    ("Stripe",      "https://stripe.com/jobs/search?location=Dublin&teams=engineering",               "Java / Backend"),
    ("Amazon",      "https://www.amazon.jobs/en/search?base_query=software+engineer&loc_query=Dublin%2C+Ireland", "Full Stack / General SWE"),
    ("Workday",     "https://www.workday.com/en-us/company/careers/overview.html?q=software+engineer&location=Dublin", "Full Stack / General SWE"),
    ("HubSpot",     "https://www.hubspot.com/careers/jobs?q=software+engineer&country=Ireland",       "Full Stack / General SWE"),
    ("Salesforce",  "https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site?q=software+engineer&locationCountry=IE", "Full Stack / General SWE"),
    ("MongoDB",     "https://www.mongodb.com/careers/search?department=Engineering&location=Dublin%2C+Ireland", "Full Stack / General SWE"),
    ("Zendesk",     "https://jobs.zendesk.com/us/en/search-results?keywords=software+engineer&location=Dublin", "Full Stack / General SWE"),
    ("Intercom",    "https://www.intercom.com/careers/jobs?search=engineer&location=Dublin",          "Full Stack / General SWE"),
    ("Gong",        "https://www.gong.io/careers/#open-positions",                                    "Full Stack / General SWE"),
    ("Arista",      "https://www.arista.com/en/careers",                                              "Full Stack / General SWE"),
    ("Bentley",     "https://www.bentley.com/company/careers/?search=software+engineer&location=Dublin", "Full Stack / General SWE"),
    ("Canonical",   "https://canonical.com/careers/all?location=Ireland",                             "Python / Data / ML"),
    ("Etsy",        "https://careers.etsy.com/?country=IE",                                           "Java / Backend"),
    ("Fidelity",    "https://www.fidelityinternational.com/careers/",                                 "Java / Backend"),
]

# ── Experience filter ──────────────────────────────────────────────────────────
SENIOR_TITLE_KEYWORDS = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|head\s+of|director|vp\b|vice\s+president"
    r"|architect|manager|consultant|expert|level\s+[4-9]"
    r"|[4-9]\+?\s*years?|[1-9][0-9]\+?\s*years?)\b",
    re.IGNORECASE
)
JUNIOR_TITLE_KEYWORDS = re.compile(
    r"\b(junior|jr\.?|graduate|grad\b|intern|trainee|associate|entry.?level"
    r"|new\s+grad|early\s+career|apprentice|software\s+engineer\s+i{1,2}$"
    r"|engineer\s+i{1,2}$|swe\s+i{1,2}$)\b",
    re.IGNORECASE
)

def is_experience_appropriate(title: str) -> bool:
    if JUNIOR_TITLE_KEYWORDS.search(title):
        return True
    if SENIOR_TITLE_KEYWORDS.search(title):
        return False
    return True   # neutral titles (Software Engineer, Developer, etc.) → include

def slug(text):
    text = re.sub(r"[^a-z0-9\s]", "", text.lower().strip())
    return re.sub(r"\s+", "_", text)[:40]

def job_id(company, title):
    return hashlib.md5(f"{slug(company)}_{slug(title)}".encode()).hexdigest()[:10]

# ── Safe string extractor (guards against scrapers returning dicts) ────────────
def _s(val):
    """Return val if it's a non-empty string, otherwise ''."""
    return val if isinstance(val, str) else ""

# ── Apify RAG browser (fallback for sites without dedicated actors) ────────────
def rag_fetch(client, url, query="software engineer ireland", timeout=120):
    try:
        run   = client.actor("apify/rag-web-browser").call(
            run_input={"startUrls": [{"url": url}], "maxResults": 1, "query": query},
            timeout_secs=timeout,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        if not items:
            return ""
        return items[0].get("text", "") or items[0].get("markdown", "")
    except Exception as e:
        print(f"    ⚠  RAG fetch failed: {e}")
        return ""

# ── 1. LinkedIn — worldunboxer/rapid-linkedin-scraper (FREE) ─────────────────
def search_linkedin(client, query, max_results=RESULTS_PER_QUERY):
    """
    Uses the FREE dedicated LinkedIn scraper. Returns structured job objects.
    experience_level: 1=Internship 2=Entry 3=Associate 4=Mid 5=Director 6=Executive
    job_post_time: r86400=24h r604800=week r2592000=month
    """
    try:
        run = client.actor("worldunboxer/rapid-linkedin-scraper").call(
            run_input={
                "job_title":       query,
                "location":        "Ireland",
                "jobs_entries":    max_results,
                "experience_level": "2",   # Entry level
                "job_post_time":   "r2592000",  # Last month
                "job_type":        "F",    # Full-time
            },
            timeout_secs=180,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        jobs  = []
        for item in items:
            title   = (_s(item.get("job_title")) or _s(item.get("title")) or "").strip()
            company = (_s(item.get("company_name")) or _s(item.get("company")) or "").strip()
            loc     = (_s(item.get("job_location")) or _s(item.get("location")) or "Ireland").strip()
            url     = item.get("job_url") or item.get("url") or ""
            desc    = (_s(item.get("description")) or _s(item.get("job_description")) or
                       _s(item.get("jobDescription")) or _s(item.get("snippet")) or "").strip()
            if title and company and len(title) > 3:
                jobs.append({"title": title, "company": company,
                             "location": loc, "source": "LinkedIn", "url": url,
                             "description": desc[:6000] if desc else ""})
        print(f"        LinkedIn   → {len(jobs)} results")
        return jobs
    except Exception as e:
        print(f"        ⚠  LinkedIn scraper failed ('{query}'): {e}")
        return []

# ── 2. Indeed IE — valig/indeed-jobs-scraper (99.8% success) ─────────────────
def search_indeed(client, query, max_results=RESULTS_PER_QUERY):
    """
    Dedicated Indeed scraper — country=ie for Ireland, datePosted=14 (last 2 weeks).
    """
    try:
        run = client.actor("valig/indeed-jobs-scraper").call(
            run_input={
                "country":    "ie",
                "title":      query,
                "location":   "Ireland",
                "limit":      max_results,
                "datePosted": "14",  # last 14 days
            },
            timeout_secs=180,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        jobs  = []
        for item in items:
            title   = (_s(item.get("title")) or _s(item.get("positionName")) or "").strip()
            company = (_s(item.get("company")) or _s(item.get("companyName")) or "").strip()
            loc     = (_s(item.get("location")) or "Ireland").strip()
            url     = item.get("url") or item.get("jobUrl") or ""
            desc    = (_s(item.get("description")) or _s(item.get("jobDescription")) or
                       _s(item.get("snippet")) or _s(item.get("summary")) or "").strip()
            if title and company and len(title) > 3:
                jobs.append({"title": title, "company": company,
                             "location": loc, "source": "Indeed", "url": url,
                             "description": desc[:6000] if desc else ""})
        print(f"        Indeed     → {len(jobs)} results")
        return jobs
    except Exception as e:
        print(f"        ⚠  Indeed scraper failed ('{query}'): {e}")
        return []

# ── 3. Glassdoor — valig/glassdoor-jobs-scraper (99.9% success) ──────────────
def search_glassdoor(client, query, max_results=RESULTS_PER_QUERY):
    """
    Dedicated Glassdoor scraper — Ireland location, last 30 days.
    """
    try:
        run = client.actor("valig/glassdoor-jobs-scraper").call(
            run_input={
                "keywords": query,
                "location": "Ireland",
                "daysOld":  30,
                "limit":    max_results,
            },
            timeout_secs=180,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        jobs  = []
        for item in items:
            title   = (_s(item.get("jobTitle")) or _s(item.get("title")) or "").strip()
            _emp = item.get("employer") or item.get("company") or item.get("companyName") or ""
            company = (_emp.get("name", "") if isinstance(_emp, dict) else _s(_emp)).strip()
            loc     = (_s(item.get("location")) or "Ireland").strip()
            url     = item.get("jobUrl") or item.get("url") or ""
            desc    = (_s(item.get("description")) or _s(item.get("jobDescription")) or
                       _s(item.get("jobDescriptionText")) or _s(item.get("snippet")) or "").strip()
            if title and company and len(title) > 3:
                jobs.append({"title": title, "company": company,
                             "location": loc, "source": "Glassdoor", "url": url,
                             "description": desc[:6000] if desc else ""})
        print(f"        Glassdoor  → {len(jobs)} results")
        return jobs
    except Exception as e:
        print(f"        ⚠  Glassdoor scraper failed ('{query}'): {e}")
        return []

# ── 4. IrishJobs.ie — dedicated scraper ───────────────────────────────────────
def search_irishjobs(client, query, max_results=RESULTS_PER_QUERY):
    """
    Dedicated IrishJobs.ie scraper — Ireland's #1 local job board.
    Falls back to RAG browser if actor fails.
    """
    try:
        run = client.actor("unfenced-group/irishjobs-ie-scraper").call(
            run_input={
                "keywords":   query,
                "location":   "Dublin",
                "maxResults": max_results,
            },
            timeout_secs=180,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        jobs  = []
        for item in items:
            title   = (_s(item.get("title")) or _s(item.get("jobTitle")) or "").strip()
            company = (_s(item.get("company")) or _s(item.get("companyName")) or "").strip()
            loc     = (_s(item.get("location")) or "Ireland").strip()
            url     = item.get("url") or item.get("jobUrl") or ""
            desc    = (_s(item.get("description")) or _s(item.get("jobDescription")) or
                       _s(item.get("fullDescription")) or _s(item.get("summary")) or "").strip()
            if title and company and len(title) > 3:
                jobs.append({"title": title, "company": company,
                             "location": loc, "source": "IrishJobs", "url": url,
                             "description": desc[:6000] if desc else ""})
        print(f"        IrishJobs  → {len(jobs)} results")
        return jobs
    except Exception as e:
        print(f"        ⚠  IrishJobs scraper failed ('{query}'): {e} — trying RAG fallback")
        return _irishjobs_rag_fallback(client, query, max_results)

def _irishjobs_rag_fallback(client, query, max_results):
    url  = f"https://www.irishjobs.ie/Jobs/{query.replace(' ', '-')}?JobCategoryId=2,3,5,11"
    text = rag_fetch(client, url, query=query)
    return _parse_generic(text, "IrishJobs", max_results)

# ── 5. Jobs.ie — RAG browser (no dedicated actor) ────────────────────────────
def search_jobsie(client, query, max_results=RESULTS_PER_QUERY):
    terms = query.replace(" ireland", "").replace(" ", "-")
    url   = f"https://www.jobs.ie/jobs/{terms}/ireland/"
    text  = rag_fetch(client, url, query=query)
    jobs  = _parse_generic(text, "Jobs.ie", max_results)
    print(f"        Jobs.ie    → {len(jobs)} results")
    return jobs

def _parse_generic(text, source_name, max_results):
    jobs, seen = [], set()
    patterns = [
        r"^([A-Z][^\n]{4,79})\n([A-Z][^\n]{2,60})\n([^\n]*(?:Ireland|Dublin|Cork|Galway|Remote)[^\n]*)",
        r"([A-Z][^\n]{4,79}?)\s+at\s+([A-Z][^\n]{2,60}?)\s*[\n·]\s*([^\n]*(?:Ireland|Dublin|Cork)[^\n]*)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.MULTILINE):
            title   = m.group(1).strip()
            company = m.group(2).strip() if len(m.groups()) > 1 else "Unknown"
            loc     = m.group(3).strip()[:80] if len(m.groups()) > 2 else "Ireland"
            key     = f"{title.lower()[:60]}_{company.lower()[:40]}"
            if key not in seen and 5 < len(title) < 90 and len(company) > 1:
                seen.add(key)
                jobs.append({"title": title, "company": company, "location": loc,
                             "source": source_name, "url": ""})
            if len(jobs) >= max_results:
                return jobs
    return jobs

# ── 6. Company career pages — RAG browser ─────────────────────────────────────
def parse_company_page(text, company, max_results=10):
    jobs, seen = [], set()
    title_re = re.compile(
        r"(?:^|\n)([A-Z][A-Za-z0-9 ,./\-&'()]{5,79})"
        r"(?:\n|\s*[-–·|]\s*)"
        r"(?:[^\n]*(?:Dublin|Ireland|Remote)[^\n]*)",
        re.MULTILINE
    )
    skip = re.compile(
        r"^(Apply|View|Learn|Read|See|Sign|Join|Home|About|Contact|Benefits|Culture"
        r"|Login|Life at|Jobs in|Search|Filter|Careers|Explore|Skip|Showing|Sort|Page)\b",
        re.I
    )
    for m in title_re.finditer(text):
        title = m.group(1).strip().rstrip("-–·|•").strip()
        if not (5 < len(title) < 90) or skip.match(title):
            continue
        key = f"{title.lower()[:60]}_{company.lower()[:30]}"
        if key not in seen and is_experience_appropriate(title):
            seen.add(key)
            jobs.append({"title": title, "company": company,
                         "location": "Dublin, Ireland", "source": f"{company} Careers", "url": ""})
        if len(jobs) >= max_results:
            break
    return jobs

def search_company_careers(client, company, url, category):
    print(f"    🏢  {company} careers page...")
    text = rag_fetch(client, url, query=f"software engineer {company} ireland", timeout=90)
    jobs = parse_company_page(text, company, max_results=10)
    print(f"        {company}  → {len(jobs)} results")
    return jobs, category

# ── Helpers ───────────────────────────────────────────────────────────────────
def load_existing_jobs():
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE) as f:
            return json.load(f)
    return []

def save_jobs(jobs):
    os.makedirs(os.path.dirname(JOBS_FILE), exist_ok=True)
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

def make_entry(r, category, next_num):
    title   = r["title"]
    company = r["company"]
    source  = r.get("source", "LinkedIn")
    loc     = r.get("location", "Ireland")
    url     = r.get("url", "")
    if not url:
        if "Indeed" in source:
            url = f"https://ie.indeed.com/jobs?q={title.replace(' ', '+')}&l=Ireland"
        elif "Glassdoor" in source:
            url = f"https://www.glassdoor.com/Jobs/Ireland-{title.replace(' ', '-')}-SRCH_IL.0,7_IN97_KO8,{8+len(title)}.htm"
        elif "IrishJobs" in source:
            url = f"https://www.irishjobs.ie/Jobs/{title.replace(' ', '-')}"
        elif "Jobs.ie" in source:
            url = f"https://www.jobs.ie/jobs/{title.replace(' ', '-')}/ireland/"
        else:
            url = f"https://www.linkedin.com/jobs/search/?keywords={title.replace(' ', '%20')}&location=Ireland"
    entry = {
        "id":        job_id(company, title),
        "num":       next_num,
        "category":  category,
        "company":   company,
        "title":     title,
        "location":  loc,
        "source":    source,
        "posted":    datetime.now().strftime("%b %Y"),
        "apply_url": url,
        "resume":    f"hari_{slug(company)}_{slug(title)}.pdf",
        "status":    "Not Applied",
        "added":     datetime.now().strftime("%Y-%m-%d"),
    }
    # Capture job description if the scraper returned one
    desc = _s(r.get("description", "")).strip()
    if desc:
        entry["description"] = desc
    return entry

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    print(f"🔍  Multi-platform job search — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"    Sources: LinkedIn (free) | Indeed IE | Glassdoor | IrishJobs | Jobs.ie | 16 company sites")
    client       = ApifyClient(APIFY_TOKEN)
    existing     = load_existing_jobs()
    existing_ids = {j["id"] for j in existing}
    new_jobs     = []
    next_num     = max((j.get("num", 0) for j in existing), default=0) + 1

    for (category, queries) in SEARCHES:
        print(f"\n  📂  {category}")
        for query in queries:
            print(f"    🔎  {query}")
            all_results = []

            # LinkedIn (FREE dedicated scraper)
            all_results += search_linkedin(client, query, RESULTS_PER_QUERY)
            time.sleep(2)

            # Indeed IE (99.8% success, $0.0001/result)
            all_results += search_indeed(client, query, RESULTS_PER_QUERY)
            time.sleep(2)

            # Glassdoor (99.9% success, $0.0004/result)
            all_results += search_glassdoor(client, query, RESULTS_PER_QUERY)
            time.sleep(2)

            # IrishJobs (dedicated Ireland board)
            all_results += search_irishjobs(client, query, RESULTS_PER_QUERY)
            time.sleep(2)

            # Jobs.ie (RAG browser fallback)
            all_results += search_jobsie(client, query, RESULTS_PER_QUERY)
            time.sleep(2)

            for r in all_results:
                if not is_experience_appropriate(r["title"]):
                    continue
                jid = job_id(r["company"], r["title"])
                if jid not in existing_ids:
                    entry = make_entry(r, category, next_num)
                    new_jobs.append(entry)
                    existing_ids.add(jid)
                    next_num += 1
                    print(f"        ✓  [{r.get('source','?')}] {r['title']} @ {r['company']}")

    # ── Company career pages ────────────────────────────────────────────────
    print("\n\n🏢  Scraping company career pages...")
    for (company, url, cat) in COMPANY_CAREER_PAGES:
        try:
            results, category = search_company_careers(client, company, url, cat)
            time.sleep(3)
            for r in results:
                if not is_experience_appropriate(r["title"]):
                    continue
                jid = job_id(r["company"], r["title"])
                if jid not in existing_ids:
                    entry = make_entry(r, category, next_num)
                    new_jobs.append(entry)
                    existing_ids.add(jid)
                    next_num += 1
                    print(f"        ✓  {r['title']} @ {r['company']}")
        except Exception as e:
            print(f"    ⚠  {company} failed: {e}")

    all_jobs = existing + new_jobs
    save_jobs(all_jobs)
    print(f"\n✅  Total jobs: {len(all_jobs)}  |  New today: {len(new_jobs)}")
    return new_jobs

if __name__ == "__main__":
    main()
