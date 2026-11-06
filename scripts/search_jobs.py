#!/usr/bin/env python3
"""
Multi-platform Ireland job search pipeline.

Sources:
  1. LinkedIn   — worldunboxer/rapid-linkedin-scraper ($0.00035/job incl. details;
                  jobs already in jobs.json are skipped free)
  2. Indeed IE  — valig/indeed-jobs-scraper (99.8% success, $0.0001/result)
  3. Glassdoor  — valig/glassdoor-jobs-scraper ($0.0004/result; SWE searches only)
  4. Company career pages — 16 companies via RAG browser (off unless
     SCRAPE_COMPANY_PAGES=1)

  (IrishJobs and Jobs.ie scrapers still exist below but are disabled in main();
  see the note there.)

All sources return structured data. Deduplicates against existing jobs.json.
"""
import os, re, json, hashlib, time, inspect
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta
from decimal import Decimal
from apify_client import ApifyClient

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE   = os.path.join(ROOT, "web", "data", "jobs.json")

# ── Role categories — MUST EXACTLY MATCH the chip values in web/index.html
# (Java / Backend, Python, Data Analyst, Data Scientist, AI / ML, IT Support,
# Full Stack, Production Support, Trust & Safety). If you add a new bucket here, also add a
# matching chip in the dashboard, otherwise those jobs won't appear under
# any filter.
#
# Order = priority: software-engineering buckets run first so a mid-run Apify
# credit exhaustion can't starve them.
SEARCHES = [
    ("Java / Backend", [
        "junior java developer",
        "graduate java engineer",
        "graduate java software engineer ireland",
        "associate software engineer java",
        "entry level backend developer",
        "graduate spring boot developer",
        "junior backend engineer",
        "software engineer java",
        "junior kotlin developer",
        "graduate backend engineer dublin",
    ]),
    ("Python", [
        "junior python developer",
        "graduate python engineer",
        "graduate python developer ireland",
        "entry level python developer",
        "junior data engineer",
        "graduate data engineer",
        "software engineer python",
        "graduate backend python ireland",
    ]),
    ("Full Stack", [
        "junior full stack developer",
        "graduate software engineer",
        "graduate software engineer ireland",
        "entry level software engineer",
        "associate software engineer",
        "junior react developer",
        "junior node.js developer",
        "software engineer new grad",
        "junior web developer",
        "graduate fullstack developer dublin",
        "graduate programme software engineer",
    ]),
    ("Production Support", [
        "junior production support engineer",
        "graduate application support engineer",
        "junior devops engineer",
        "graduate site reliability engineer",
        "associate DevOps engineer",
        "junior cloud engineer",
        "graduate cloud engineer",
        "junior platform engineer",
        "graduate AWS engineer",
        "junior Azure engineer",
        "junior kubernetes engineer",
        "cloud support engineer",
        "graduate SRE ireland",
    ]),
    # Experience cap for this bucket is enforced separately (≤3 years) —
    # see exceeds_max_experience().
    ("Trust & Safety", [
        "trust and safety",
        "trust and safety analyst",
        "trust and safety specialist",
        "content moderator",
        "content reviewer",
        "policy enforcement specialist",
        "online safety analyst",
        "integrity analyst",
        "community operations specialist",
    ]),
    ("AI / ML", [
        "junior machine learning engineer",
        "graduate AI engineer",
        "graduate machine learning engineer",
        "entry level ML engineer",
        "associate machine learning engineer",
        "junior NLP engineer",
        "AI software engineer entry level",
        "graduate deep learning engineer",
        "graduate AI engineer ireland",
    ]),
    ("Data Scientist", [
        "graduate data scientist",
        "junior data scientist",
        "associate data scientist",
        "graduate data scientist ireland",
        "entry level data scientist",
        "data science graduate programme",
    ]),
    ("Data Analyst", [
        "junior data analyst",
        "graduate data analyst",
        "graduate data analyst ireland",
        "entry level data analyst",
        "associate business analyst",
        "graduate business intelligence analyst",
        "junior SQL analyst",
        "data analyst graduate dublin",
        "graduate business analyst data",
    ]),
    ("IT Support", [
        "junior IT support engineer",
        "graduate IT support",
        "entry level desktop support",
        "associate service desk analyst",
        "junior helpdesk engineer",
        "IT support analyst",
        "junior systems administrator",
        "graduate IT support ireland",
    ]),
]

