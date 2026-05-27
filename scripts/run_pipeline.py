#!/usr/bin/env python3
"""
Orchestrator: search jobs → generate resumes → rebuild dashboard data.
Run daily via GitHub Actions at 07:00 UTC.

Resume generation strategy:
  - New jobs found today → always generate
  - Existing "Not Applied" jobs with missing PDFs → generate (handles first-run
    after AI upgrade, and any PDFs that were deleted / never created)
  - Existing jobs with PDFs already present → skip (no re-gen needed daily)
"""
import sys, os, re, json
sys.path.insert(0, os.path.dirname(__file__))

import search_jobs
import gen_resumes

SENIOR = re.compile(
    r"\b(senior|sr\.?|lead|principal|staff|head\s+of|director|vp\b|"
    r"vice\s+president|architect|manager|avp)\b",
    re.IGNORECASE,
)

def kill_zombie_apify_runs():
    """
    Abort any RUNNING actor runs owned by this Apify token before starting fresh.

    Why: the free tier has an 8 GB concurrent-actor-memory cap. If a previous
    pipeline run crashed mid-execution (Python exception after .call() but
    before completion), the actor on Apify's side keeps running and holds
    its memory allocation forever. After 2-3 crashes the cap is fully
    saturated and the next run can't start any new actors.

    This cleanup runs first, every time, so we always start with a clean
    memory budget.
    """
    token = os.environ.get("APIFY_TOKEN", "")
    if not token:
        print("  ⚠  APIFY_TOKEN not set — skipping zombie cleanup")
        return
    try:
        from apify_client import ApifyClient
        client = ApifyClient(token)
        runs = client.runs().list(status="RUNNING", limit=100).items or []
        if not runs:
            print("  ✓  no zombie actor runs found")
            return
        print(f"  Found {len(runs)} RUNNING actor runs — aborting…")
        for r in runs:
            rid = r.get("id") if isinstance(r, dict) else getattr(r, "id", None)
            actor_name = (r.get("actId") if isinstance(r, dict) else getattr(r, "act_id", None)) or "?"
            if not rid:
                continue
            try:
                client.run(rid).abort()
                print(f"    aborted {rid}  ({actor_name})")
            except Exception as e:
                print(f"    ⚠  failed to abort {rid}: {e}")
    except Exception as e:
        print(f"  ⚠  zombie-cleanup failed: {e}")


def main():
    print("=" * 60)
    print("  HARI JOB PIPELINE — DAILY RUN")
    print("=" * 60)

    # 0. Cleanup — abort any zombie actors holding Apify memory quota
    print("\n[0/3]  Aborting any zombie Apify actor runs...")
    kill_zombie_apify_runs()

    # 1. Search for new jobs
    print("\n[1/3]  Searching for new jobs...")
    new_jobs = search_jobs.main()

    # 2. Find existing Not Applied jobs whose PDF is missing (e.g. after AI upgrade)
    jobs_file  = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                              "web", "data", "jobs.json")
    resume_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                              "web", "resumes")

    with open(jobs_file) as f:
        all_jobs = json.load(f)

    missing_pdf_jobs = [
        j for j in all_jobs
        if j.get("status") == "Not Applied"
        and not SENIOR.search(j.get("title", ""))
        and (
            not j.get("resume")  # no resume filename assigned at all
            or not os.path.exists(os.path.join(resume_dir, j["resume"]))
        )
    ]

    # 3. Combine: new jobs + existing jobs with missing PDFs (deduplicate by id)
    seen_ids   = {j["id"] for j in new_jobs}
    extra_jobs = [j for j in missing_pdf_jobs if j["id"] not in seen_ids]
    all_to_gen = new_jobs + extra_jobs

    print(f"\n[2/3]  Generating resumes:")
    print(f"       New jobs today:            {len(new_jobs)}")
    print(f"       Existing jobs missing PDF: {len(extra_jobs)}")
    print(f"       Total to generate:         {len(all_to_gen)}")

    if all_to_gen:
        gen_resumes.generate_for_jobs(all_to_gen)
    else:
        print("  Nothing to generate.")

    print(f"\n[3/3]  Pipeline complete.")
    print("=" * 60)

if __name__ == "__main__":
    main()
