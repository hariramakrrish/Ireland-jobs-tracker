"""
Live tracker state from Supabase, via the dashboard's /api/jobs endpoint.

web/data/jobs.json in git is the scraper's working copy. Statuses and
categories are edited on the dashboard and only ever written to Supabase, so
the git copy goes stale (e.g. jobs marked Applied still read "Not Applied").
Anything that decides WHICH resumes to (re)build, or WHICH resume format to
use, must read status/category from here — otherwise it can overwrite the
exact PDF that was already submitted for a job, or build a Trust & Safety
role in the wrong format.
"""
import json, os, urllib.parse, urllib.request

API_URL = os.environ.get("JOBS_API_URL",
                         "https://ireland-jobs-tracker.vercel.app/api/jobs")

# Statuses where a resume has already been sent — never replace that PDF
# automatically (a manual single-job regen from the dashboard still can).
SUBMITTED = {"Applied", "Interviewing", "Selected"}


def fetch_live_jobs(required=True, timeout=60):
    """Return the dashboard's job rows (soft-deleted rows are already
    excluded by the API). If unreachable: exit when required, else None."""
    try:
        req = urllib.request.Request(API_URL, headers={"User-Agent": "ireland-jobs-tracker/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rows = json.load(r)
        if not isinstance(rows, list) or not rows:
            raise ValueError(f"unexpected /api/jobs payload ({type(rows).__name__})")
        return rows
    except Exception as e:
        if required:
            raise SystemExit(f"ERROR: could not read live statuses from {API_URL}: {e}\n"
                             "Refusing to continue on stale git data.")
        print(f"  ⚠  Could not reach {API_URL} ({e}) — falling back to git statuses")
        return None


def fetch_job(job_id, timeout=30):
    """One job's full row, including its description (the list endpoint
    omits descriptions to stay small). Returns None if not found/unreachable."""
    try:
        url = f"{API_URL}?id={urllib.parse.quote(job_id)}"
        req = urllib.request.Request(url, headers={"User-Agent": "ireland-jobs-tracker/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            rows = json.load(r)
        return rows[0] if rows else None
    except Exception as e:
        print(f"  ⚠  Could not fetch job {job_id} from {API_URL} ({e})")
        return None


def overlay_live(git_jobs, live_jobs):
    """Merge the two copies the way the dashboard sees them:
      - rows in both: git fields, with status and category taken from live
      - rows only in git: dropped (soft-deleted on the dashboard, or not
        yet synced — callers handle brand-new scrapes separately)
      - rows only in live: included (added via the dashboard's Add JD)
    """
    live = {j["id"]: j for j in live_jobs if j.get("id")}
    merged = []
    for j in git_jobs:
        lj = live.get(j.get("id"))
        if lj is None:
            continue
        row = dict(j)
        row["status"] = lj.get("status") or row.get("status")
        row["category"] = lj.get("category") or row.get("category")
        merged.append(row)
    # Dashboard-added rows have no git copy, so their JD exists only in
    # Supabase — fetch each one in full (there are only ever a handful).
    git_ids = {j.get("id") for j in git_jobs}
    for jid, lj in live.items():
        if jid not in git_ids:
            merged.append(fetch_job(jid) or dict(lj))
    return merged