# Broad software-engineering searches with no seniority word. Most Irish SWE
# postings aren't titled "junior"/"graduate", so the bucket queries above miss
# them. These run before everything else; senior titles are still dropped by
# is_experience_appropriate() and strict_category() files each result under
# its real domain (Java, Python, DevOps → Production Support, ...).
BROAD_SWE_QUERIES = [
    "software engineer",
    "software developer",
    "software engineer II",
    "java developer",
    "backend engineer",
    "python developer",
    "full stack developer",
    "frontend developer",
    ".net developer",
    "devops engineer",
    "site reliability engineer",
    "platform engineer",
    "cloud engineer",
    "data engineer",
]

# Buckets that get the software-engineering treatment: more results per query
# and Glassdoor coverage. Glassdoor costs 4x Indeed per result and mostly
# repeats LinkedIn/Indeed for the other buckets, so they skip it.
SWE_BUCKETS = {"Java / Backend", "Python", "Full Stack", "Production Support"}

# Maximum results per query per source.
RESULTS_PER_QUERY     = 15
SWE_RESULTS_PER_QUERY = 30
BROAD_SWE_RESULTS     = 100

# How many days back each source looks. Daily runs only need a few days (dedup
# skips known jobs); after a gap, run the workflow by hand with a larger
# lookback_days to catch up. Indeed can't go past 14 days.
LOOKBACK_DAYS = max(1, int(os.environ.get("LOOKBACK_DAYS") or 3))

# The 16 career pages below go through the RAG browser — the costliest calls in
# a run — and yielded 1 job in total in a full run (Oct 2026). Off unless asked.
SCRAPE_COMPANY_PAGES = os.environ.get("SCRAPE_COMPANY_PAGES") == "1"

# Which job boards to query (comma-separated). A retry after one board failed
# can re-run just that board instead of paying again for the others.
SOURCES = {s.strip().lower() for s in
           (os.environ.get("SOURCES") or "linkedin,indeed,glassdoor").split(",") if s.strip()}

# A healthy Glassdoor run takes ~50 s; anything past this is a hung retry loop.
GLASSDOOR_TIMEOUT_SECS = 90

# The LinkedIn actor's own limit is 12 hours, so one search that keeps paging
# (e.g. digging past hundreds of known jobs for new ones) could stall a whole
# run. A timed-out run still returns what it collected.
LINKEDIN_TIMEOUT_SECS = 180

# Stop starting new searches after this long and move on to saving + resumes,
# so a slow run can never hit GitHub's 6-hour limit and lose everything.
# Searches run in priority order, so only the lowest-priority ones get cut.
SEARCH_BUDGET_MINUTES = int(os.environ.get("SEARCH_BUDGET_MINUTES") or 150)

