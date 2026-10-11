#!/usr/bin/env python3
"""
One-time script: force-regenerate AI-tailored resumes for all "Not Applied" jobs.
Run via GitHub Actions (regen-resumes.yml) so ANTHROPIC_API_KEY is available.

Skips: Applied, Rejected, Interview in Progress, No Longer Available.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import gen_resumes
import live_jobs

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE = os.path.join(ROOT, "web", "data", "jobs.json")
RES_DIR   = os.path.join(ROOT, "web", "resumes")

with open(JOBS_FILE) as f:
    all_jobs = json.load(f)

# This script DELETES PDFs, so it must use the dashboard's live statuses —
# git's copy would sweep in jobs already applied to (replacing the submitted
# resume) and rows cleared from the dashboard. No fallback to stale data.
pool    = live_jobs.overlay_live(all_jobs, live_jobs.fetch_live_jobs(required=True))
targets = [j for j in pool if j.get("status") == "Not Applied"]

print(f"Found {len(targets)} 'Not Applied' jobs to regenerate.")
print(f"AI available: {gen_resumes._ai_available()}")
print("=" * 60)

# Delete existing PDFs so force_regen kicks in
deleted = 0
for job in targets:
    if job.get("resume"):
        path = os.path.join(RES_DIR, job["resume"])
        if os.path.exists(path):
            os.remove(path)
            deleted += 1

print(f"Deleted {deleted} existing static PDFs — regenerating with AI...")
print("=" * 60)

gen_resumes.generate_for_jobs(targets, force_regen=False)
