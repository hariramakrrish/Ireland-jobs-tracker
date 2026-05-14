#!/usr/bin/env python3
"""
One-time script: force-regenerate AI-tailored resumes for all "Not Applied" jobs.
Run via GitHub Actions (regen-resumes.yml) so ANTHROPIC_API_KEY is available.

Skips: Applied, Rejected, Interview in Progress, No Longer Available.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import gen_resumes

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE = os.path.join(ROOT, "web", "data", "jobs.json")
RES_DIR   = os.path.join(ROOT, "web", "resumes")

with open(JOBS_FILE) as f:
    all_jobs = json.load(f)

targets = [j for j in all_jobs if j.get("status") == "Not Applied"]

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