# ── Company career pages (RAG browser fallback) ───────────────────────────────
COMPANY_CAREER_PAGES = [
    ("Microsoft",   "https://careers.microsoft.com/v2/global/en/locations/dublin.html",               "Full Stack"),
    ("Google",      "https://www.google.com/about/careers/applications/jobs/results?location=Dublin,+Ireland", "Full Stack"),
    ("Stripe",      "https://stripe.com/jobs/search?location=Dublin&teams=engineering",               "Java / Backend"),
    ("Amazon",      "https://www.amazon.jobs/en/search?base_query=software+engineer&loc_query=Dublin%2C+Ireland", "Full Stack"),
    ("Workday",     "https://www.workday.com/en-us/company/careers/overview.html?q=software+engineer&location=Dublin", "Full Stack"),
    ("HubSpot",     "https://www.hubspot.com/careers/jobs?q=software+engineer&country=Ireland",       "Full Stack"),
    ("Salesforce",  "https://salesforce.wd12.myworkdayjobs.com/en-US/External_Career_Site?q=software+engineer&locationCountry=IE", "Full Stack"),
    ("MongoDB",     "https://www.mongodb.com/careers/search?department=Engineering&location=Dublin%2C+Ireland", "Full Stack"),
    ("Zendesk",     "https://jobs.zendesk.com/us/en/search-results?keywords=software+engineer&location=Dublin", "Full Stack"),
    ("Intercom",    "https://www.intercom.com/careers/jobs?search=engineer&location=Dublin",          "Full Stack"),
    ("Gong",        "https://www.gong.io/careers/#open-positions",                                    "Full Stack"),
    ("Arista",      "https://www.arista.com/en/careers",                                              "Full Stack"),
    ("Bentley",     "https://www.bentley.com/company/careers/?search=software+engineer&location=Dublin", "Full Stack"),
    ("Canonical",   "https://canonical.com/careers/all?location=Ireland",                             "Python"),
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

# Years-of-experience requirement stated in a JD body, e.g. "4+ years of
# experience", "3-5 years' experience", "minimum of 5 years in ...". For a
# range the lower bound counts ("3-5 years" is fine under a 3-year cap).
_YEARS_REQ = re.compile(
    r"(?i)(?:minimum (?:of )?|at least )?(\d{1,2})\s*(?:\+|plus)?\s*"
    r"(?:(?:-|–|to)\s*\d{1,2}\s*\+?\s*)?(?:years?|yrs?)'?"
    r"(?=[^.]{0,60}?\b(?:experience|background|in (?:a |an )?(?:similar|trust|content|moderation|policy|operations)))"
)

def exceeds_max_experience(description: str, max_years: int = 3) -> bool:
    """True if the JD asks for more than max_years of experience. Used for the
    Trust & Safety bucket only (other domains rely on the title filter)."""
    for m in _YEARS_REQ.finditer(description or ""):
        if int(m.group(1)) > max_years:
            return True
    return False

# Companies whose listings should never enter the tracker (gig-work / AI-trainer
# spam that floods every search query with hundreds of near-duplicate roles).
COMPANY_BLOCKLIST = {"dataannotation", "data annotation"}

def is_company_allowed(company: str) -> bool:
    c = (company or "").lower().strip()
    return not any(b in c for b in COMPANY_BLOCKLIST)

# Titles that aren't software-engineering roles. Scrapers ingest these because
# generic queries like "graduate engineer" or "junior analyst" match civil/lab/
# admin postings. Drop them at ingestion so the tracker stays SWE-focused.
NON_SWE_TITLE = re.compile(
    r"\b("
    # Construction / civil / mechanical / electrical engineering
    r"civil (engineer|technician)|graduate civil|civil engineering|"
    r"mechanical engineer|graduate mechanical|hvac|"
    r"(graduate )?electrical engineer|power engineer|"
    r"wastewater|geospatial|surveyor|site engineer|construction|landscape (architect|engineer)|"
    r"roads and streets|elec\. engineer|"
    r"chemical engineer|process engineer|quantity surveyor|building services|"
    r"ehs |environmental consultant|heritage consultant|continuous improvement|"
    # Lab / Medical / Biotech / Pharma
    r"medical scientist|laboratory support|lab analyst|biopharma|biomedical|microbiology|"
    r"pharmacology|haematology|qc analyst|complaint investigation|"
    r"(associate|principal) research scientist|pharmaceutical|"
    # Sales / Marketing / Finance / Admin (non-technical)
    r"sales path|sales (graduate|associate)|marketing analyst|"
    r"accounts payable|accounts receivable|patient administrator|"
    r"junior administrator|landscape architect|change analyst|"
    r"project manager- change|graduate sales|business unit coordinator|"
    r"document controller|junior business analyst - revenue|financial analyst(?! .*tech)|"
    r"graduate health (and|&) safety|health (and|&) safety consultant"
    r")\b",
    re.I,
)

def is_swe_title(title: str) -> bool:
    return not NON_SWE_TITLE.search(title or "")

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

# ── Cross-version helper: apify-client 1.x returns a dict from .call(),
# 2.x returns a Run object. Both expose the dataset ID; this helper grabs it.
def _dataset_id(run):
    if run is None:
        return None
    if hasattr(run, "default_dataset_id"):
        return run.default_dataset_id
    if isinstance(run, dict):
        return run.get("defaultDatasetId")
    return getattr(run, "defaultDatasetId", None)

# apify-client 1.x takes timeout_secs=int; 3.x takes run_timeout=timedelta.
# Passing the wrong name raises TypeError, which callers swallow — so pick
# whichever the installed version actually supports.
def _run_timeout_kwargs(actor_client, secs):
    params = inspect.signature(actor_client.call).parameters
    if "run_timeout" in params:
        return {"run_timeout": timedelta(seconds=secs)}
    if "timeout_secs" in params:
        return {"timeout_secs": secs}
    return {}

# Cap what one actor run may return and charge. Without a cap, a pay-per-event
# actor needs credit for its default maximum (e.g. 1000 LinkedIn jobs) before
# it will start, so runs near the end of the monthly credit were refused.
# Apify rejects caps under $0.05 ("Maximum cost per run is less than the
# allowed minimum"), which killed 83 of 97 LinkedIn searches on 2026-11-05.
MIN_CHARGE_CAP_USD = 0.05

def _charge_cap_kwargs(actor_client, max_items, max_usd):
    params = inspect.signature(actor_client.call).parameters
    kw = {}
    if "max_items" in params:
        kw["max_items"] = max_items
    if "max_total_charge_usd" in params:
        kw["max_total_charge_usd"] = Decimal(str(round(max(max_usd, MIN_CHARGE_CAP_USD), 4)))
    return kw

# LinkedIn job IDs already in jobs.json or seen earlier in this run. Sent as
# exclude_job_ids: the actor skips those jobs without charging for them, so
# overlapping searches and wide catch-up windows only pay for new postings.
SEEN_LINKEDIN_IDS = set()
_LINKEDIN_JOB_ID = re.compile(r"linkedin\.com/jobs/view/(?:[^/?#]*-)?(\d{6,})")

def linkedin_job_id(url):
    m = _LINKEDIN_JOB_ID.search(url or "")
    return m.group(1) if m else None

def _indeed_date_posted(days):
    """Indeed only accepts 1, 3, 7 or 14 days: round up, capped at 14."""
    for opt in (1, 3, 7, 14):
        if days <= opt:
            return str(opt)
    return "14"

def rag_fetch(client, url, query="software engineer ireland", timeout=120):
    try:
        run   = client.actor("apify/rag-web-browser").call(
            run_input={"startUrls": [{"url": url}], "maxResults": 1, "query": query},
        )
        items = list(client.dataset(_dataset_id(run)).iterate_items())
        if not items:
            return ""
        return items[0].get("text", "") or items[0].get("markdown", "")
    except Exception as e:
        print(f"    ⚠  RAG fetch failed: {e}")
        return ""

# ── 1. LinkedIn — worldunboxer/rapid-linkedin-scraper (FREE) ─────────────────
def search_linkedin(client, query, max_results=RESULTS_PER_QUERY):
    """
    Dedicated LinkedIn scraper. Returns structured job objects.
    The actor's inputs changed in 2026: titles go in a jobs_titles list and the
    posting window is in seconds; the old experience_level / job_type /
    "r2592000" fields are no longer read, so seniority is filtered by title.
    """
    try:
        actor = client.actor("worldunboxer/rapid-linkedin-scraper")
        run = actor.call(
            run_input={
                "jobs_titles":         [query],
                "location":            "Ireland",
                "jobs_entries":        max_results,
                "include_job_details": True,   # full description, used for tailoring
                "job_post_time":       str(LOOKBACK_DAYS * 86400),
                "exclude_job_ids":     sorted(SEEN_LINKEDIN_IDS),
            },
            **_run_timeout_kwargs(actor, LINKEDIN_TIMEOUT_SECS),
            # $0.0001/job + $0.00025 detail enrichment, plus start fees
            **_charge_cap_kwargs(actor, max_results, max_results * 0.0005 + 0.01),
        )
        items = list(client.dataset(_dataset_id(run)).iterate_items())
        jobs  = []
        for item in items:
            title   = (_s(item.get("job_title")) or _s(item.get("title")) or "").strip()
            company = (_s(item.get("company_name")) or _s(item.get("company")) or "").strip()
            loc     = (_s(item.get("job_location")) or _s(item.get("location")) or "Ireland").strip()
            url     = item.get("job_url") or item.get("url") or ""
            lid     = linkedin_job_id(url) or (str(item["job_id"]) if item.get("job_id") else None)
            if lid:
                SEEN_LINKEDIN_IDS.add(lid)
            desc    = (_s(item.get("description")) or _s(item.get("job_description")) or
                       _s(item.get("jobDescription")) or _s(item.get("snippet")) or "").strip()
            if title and company and len(title) > 3:
                jobs.append({"title": title, "company": company,
                             "location": loc, "source": "LinkedIn", "url": url,
                             "description": desc[:6000] if desc else ""})
        print(f"        LinkedIn   → {len(jobs)} results")
        return jobs
    except Exception as e:
        import traceback
        print(f"        ⚠  LinkedIn scraper failed ('{query}'): {e}")
        traceback.print_exc()
        return []

# ── 2. Indeed IE — valig/indeed-jobs-scraper (99.8% success) ─────────────────
def search_indeed(client, query, max_results=RESULTS_PER_QUERY):
    """
    Dedicated Indeed scraper — country=ie for Ireland, last LOOKBACK_DAYS
    (Indeed caps the window at 14 days).
    """
    try:
        actor = client.actor("valig/indeed-jobs-scraper")
        run = actor.call(
            run_input={
                "country":    "ie",
                "title":      query,
                "location":   "Ireland",
                "limit":      max_results,
                "datePosted": _indeed_date_posted(LOOKBACK_DAYS),
            },
            # $0.0001/result plus start fees
            **_charge_cap_kwargs(actor, max_results, max_results * 0.00015 + 0.01),
        )
        items = list(client.dataset(_dataset_id(run)).iterate_items())
        jobs  = []
        # Since the actor's Sep 2026 update, company/location/description are
        # nested objects (employer.name, location.city, description.text);
        # older runs returned flat strings. Accept both.
        def sub(obj, key):
            return _s(obj.get(key)) if isinstance(obj, dict) else ""
        for item in items:
            title   = (_s(item.get("title")) or _s(item.get("positionName")) or "").strip()
            company = (_s(item.get("company")) or _s(item.get("companyName")) or
                       sub(item.get("employer"), "name") or "").strip()
            loc     = (_s(item.get("location")) or sub(item.get("location"), "city") or "Ireland").strip()
            url     = item.get("url") or item.get("jobUrl") or ""
            desc    = (_s(item.get("description")) or sub(item.get("description"), "text") or
                       _s(item.get("jobDescription")) or _s(item.get("snippet")) or
                       _s(item.get("summary")) or "").strip()
            if title and company and len(title) > 3:
                jobs.append({"title": title, "company": company,
                             "location": loc, "source": "Indeed", "url": url,
                             "description": desc[:6000] if desc else ""})
        print(f"        Indeed     → {len(jobs)} results")
        return jobs
    except Exception as e:
        import traceback
        print(f"        ⚠  Indeed scraper failed ('{query}'): {e}")
        traceback.print_exc()
        return []

# ── 3. Glassdoor — valig/glassdoor-jobs-scraper (99.9% success) ──────────────
def search_glassdoor(client, query, max_results=RESULTS_PER_QUERY):
    """
    Dedicated Glassdoor scraper — Ireland location, last LOOKBACK_DAYS.
    """
    try:
        actor = client.actor("valig/glassdoor-jobs-scraper")
        # Glassdoor's crawler sometimes hangs ~2 min retrying; a timed-out
        # run still returns whatever it collected.
        run = actor.call(
            run_input={
                "keywords": query,
                "location": "Ireland",
                "daysOld":  LOOKBACK_DAYS,
                "limit":    max_results,
            },
            **_run_timeout_kwargs(actor, GLASSDOOR_TIMEOUT_SECS),
            # $0.0004/result plus start fees
            **_charge_cap_kwargs(actor, max_results, max_results * 0.0006 + 0.01),
        )
        items = list(client.dataset(_dataset_id(run)).iterate_items())
        jobs  = []
        for item in items:
            title   = (_s(item.get("jobTitle")) or _s(item.get("title")) or "").strip()
            _emp = item.get("employer") or item.get("company") or item.get("companyName") or ""
            _name = _emp.get("name", "") if isinstance(_emp, dict) else _emp
            company = (_s(_name) or "").strip()
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
        import traceback
        print(f"        ⚠  Glassdoor scraper failed ('{query}'): {e}")
        traceback.print_exc()
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
        )
        items = list(client.dataset(_dataset_id(run)).iterate_items())
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
        import traceback
        print(f"        ⚠  IrishJobs scraper failed ('{query}'): {e} — trying RAG fallback")
        traceback.print_exc()
        return _irishjobs_rag_fallback(client, query, max_results)

