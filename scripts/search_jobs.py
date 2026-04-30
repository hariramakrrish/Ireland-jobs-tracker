#!/usr/bin/env python3
"""
Search for Ireland jobs across LinkedIn, Indeed (ie), IrishJobs.ie, Jobs.ie,
and direct company career pages (Microsoft, Google, Stripe, Amazon, etc.).
Uses Apify RAG browser for scraping, and Apify Indeed scraper for structured results.
Deduplicates against existing jobs.json.
"""
import os, re, json, hashlib, time
from datetime import datetime
from apify_client import ApifyClient

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE   = os.path.join(ROOT, "web", "data", "jobs.json")

# ── Role categories — broad + specific terms, all junior/grad/entry level ────
SEARCHES = [
    ("Java / Backend", [
        "junior java developer ireland",
        "graduate java engineer ireland",
        "entry level java developer ireland",
        "associate software engineer java ireland",
        "graduate spring boot developer ireland",
        "intern java developer ireland",
        "junior backend developer ireland",
        "graduate backend engineer ireland",
    ]),
    ("Python", [
        "junior python developer ireland",
        "graduate python engineer ireland",
        "entry level python developer ireland",
        "associate python developer ireland",
        "intern python developer ireland",
        "junior software developer python ireland",
    ]),
    ("Data Analyst", [
        "junior data analyst ireland",
        "graduate data analyst ireland",
        "entry level data analyst ireland",
        "intern data analyst ireland",
        "associate data analyst ireland",
        "graduate business analyst ireland",
        "junior business intelligence analyst ireland",
    ]),
    ("Data Scientist", [
        "junior data scientist ireland",
        "graduate data scientist ireland",
        "entry level data scientist ireland",
        "associate data scientist ireland",
        "intern data scientist ireland",
        "graduate quantitative analyst ireland",
    ]),
    ("AI / ML", [
        "junior machine learning engineer ireland",
        "graduate ai engineer ireland",
        "entry level ml engineer ireland",
        "associate machine learning engineer ireland",
        "graduate nlp engineer ireland",
        "junior ai developer ireland",
        "intern machine learning ireland",
    ]),
    ("IT Support", [
        "junior IT support engineer ireland",
        "graduate IT support ireland",
        "entry level desktop support ireland",
        "intern IT support ireland",
        "associate service desk analyst ireland",
        "junior helpdesk engineer ireland",
        "graduate systems administrator ireland",
    ]),
    ("Full Stack", [
        "junior full stack developer ireland",
        "graduate software engineer ireland",
        "entry level full stack ireland",
        "associate full stack developer ireland",
        "graduate web developer ireland",
        "intern full stack developer ireland",
        "junior react developer ireland",
        "junior node.js developer ireland",
    ]),
    ("Production Support", [
        "junior production support engineer ireland",
        "graduate application support engineer ireland",
        "entry level IT support analyst ireland",
        "associate application support ireland",
        "junior devops engineer ireland",
        "graduate site reliability engineer ireland",
        "intern production support ireland",
    ]),
]

RESULTS_PER_QUERY = 8   # per source per query

# ── Experience filter ──────────────────────────────────────────────────────────
SENIOR_TITLE_KEYWORDS = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|head\s+of|director|vp\b|vice\s+president"
    r"|architect|manager|consultant|expert|specialist\s+iii|level\s+[4-9]"
    r"|[4-9]\+?\s*years?|[1-9][0-9]\+?\s*years?)\b",
    re.IGNORECASE
)
JUNIOR_TITLE_KEYWORDS = re.compile(
    r"\b(junior|jr\.?|graduate|grad\b|intern|trainee|associate|entry.?level"
    r"|new\s+grad|early\s+career|apprentice|1st\s+year|2nd\s+year|3rd\s+year"
    r"|mid.?level|software\s+engineer\s+i{1,2}$|engineer\s+i{1,2}$)\b",
    re.IGNORECASE
)

def is_experience_appropriate(title: str) -> bool:
    if JUNIOR_TITLE_KEYWORDS.search(title):
        return True
    if SENIOR_TITLE_KEYWORDS.search(title):
        return False
    return True   # neutral titles (Software Engineer, Python Developer, etc.) → include

def slug(text):
    text = re.sub(r"[^a-z0-9\s]", "", text.lower().strip())
    return re.sub(r"\s+", "_", text)[:40]

def job_id(company, title):
    return hashlib.md5(f"{slug(company)}_{slug(title)}".encode()).hexdigest()[:10]

