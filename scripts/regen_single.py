#!/usr/bin/env python3
"""
Regenerate ONE resume on demand. Triggered by the regen-single-resume GitHub
workflow when the user clicks the regenerate button on the dashboard.

Inputs (via env vars, since repository_dispatch payloads are read from
GITHUB_EVENT_PATH inside the workflow):
  JOB_ID      — the job id to regenerate
  JD_OVERRIDE — (optional) full JD text to use instead of the stored one.
                If provided, also persisted back to jobs.json so subsequent
                regenerations have the better description.

Exits 0 on success. Exits non-zero on any failure so the workflow surfaces it.
"""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import gen_resumes
import live_jobs

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE = os.path.join(ROOT, "web", "data", "jobs.json")
RES_DIR   = os.path.join(ROOT, "web", "resumes")

job_id      = (os.environ.get("JOB_ID") or "").strip()
jd_override = (os.environ.get("JD_OVERRIDE") or "").strip()

if not job_id:
    print("ERROR: JOB_ID env var is required")
    sys.exit(2)

if not gen_resumes._ai_available():
    print("ERROR: ANTHROPIC_API_KEY is not set — cannot regenerate via AI path")
    sys.exit(2)

with open(JOBS_FILE) as f:
    all_jobs = json.load(f)

# Jobs added via the dashboard exist only in Supabase, and categories edited
# there never reach jobs.json — so consult the live row too.
live_row = live_jobs.fetch_job(job_id)
target   = next((j for j in all_jobs if j.get("id") == job_id), None)
in_git   = target is not None
if target is None:
    if live_row is None:
        print(f"ERROR: job id {job_id!r} not found in jobs.json or on the dashboard")
        sys.exit(2)
    target = dict(live_row)
    print("  (dashboard-added job — using its Supabase row)")
elif live_row and live_row.get("category"):
    target["category"] = live_row["category"]

print(f"Regenerating resume for: {target.get('company')} — {target.get('title')}")
print(f"  Stored JD length      : {len(target.get('description') or '')}")
print(f"  Override JD provided  : {'yes' if jd_override else 'no'} ({len(jd_override)} chars)")

# If user provided a new JD, persist it. The AI generator reads from job['description'].
if jd_override:
    target["description"] = jd_override
    if in_git:
        with open(JOBS_FILE, "w") as f:
            json.dump(all_jobs, f, indent=2, ensure_ascii=True)
            f.write("\n")
        print("  Updated jobs.json with new description.")

# Force regenerate this single job (deletes existing PDF first).
if target.get("resume"):
    pdf = os.path.join(RES_DIR, target["resume"])
    if os.path.exists(pdf):
        os.remove(pdf)
        print("  Deleted old PDF.")

gen_resumes.generate_for_jobs([target], force_regen=True)
print("Done.")