def _irishjobs_rag_fallback(client, query, max_results):
    url  = f"https://www.irishjobs.ie/Jobs/{query.replace(' ', '-')}?JobCategoryId=2,3,5,11"
    # Use site: prefix so Google returns irishjobs.ie results, not indeed.com
    text = rag_fetch(client, url, query=f"site:irishjobs.ie {query}")
    return _parse_generic(text, "IrishJobs", max_results)

# ── 5. Jobs.ie — RAG browser (no dedicated actor) ────────────────────────────
def search_jobsie(client, query, max_results=RESULTS_PER_QUERY):
    terms = query.replace(" ireland", "").replace(" ", "-")
    url   = f"https://www.jobs.ie/jobs/{terms}/ireland/"
    # Use site: prefix so Google returns jobs.ie results, not indeed.com (which 403s)
    text  = rag_fetch(client, url, query=f"site:jobs.ie {query}")
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

# ── Strict title-driven category classifier ─────────────────────────────────
# The search-query bucket that surfaced a job is a WEAK signal — a
# "junior python developer" search returns plenty of generic "Software
# Engineer" titles that aren't actually Python. So before we trust the
# search-bucket category, run the title through a strict title-based
# classifier and let it override when it has a strong signal.
#
# Order matters: most specific rules first; first match wins.
_STRICT_CATEGORY_RULES = [
    (re.compile(r"(?i)\b(machine learning|\bml\b engineer|\bai\b engineer|deep learning|\bnlp\b|computer vision|\bllm\b|gen[- ]?ai|generative ai|ai agents|mlops|ai/ml|ai engineer|ml ops|ai software)\b"), "AI / ML"),
    (re.compile(r"(?i)\bdata scientists?\b|biostatistician|statistical programmer|\bdata science\b"), "Data Scientist"),
    (re.compile(r"(?i)\b(data analyst|bi analyst|business intelligence|reporting analyst|analytics analyst)\b"), "Data Analyst"),
    (re.compile(r"(?i)\b(helpdesk|help desk|service desk|desktop support|ict support|technical support|it support|l1 support|l2 support|level 1 support|level 2 support|systems? admin)\b"), "IT Support"),
    (re.compile(r"(?i)\b(devops|\bsre\b|site reliability|cloud engineer|platform engineer|aws engineer|azure engineer|kubernetes|infrastructure engineer|terraform|application support|production support|reliability engineer|cloud operations|cloud platform|cloud architect|cloud developer|cloud security|cybersecurity|cyber security|security engineer|qa engineer|test automation)\b"), "Production Support"),
    (re.compile(r"(?i)\b(react|vue|angular|frontend|front[- ]end|\bui\b engineer|\bui\b developer|full[- ]?stack|fullstack|mobile (engineer|developer)|\bios\b engineer|android (engineer|developer)|web developer|wordpress)\b"), "Full Stack"),
    (re.compile(r"(?i)\b(java\b|spring boot|jvm|scala (engineer|developer)|kotlin (engineer|developer)|backend (engineer|developer|software)|back[- ]end (engineer|developer))\b"), "Java / Backend"),
    (re.compile(r"(?i)\b(python|django|flask|fastapi|pyspark|airflow developer)\b"), "Python"),
    (re.compile(r"(?i)\bdata engineer\b"), "Python"),
    (re.compile(r"(?i)\b(software engineer|software developer|sr software|associate software|junior software|graduate software|software internship)\b"), "Full Stack"),
]