# ── Apify RAG browser helper ───────────────────────────────────────────────────
def rag_fetch(client, url, timeout=120):
    try:
        run   = client.actor("apify/rag-web-browser").call(
            run_input={"startUrls": [{"url": url}], "maxResults": 1},
            timeout_secs=timeout,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        if not items:
            return ""
        return items[0].get("text", "") or items[0].get("markdown", "")
    except Exception as e:
        print(f"    ⚠  RAG fetch failed: {e}")
        return ""

# ── LinkedIn search ────────────────────────────────────────────────────────────
def search_linkedin(client, query, max_results=8):
    url = (
        "https://www.linkedin.com/jobs/search/"
        f"?keywords={query.replace(' ', '%20')}"
        "&location=Ireland&f_TPR=r2592000&f_E=1%2C2%2C3"
    )
    text = rag_fetch(client, url)
    jobs = parse_linkedin_text(text, max_results)
    print(f"        LinkedIn → {len(jobs)} results")
    return jobs

def parse_linkedin_text(text, max_results):
    jobs, seen = [], set()
    patterns = [
        # "Title at Company · Location · N days ago"
        r"([A-Z][^\n]{4,79}?)\s+at\s+([A-Z][^\n]{2,60}?)\s*[\n·•]\s*([^\n]+?)\s*[\n·•]\s*\d+\s*(?:days?|weeks?|hours?|minutes?)\s*ago",
        # "Title\nCompany\nLocation, Ireland"
        r"^([A-Z][^\n]{4,79})\n([A-Z][^\n]{2,60})\n([^\n]*(?:Ireland|Dublin|Cork|Galway|Limerick|Waterford|Remote)[^\n]*)",
        # "Title\nCompany\n·\nLocation"
        r"([A-Z][^\n]{4,79})\n([A-Z][^\n]{2,60})\n·\n([^\n]+)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.MULTILINE):
            title   = m.group(1).strip().rstrip("·•").strip()
            company = m.group(2).strip().rstrip("·•").strip() if len(m.groups()) > 1 else "Unknown"
            loc     = m.group(3).strip()[:80]                  if len(m.groups()) > 2 else "Ireland"
            key     = f"{title.lower()[:60]}_{company.lower()[:40]}"
            if key not in seen and 5 < len(title) < 90 and len(company) > 1:
                seen.add(key)
                jobs.append({"title": title, "company": company, "location": loc, "source": "LinkedIn"})
            if len(jobs) >= max_results:
                return jobs
    return jobs

# ── Indeed IE search ────────────────────────────────────────────────────────────
def search_indeed(client, query, max_results=8):
    url = (
        "https://ie.indeed.com/jobs"
        f"?q={query.replace(' ', '+')}"
        "&l=Ireland&fromage=30&explvl=entry_level&sort=date"
    )
    text = rag_fetch(client, url)
    jobs = parse_indeed_text(text, max_results)
    print(f"        Indeed   → {len(jobs)} results")
    return jobs

def parse_indeed_text(text, max_results):
    jobs, seen = [], set()
    patterns = [
        # Indeed card: "Title\nCompany\nLocation"
        r"^([A-Z][^\n]{4,79})\n([A-Z][^\n]{2,60})\n([^\n]*(?:Ireland|Dublin|Cork|Galway|Limerick|Waterford|Remote|Hybrid|On-site)[^\n]*)",
        # "Title - Company"
        r"^([A-Z][^\n]{4,79})\s*[-–]\s*([A-Z][^\n]{2,60})\n([^\n]*(?:Ireland|Dublin|Cork|Galway|Limerick)[^\n]*)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.MULTILINE):
            title   = m.group(1).strip()
            company = m.group(2).strip() if len(m.groups()) > 1 else "Unknown"
            loc     = m.group(3).strip()[:80] if len(m.groups()) > 2 else "Ireland"
            key     = f"{title.lower()[:60]}_{company.lower()[:40]}"
            if key not in seen and 5 < len(title) < 90 and len(company) > 1:
                seen.add(key)
                jobs.append({"title": title, "company": company, "location": loc, "source": "Indeed"})
            if len(jobs) >= max_results:
                return jobs
    return jobs

# ── IrishJobs.ie search ────────────────────────────────────────────────────────
def search_irishjobs(client, query, max_results=8):
    url = (
        "https://www.irishjobs.ie/Jobs"
        f"/{query.replace(' ', '-')}"
        "?JobCategoryId=2,3,5,11"
    )
    text = rag_fetch(client, url)
    jobs = parse_generic_text(text, max_results, "IrishJobs")
    print(f"        IrishJobs→ {len(jobs)} results")
    return jobs

# ── Jobs.ie search ─────────────────────────────────────────────────────────────
def search_jobsie(client, query, max_results=8):
    terms = query.replace(" ireland", "").replace(" ", "-")
    url   = f"https://www.jobs.ie/jobs/{terms}/ireland/"
    text  = rag_fetch(client, url)
    jobs  = parse_generic_text(text, max_results, "Jobs.ie")
    print(f"        Jobs.ie  → {len(jobs)} results")
    return jobs

# ── Company career page scraper ────────────────────────────────────────────────
# Each entry: (company_name, url, category)
COMPANY_CAREER_PAGES = [
    ("Microsoft",   "https://careers.microsoft.com/v2/global/en/locations/dublin.html",               "Full Stack / General SWE"),
    ("Google",      "https://www.google.com/about/careers/applications/jobs/results?location=Dublin,+Ireland&experience=EARLY&experience=MID", "Full Stack / General SWE"),
    ("Stripe",      "https://stripe.com/jobs/search?location=Dublin&teams=engineering",               "Java / Backend"),
    ("Amazon",      "https://www.amazon.jobs/en/search?base_query=software+engineer&loc_query=Dublin%2C+Ireland", "Full Stack / General SWE"),
    ("Workday",     "https://www.workday.com/en-us/company/careers/overview.html?q=software+engineer&location=Dublin", "Full Stack / General SWE"),
    ("HubSpot",     "https://www.hubspot.com/careers/jobs?hubs_content=www.hubspot.com%2Fcareers&q=software+engineer&country=Ireland", "Full Stack / General SWE"),
    ("Salesforce",  "https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site?q=software+engineer&locationCountry=IE", "Full Stack / General SWE"),
    ("MongoDB",     "https://www.mongodb.com/careers/search?department=Engineering&location=Dublin%2C+Ireland", "Full Stack / General SWE"),
    ("Zendesk",     "https://jobs.zendesk.com/us/en/search-results?keywords=software+engineer&location=Dublin", "Full Stack / General SWE"),
    ("Intercom",    "https://www.intercom.com/careers/jobs?search=engineer&location=Dublin",          "Full Stack / General SWE"),
    ("Gong",        "https://www.gong.io/careers/#open-positions",                                    "Full Stack / General SWE"),
    ("Fidelity",    "https://www.fidelityinternational.com/careers/",                                 "Java / Backend"),
    ("Arista",      "https://www.arista.com/en/careers",                                              "Full Stack / General SWE"),
    ("Bentley",     "https://www.bentley.com/company/careers/?search=software+engineer&location=Dublin", "Full Stack / General SWE"),
    ("Canonical",   "https://canonical.com/careers/all?location=Ireland",                             "Python / Data / ML"),
    ("Etsy",        "https://careers.etsy.com/?country=IE",                                           "Java / Backend"),
]

def parse_company_page(text, company, max_results=10):
    """
    Parse raw text/markdown from a company career page to extract Dublin/Ireland job listings.
    Looks for title + location patterns.
    """
    jobs, seen = [], set()
    ireland_re = re.compile(r"\b(Dublin|Ireland|Cork|Galway|Limerick|Remote)\b", re.I)
    title_re   = re.compile(
        r"(?:^|\n)([A-Z][A-Za-z0-9 ,./\-&'()]{5,79})"
        r"(?:\n|\s*[-–·|]\s*)"
        r"(?:[^\n]*(?:Dublin|Ireland|Remote)[^\n]*)",
        re.MULTILINE
    )
    for m in title_re.finditer(text):
        title = m.group(1).strip().rstrip("-–·|•").strip()
        if not (5 < len(title) < 90):
            continue
        # Filter out navigation elements and generic headings
        skip_words = re.compile(
            r"^(Apply|View|Learn|Read|See|Sign|Join|Home|About|Contact|Benefits|Culture|Login"
            r"|Life at|Jobs in|Search|Filter|Careers|Explore|Skip|Showing|Sort|Page)\b",
            re.I
        )
        if skip_words.match(title):
            continue
        key = f"{title.lower()[:60]}_{company.lower()[:30]}"
        if key not in seen and is_experience_appropriate(title):
            seen.add(key)
            jobs.append({"title": title, "company": company, "location": "Dublin, Ireland", "source": f"{company} Careers"})
        if len(jobs) >= max_results:
            break
    return jobs

def search_company_careers(client, company, url, category, max_results=10):
    """Scrape a company's own career page for Dublin/Ireland roles."""
    print(f"    🏢  {company} careers page...")
    text = rag_fetch(client, url, timeout=90)
    jobs = parse_company_page(text, company, max_results)
    print(f"        {company} → {len(jobs)} results")
    return jobs, category

def parse_generic_text(text, max_results, source_name):
    """Generic parser that works across IrishJobs, Jobs.ie and similar boards."""
    jobs, seen = [], set()
    patterns = [
        r"^([A-Z][^\n]{4,79})\n([A-Z][^\n]{2,60})\n([^\n]*(?:Ireland|Dublin|Cork|Galway|Limerick|Waterford|Remote)[^\n]*)",
        r"([A-Z][^\n]{4,79}?)\s+at\s+([A-Z][^\n]{2,60}?)\s*[\n·]\s*([^\n]*(?:Ireland|Dublin|Cork|Galway)[^\n]*)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.MULTILINE):
            title   = m.group(1).strip()
            company = m.group(2).strip() if len(m.groups()) > 1 else "Unknown"
            loc     = m.group(3).strip()[:80] if len(m.groups()) > 2 else "Ireland"
            key     = f"{title.lower()[:60]}_{company.lower()[:40]}"
            if key not in seen and 5 < len(title) < 90 and len(company) > 1:
                seen.add(key)
                jobs.append({"title": title, "company": company, "location": loc, "source": source_name})
            if len(jobs) >= max_results:
                return jobs
    return jobs

# ── Apify Indeed scraper (structured JSON) ────────────────────────────────────
def search_indeed_scraper(client, query, max_results=8):
    """
    Use Apify's dedicated Indeed scraper for structured results — much more reliable
    than text parsing. Falls back gracefully if actor isn't available.
    """
    try:
        run = client.actor("misceres/indeed-scraper").call(
            run_input={
                "queries":    [query],
                "location":   "Ireland",
                "maxItems":   max_results,
                "saveHtml":   False,
                "startUrls":  [],
            },
            timeout_secs=180,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        jobs  = []
        for item in items:
            title   = item.get("positionName") or item.get("title") or ""
            company = item.get("company") or ""
            loc     = item.get("location") or "Ireland"
            if title and company and len(title) > 3:
                jobs.append({"title": title.strip(), "company": company.strip(),
                             "location": loc.strip(), "source": "Indeed"})
        print(f"        IndeedScraper → {len(jobs)} results")
        return jobs
    except Exception as e:
        print(f"        ⚠  Indeed scraper failed ('{query}'): {e}")
        return []

# ── Main ───────────────────────────────────────────────────────────────────────
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
    if source == "Indeed":
        apply_url = f"https://ie.indeed.com/jobs?q={title.replace(' ', '+')}&l=Ireland"
    elif source in ("IrishJobs", "Jobs.ie"):
        apply_url = f"https://www.irishjobs.ie/Jobs/{title.replace(' ', '-')}"
    else:
        apply_url = f"https://www.linkedin.com/jobs/search/?keywords={title.replace(' ', '%20')}&location=Ireland"
    return {
        "id":        job_id(company, title),
        "num":       next_num,
        "category":  category,
        "company":   company,
        "title":     title,
        "location":  loc,
        "source":    source,
        "posted":    datetime.now().strftime("%b %Y"),
        "apply_url": apply_url,
        "resume":    f"hari_{slug(company)}_{slug(title)}.pdf",
        "status":    "Not Applied",
        "added":     datetime.now().strftime("%Y-%m-%d"),
    }

def main():
    print(f"🔍  Starting multi-source job search — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    client       = ApifyClient(APIFY_TOKEN)
    existing     = load_existing_jobs()
    existing_ids = {j["id"] for j in existing}
    new_jobs     = []
    next_num     = max((j.get("num", 0) for j in existing), default=0) + 1

    for (category, queries) in SEARCHES:
        print(f"\n  📂  {category}")
        for query in queries:
            print(f"    🔎  {query}")
            # Pull from all 4 sources per query
            all_results = []
            all_results += search_linkedin(client, query, RESULTS_PER_QUERY)
            time.sleep(2)
            all_results += search_indeed_scraper(client, query, RESULTS_PER_QUERY)
            time.sleep(2)
            all_results += search_indeed(client, query, RESULTS_PER_QUERY)
            time.sleep(2)
            all_results += search_irishjobs(client, query, RESULTS_PER_QUERY)
            time.sleep(2)

            for r in all_results:
                if not is_experience_appropriate(r["title"]):
                    print(f"        ✗  Skip (senior): {r['title']}")
                    continue
                jid = job_id(r["company"], r["title"])
                if jid not in existing_ids:
                    entry = make_entry(r, category, next_num)
                    new_jobs.append(entry)
                    existing_ids.add(jid)
                    next_num += 1
                    print(f"        ✓  [{r.get('source','?')}] {r['title']} @ {r['company']}")

    # ── Company career pages ──────────────────────────────────────────────────
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
                    print(f"        ✓  [{r.get('source','?')}] {r['title']} @ {r['company']}")
        except Exception as e:
            print(f"    ⚠  {company} career page failed: {e}")

    all_jobs = existing + new_jobs
    save_jobs(all_jobs)
    print(f"\n✅  Total jobs: {len(all_jobs)}  |  New today: {len(new_jobs)}")
    return new_jobs

if __name__ == "__main__":
    main()
