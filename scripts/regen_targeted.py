#!/usr/bin/env python3
"""
Targeted regen — only regenerates resumes for a fixed list of job IDs.

Use case: the previous mass regen ran out of Anthropic credits partway through,
leaving 138 jobs with static-template fallback resumes instead of AI-tailored
ones. We re-run JUST those.

Reads the ID list from JOB_IDS_FILE env var (path to a JSON array of id strings)
or from scripts/regen_targets.json by default.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import gen_resumes
import live_jobs

ROOT       = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE  = os.path.join(ROOT, "web", "data", "jobs.json")
RES_DIR    = os.path.join(ROOT, "web", "resumes")
IDS_FILE   = os.environ.get("JOB_IDS_FILE") or os.path.join(ROOT, "scripts", "regen_targets.json")

if not os.path.exists(IDS_FILE):
    print(f"ERROR: ID list not found at {IDS_FILE}")
    sys.exit(2)
if not gen_resumes._ai_available():
    print("ERROR: ANTHROPIC_API_KEY not set — cannot regen via AI path")
    sys.exit(2)

with open(IDS_FILE) as f:
    target_ids = set(json.load(f))

with open(JOBS_FILE) as f:
    all_jobs = json.load(f)

# Live status/category (git's copy is stale) and dashboard-added rows.
pool    = live_jobs.overlay_live(all_jobs, live_jobs.fetch_live_jobs(required=True))
found   = [j for j in pool if j.get("id") in target_ids]
skipped = [j for j in found if j.get("status") in live_jobs.SUBMITTED]
targets = [j for j in found if j.get("status") not in live_jobs.SUBMITTED]
print(f"Found {len(found)} of {len(target_ids)} requested IDs on the dashboard")
for j in skipped:
    print(f"  skip (resume already submitted, status {j['status']}): {j.get('company')} — {j.get('title')}")

# Force-regen: delete each target's existing PDF so AI path always runs
deleted = 0
for j in targets:
    if j.get("resume"):
        path = os.path.join(RES_DIR, j["resume"])
        if os.path.exists(path):
            os.remove(path); deleted += 1
print(f"Deleted {deleted} existing PDFs — regenerating with AI")
print("=" * 60)

gen_resumes.generate_for_jobs(targets, force_regen=False)