_TS_TITLE = re.compile(
    r"(?i)\b(trust\s*(&|and)\s*safety|content (moderat\w*|review\w*|polic\w*|safety|integrity)"
    r"|moderator|policy enforcement|community (operations|standards|integrity|safety)"
    r"|online safety|user safety|integrity (analyst|specialist|operations|associate)"
    r"|abuse (analyst|investigat\w*|specialist)|safety (analyst|specialist|associate|agent))\b"
)
# SWE roles on T&S teams ("Trust & Safety Software Engineer") stay in their
# engineering domain.
_ENGINEERING_TITLE = re.compile(r"(?i)\b(engineer|developer|scientist|programmer|architect)\b")

def is_ts_search_noise(title: str, bucket: str) -> bool:
    """T&S searches also surface unrelated engineering roles. If no title rule
    claims one, it would inherit the T&S bucket — and get the T&S resume
    format. Drop it; the engineering searches find genuine ones."""
    return (bucket == "Trust & Safety"
            and strict_category(title, fallback=None) is None
            and bool(_ENGINEERING_TITLE.search(title or "")))

def strict_category(title: str, fallback: str) -> str:
    """Return the strict title-driven category, or fallback if no rule matches."""
    if _TS_TITLE.search(title or "") and not _ENGINEERING_TITLE.search(title or ""):
        return "Trust & Safety"
    for pat, cat in _STRICT_CATEGORY_RULES:
        if pat.search(title or ""):
            return cat
    return fallback

