#!/usr/bin/env python3
"""
Search for jobs in Ireland across all role categories using Apify.
Saves new jobs to web/data/jobs.json (deduplicates against existing).
"""
import os, re, json, hashlib, time
from datetime import datetime
from apify_client import ApifyClient

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE   = os.path.join(ROOT, "web", "data", "jobs.json")

# Role categories and their search terms — all targeting 0-3 years / graduate / junior
SEARCHES = [
    ("Java / Backend",  [
        "junior java developer ireland",
        "graduate java engineer ireland",
        "associate java developer ireland",
        "entry level spring boot developer ireland",
    ]),
    ("Python",          [
        "junior python developer ireland",
        "graduate python engineer ireland",
        "entry level python developer ireland",
    ]),
    ("Data Analyst",    [
        "junior data analyst ireland",
        "graduate data analyst ireland",
        "entry level business analyst ireland",
    ]),
    ("Data Scientist",  [
        "junior data scientist ireland",
        "graduate data scientist ireland",
        "entry level data scientist ireland",
    ]),
    ("AI / ML",         [
        "junior machine learning engineer ireland",
        "graduate ai engineer ireland",
        "entry level ml engineer ireland",
    ]),
    ("IT Support",      [
        "junior IT support engineer ireland",
        "graduate IT support ireland",
        "entry level desktop support ireland",
    ]),
    ("Full Stack",      [
        "junior full stack developer ireland",
        "graduate software engineer ireland",
        "entry level full stack ireland",
    ]),
    ("Production Support", [
        "junior production support engineer ireland",
        "graduate application support engineer ireland",
        "entry level IT support analyst ireland",
    ]),
]

RESULTS_PER_QUERY = 5   # jobs per search query

# ── Experience filter ────────────────────────────────────────────────────────
# Titles that signal 4+ years seniority — skip these entirely
SENIOR_TITLE_KEYWORDS = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|head\s+of|director|vp\b|vice\s+president"
    r"|architect|manager|consultant|expert|specialist\s+iii|level\s+[4-9]"
    r"|[4-9]\+?\s*years?|[1-9][0-9]\+?\s*years?)\b",
    re.IGNORECASE
)

# Titles that explicitly confirm 0-3 year suitability — always allow
JUNIOR_TITLE_KEYWORDS = re.compile(
    r"\b(junior|jr\.?|graduate|grad\b|intern|trainee|associate|entry.?level"
    r"|new\s+grad|early\s+career|apprentice|1st\s+year|2nd\s+year|3rd\s+year"
    r"|mid.?level|mid.?senior)\b",
    re.IGNORECASE
)

def is_experience_appropriate(title: str) -> bool:
    """Return True only if the job title is suitable for 0-3 years experience."""
    # Explicitly junior/grad → always include
    if JUNIOR_TITLE_KEYWORDS.search(title):
        return True
    # Contains senior/lead/etc. keywords → always exclude
    if SENIOR_TITLE_KEYWORDS.search(title):
        return False
    # Neutral title (e.g. "Software Engineer", "Python Developer") → include
    return True

def slug(text):
    text = re.sub(r"[^a-z0-9\s]", "", text.lower().strip())
    return re.sub(r"\s+", "_", text)[:40]

def job_id(company, title):
    return hashlib.md5(f"{slug(company)}_{slug(title)}".encode()).hexdigest()[:10]

