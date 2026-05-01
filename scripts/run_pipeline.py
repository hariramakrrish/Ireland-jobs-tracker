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

def main():
    print("=" * 60)
    print("  HARI JOB PIPELINE — DAILY RUN")
    print("=" * 60)

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
        and not os.path.exists(os.path.join(resume_dir, j.get("resume", "")))
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