def make_entry(r, category, next_num):
    title   = r["title"]
    company = r["company"]
    # Override the search-bucket category with strict title classification.
    # Falls back to the search-bucket category only when no rule matches.
    category = strict_category(title, fallback=category)
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
    print(f"    Sources: {', '.join(sorted(SOURCES))} (Glassdoor: SWE searches only)"
          f"{' | 16 company sites' if SCRAPE_COMPANY_PAGES else ''}")
    client       = ApifyClient(APIFY_TOKEN)
    # One client per board: each board's searches run one at a time in its own
    # worker thread, so no client is shared between threads.
    board_client = {b: ApifyClient(APIFY_TOKEN) for b in ("linkedin", "indeed", "glassdoor")}
    pool         = ThreadPoolExecutor(max_workers=3)
    started      = time.time()
    existing     = load_existing_jobs()
    existing_ids = {j["id"] for j in existing}
    SEEN_LINKEDIN_IDS.update(filter(None, (linkedin_job_id(j.get("apply_url")) for j in existing)))
    print(f"    Lookback: {LOOKBACK_DAYS} days  |  known LinkedIn jobs skipped: {len(SEEN_LINKEDIN_IDS)}")
    new_jobs     = []
    next_num     = max((j.get("num", 0) for j in existing), default=0) + 1

    # (label, fallback category, queries, results per source, use Glassdoor)
    plan = [("Software engineering (broad)", "Full Stack", BROAD_SWE_QUERIES, BROAD_SWE_RESULTS, True)]
    plan += [(cat, cat, qs,
              SWE_RESULTS_PER_QUERY if cat in SWE_BUCKETS else RESULTS_PER_QUERY,
              cat in SWE_BUCKETS)
             for cat, qs in SEARCHES]

    out_of_time = False
    for (label, category, queries, limit, use_glassdoor) in plan:
        print(f"\n  📂  {label}")
        for query in queries:
            if time.time() - started > SEARCH_BUDGET_MINUTES * 60:
                out_of_time = True
                break
            print(f"    🔎  {query}")

            # The boards are searched at the same time (≈3.2 GB of Apify memory
            # together, well inside the plan's limit), so a query takes as long
            # as its slowest board instead of all three added up.
            futures = []
            if "linkedin" in SOURCES:
                futures.append(pool.submit(search_linkedin, board_client["linkedin"], query, limit))
            # Indeed IE ($0.0001/result)
            if "indeed" in SOURCES:
                futures.append(pool.submit(search_indeed, board_client["indeed"], query, limit))
            # Glassdoor ($0.0004/result) — software-engineering searches only
            if use_glassdoor and "glassdoor" in SOURCES:
                futures.append(pool.submit(search_glassdoor, board_client["glassdoor"], query, min(limit, 50)))
            all_results = []
            for f in futures:          # LinkedIn, Indeed, Glassdoor order — as before
                all_results += f.result()

            # IrishJobs and Jobs.ie are disabled: the IrishJobs actor ignores
            # the "keywords" input (returns the same 15 generic Dublin jobs
            # for every query) and is now 403-blocked, burning residential-
            # proxy credit on retries; Jobs.ie 403s every request. Together
            # they cost ~1.5 min per query for zero usable results.

            for r in all_results:
                if not is_experience_appropriate(r["title"]):
                    continue
                if not is_company_allowed(r["company"]):
                    continue
                if not is_swe_title(r["title"]):
                    continue
                if is_ts_search_noise(r["title"], category):
                    continue
                if (strict_category(r["title"], category) == "Trust & Safety"
                        and exceeds_max_experience(_s(r.get("description", "")))):
                    continue
                jid = job_id(r["company"], r["title"])
                if jid not in existing_ids:
                    entry = make_entry(r, category, next_num)
                    new_jobs.append(entry)
                    existing_ids.add(jid)
                    next_num += 1
                    print(f"        ✓  [{r.get('source','?')}] {r['title']} @ {r['company']}")
        if out_of_time:
            print(f"\n  ⏱  Search budget ({SEARCH_BUDGET_MINUTES} min) used up — skipping the remaining searches")
            break
    pool.shutdown(wait=True)

    # ── Company career pages ────────────────────────────────────────────────
    if SCRAPE_COMPANY_PAGES:
        print("\n\n🏢  Scraping company career pages...")
    else:
        print("\n\n🏢  Company career pages skipped (set SCRAPE_COMPANY_PAGES=1 to enable)")
    for (company, url, cat) in (COMPANY_CAREER_PAGES if SCRAPE_COMPANY_PAGES else []):
        try:
            results, category = search_company_careers(client, company, url, cat)
            time.sleep(3)
            for r in results:
                if not is_experience_appropriate(r["title"]):
                    continue
                if not is_company_allowed(r["company"]):
                    continue
                if not is_swe_title(r["title"]):
                    continue
                if (strict_category(r["title"], category) == "Trust & Safety"
                        and exceeds_max_experience(_s(r.get("description", "")))):
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