def search_via_rag(client, query, max_results=5):
    """Use Apify RAG web browser to scrape LinkedIn Jobs search results."""
    url = (
        f"https://www.linkedin.com/jobs/search/"
        f"?keywords={query.replace(' ', '%20')}"
        f"&location=Ireland&f_TPR=r2592000&f_E=1%2C2%2C3"  # last 30 days, Internship + Entry + Associate (0-3 yrs)
    )
    try:
        run = client.actor("apify/rag-web-browser").call(
            run_input={"startUrls": [{"url": url}], "maxResults": 1},
            timeout_secs=120,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        if not items:
            return []
        text = items[0].get("text", "") or items[0].get("markdown", "")
        return parse_linkedin_text(text, max_results)
    except Exception as e:
        print(f"    ⚠  RAG search failed for '{query}': {e}")
        return []

def parse_linkedin_text(text, max_results):
    """
    Extract job listings from LinkedIn Jobs page text.
    Looks for patterns like: Title at Company · Location · N days ago
    """
    jobs = []
    # LinkedIn job card pattern variations
    patterns = [
        r"([A-Z][^\n]+?)\s+at\s+([A-Z][^\n]+?)\s*[\n·•]\s*([^\n]+?)\s*[\n·•]\s*(\d+\s*(?:days?|weeks?|hours?)\s*ago)",
        r"([A-Z][^\n]+Engineer[^\n]*|[A-Z][^\n]+Developer[^\n]*|[A-Z][^\n]+Analyst[^\n]*|[A-Z][^\n]+Scientist[^\n]*|[A-Z][^\n]+Support[^\n]*)\n([A-Z][^\n]+)\n([^\n]*Ireland[^\n]*)",
    ]
    seen = set()
    for pattern in patterns:
        for m in re.finditer(pattern, text, re.MULTILINE):
            title   = m.group(1).strip()
            company = m.group(2).strip() if len(m.groups()) > 1 else "Unknown"
            loc     = m.group(3).strip() if len(m.groups()) > 2 else "Ireland"
            key = f"{title.lower()}_{company.lower()}"
            if key not in seen and len(title) > 5 and len(title) < 80:
                seen.add(key)
                jobs.append({"title": title, "company": company, "location": loc})
            if len(jobs) >= max_results:
                break
        if jobs:
            break
    return jobs

def load_existing_jobs():
    if os.path.exists(JOBS_FILE):
        with open(JOBS_FILE, "r") as f:
            return json.load(f)
    return []

def save_jobs(jobs):
    os.makedirs(os.path.dirname(JOBS_FILE), exist_ok=True)
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2)

def main():
    print(f"🔍  Starting job search — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    client         = ApifyClient(APIFY_TOKEN)
    existing       = load_existing_jobs()
    existing_ids   = {j["id"] for j in existing}
    new_jobs       = []
    next_num       = max((j.get("num", 0) for j in existing), default=0) + 1

    for (category, queries) in SEARCHES:
        print(f"\n  📂  {category}")
        for query in queries:
            print(f"      Searching: {query}")
            results = search_via_rag(client, query, RESULTS_PER_QUERY)
            for r in results:
                # Skip jobs requiring more than 3 years experience
                if not is_experience_appropriate(r["title"]):
                    print(f"      ✗  Skipped (too senior): {r['title']} @ {r['company']}")
                    continue
                jid = job_id(r["company"], r["title"])
                if jid not in existing_ids:
                    entry = {
                        "id":        jid,
                        "num":       next_num,
                        "category":  category,
                        "company":   r["company"],
                        "title":     r["title"],
                        "location":  r.get("location", "Ireland"),
                        "source":    "LinkedIn",
                        "posted":    datetime.now().strftime("%b %Y"),
                        "apply_url": f"https://www.linkedin.com/jobs/search/?keywords={r['title'].replace(' ', '%20')}&location=Ireland",
                        "resume":    f"hari_{slug(r['company'])}_{slug(r['title'])}.pdf",
                        "status":    "Not Applied",
                        "added":     datetime.now().strftime("%Y-%m-%d"),
                    }
                    new_jobs.append(entry)
                    existing_ids.add(jid)
                    next_num += 1
                    print(f"      ✓  {r['title']} @ {r['company']}")
            time.sleep(3)   # be gentle between requests

    all_jobs = existing + new_jobs
    save_jobs(all_jobs)
    print(f"\n✅  Total jobs: {len(all_jobs)}  |  New today: {len(new_jobs)}")
    return new_jobs

if __name__ == "__main__":
    main()
