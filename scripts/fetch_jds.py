#!/usr/bin/env python3
"""
fetch_jds.py — Backfill job descriptions for jobs that don't have one yet.

Strategy:
  1. Loop through all jobs in jobs.json where description is missing/empty.
  2. Fetch each apply_url using the Apify RAG web browser actor.
  3. Extract the job description text from the fetched content.
  4. Save back to jobs.json under a "description" field.
  5. Optionally re-generate the resume PDF with the new description.

Run this once to backfill existing jobs, then search_jobs.py captures descriptions
for all new jobs going forward automatically.

Usage:
    python scripts/fetch_jds.py                  # backfill only, no regen
    python scripts/fetch_jds.py --regen          # backfill + regenerate PDFs
    python scripts/fetch_jds.py --limit 10       # only process first 10 missing
    python scripts/fetch_jds.py --num 37         # fetch JD for job #37 only
"""
import os, re, json, time, argparse, sys
from apify_client import ApifyClient

APIFY_TOKEN = os.environ.get("APIFY_TOKEN", "")
ROOT        = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE   = os.path.join(ROOT, "web", "data", "jobs.json")

# Maximum characters to store from a fetched JD (keeps jobs.json lean)
MAX_DESC_CHARS = 6000

# Noise patterns to strip from fetched page text
_NOISE = re.compile(
    r"(sign in|log in|create account|cookies?|privacy policy|terms of (use|service)"
    r"|linkedin|share this job|save job|report this job|similar jobs"
    r"|apply now|easy apply|get job alerts|back to jobs|view all jobs"
    r"|© \d{4}|all rights reserved)",
    re.IGNORECASE,
)


def _clean_page_text(raw: str) -> str:
    """Remove boilerplate navigation/footer lines, keep job description lines."""
    lines = raw.splitlines()
    kept  = []
    for line in lines:
        line = line.strip()
        if not line or len(line) < 15:
            continue
        if _NOISE.search(line):
            continue
        kept.append(line)
    return "\n".join(kept)


def _extract_description(page_text: str, title: str, company: str) -> str:
    """
    Try to isolate the job description body from a full page scrape.
    Falls back to returning a cleaned version of the full text.
    """
    text = _clean_page_text(page_text)

    # Common JD section markers
    section_re = re.compile(
        r"(?:about the role|about this role|job description|responsibilities|"
        r"what you.{0,10}do|what we.{0,10}looking for|the role|overview|"
        r"position summary|role overview)",
        re.IGNORECASE,
    )
    m = section_re.search(text)
    if m:
        # Take text from this marker to end (or 6000 chars)
        text = text[m.start():]

    return text[:MAX_DESC_CHARS].strip()


def rag_fetch_jd(client: ApifyClient, url: str, title: str, company: str,
                 timeout: int = 90) -> str:
    """
    Use Apify RAG web browser to fetch a job posting URL and extract the
    job description text.
    """
    try:
        run   = client.actor("apify/rag-web-browser").call(
            run_input={"startUrls": [{"url": url}], "maxResults": 1},
            timeout_secs=timeout,
        )
        items = list(client.dataset(run["defaultDatasetId"]).iterate_items())
        if not items:
            return ""
        page_text = items[0].get("text", "") or items[0].get("markdown", "")
        return _extract_description(page_text, title, company)
    except Exception as e:
        print(f"    ⚠  RAG fetch failed for {url}: {e}")
        return ""


def load_jobs():
    with open(JOBS_FILE) as f:
        return json.load(f)


def save_jobs(jobs):
    with open(JOBS_FILE, "w") as f:
        json.dump(jobs, f, indent=2, ensure_ascii=False)
    print(f"  💾  Saved {len(jobs)} jobs to jobs.json")


def main(regen=False, limit=None, only_num=None):
    if not APIFY_TOKEN:
        print("ERROR: APIFY_TOKEN environment variable not set.")
        sys.exit(1)

    client = ApifyClient(APIFY_TOKEN)
    jobs   = load_jobs()

    # Build target list
    if only_num is not None:
        targets = [j for j in jobs if j.get("num") == only_num]
        if not targets:
            print(f"No job with num={only_num} found.")
            return
    else:
        targets = [j for j in jobs if not j.get("description") and j.get("apply_url")]
        if limit:
            targets = targets[:limit]

    print(f"\n🔍  Fetching job descriptions for {len(targets)} job(s)...\n")

    fetched = failed = already = 0
    for job in targets:
        num     = job.get("num", "?")
        title   = job.get("title", "")
        company = job.get("company", "")
        url     = job.get("apply_url", "")

        if job.get("description") and not only_num:
            already += 1
            continue

        print(f"  [{num:>3}]  {company} — {title}")
        print(f"          {url}")

        desc = rag_fetch_jd(client, url, title, company)

        if desc and len(desc) > 100:
            # Update the matching entry in the full jobs list
            for j in jobs:
                if j.get("num") == num:
                    j["description"] = desc
                    break
            print(f"          ✓  Got {len(desc)} chars")
            fetched += 1
        else:
            print(f"          ✗  No usable description extracted")
            failed += 1

        # Save incrementally every 5 fetches (crash-safe)
        if (fetched + failed) % 5 == 0:
            save_jobs(jobs)

        time.sleep(1)  # be kind to Apify rate limits

    # Final save
    save_jobs(jobs)
    print(f"\n✅  Fetched: {fetched}  |  Failed: {failed}  |  Already had description: {already}")

    # Optionally re-generate resumes for jobs that now have descriptions
    if regen and fetched > 0:
        print(f"\n🔄  Re-generating resumes for {fetched} job(s) with new descriptions...")
        sys.path.insert(0, os.path.dirname(__file__))
        import gen_resumes  # noqa: E402

        jobs_with_new_desc = [j for j in jobs if j.get("description")]
        gen_resumes.generate_for_jobs(jobs_with_new_desc, force_regen=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch job descriptions for tracker jobs")
    parser.add_argument("--regen",  action="store_true",
                        help="Re-generate resume PDFs after fetching descriptions")
    parser.add_argument("--limit",  type=int, default=None,
                        help="Only process this many jobs (useful for testing)")
    parser.add_argument("--num",    type=int, default=None,
                        help="Fetch description for a single job by its num field")
    args = parser.parse_args()
    main(regen=args.regen, limit=args.limit, only_num=args.num)
