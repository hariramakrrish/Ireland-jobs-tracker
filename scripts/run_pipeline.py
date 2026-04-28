#!/usr/bin/env python3
"""
Orchestrator: search jobs → generate resumes → rebuild dashboard data.
Run daily via GitHub Actions at 07:00 UTC.
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

import search_jobs
import gen_resumes

def main():
    print("=" * 60)
    print("  HARI JOB PIPELINE — DAILY RUN")
    print("=" * 60)

    # 1. Search for new jobs
    print("\n[1/2]  Searching for new jobs...")
    new_jobs = search_jobs.main()

    # 2. Generate resumes for new jobs only
    print(f"\n[2/2]  Generating resumes for {len(new_jobs)} new job(s)...")
    if new_jobs:
        gen_resumes.generate_for_jobs(new_jobs)
    else:
        print("  No new jobs found today.")

    print("\n" + "=" * 60)
    print("  Pipeline complete.")
    print("=" * 60)

if __name__ == "__main__":
    main()
