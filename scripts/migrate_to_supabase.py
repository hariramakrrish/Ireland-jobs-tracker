#!/usr/bin/env python3
"""
One-time bulk import: load every row from web/data/jobs.json into the
Supabase 'jobs' table via UPSERT-on-id. Safe to re-run — idempotent because
of the primary-key conflict-resolution.

Required env vars:
  SUPABASE_URL                — https://<project>.supabase.co
  SUPABASE_SERVICE_ROLE_KEY   — service role key (NOT the anon key)

Run via the regen-targeted-style workflow `.github/workflows/migrate-to-supabase.yml`
or locally with the env vars set.
"""
import os, sys, json
from supabase import create_client

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
JOBS_FILE = os.path.join(ROOT, "web", "data", "jobs.json")

SUPABASE_URL              = os.environ.get("SUPABASE_URL", "").strip()
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()

if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must both be set")
    sys.exit(2)

if not os.path.exists(JOBS_FILE):
    print(f"ERROR: jobs.json not found at {JOBS_FILE}")
    sys.exit(2)

with open(JOBS_FILE) as f:
    jobs = json.load(f)

print(f"Loaded {len(jobs)} jobs from {JOBS_FILE}")

# Only forward the columns that exist in the Supabase schema. Anything extra
# in jobs.json is dropped silently — we'll add columns later if you decide
# you want them in the DB too.
ALLOWED_COLUMNS = {
    "id", "num", "category", "title", "company", "location", "source",
    "posted", "apply_url", "resume", "description", "status",
    "salary", "notes", "tailored", "added",
}

rows = []
skipped = 0
for j in jobs:
    if not j.get("id") or not j.get("title") or not j.get("company"):
        skipped += 1
        continue
    row = {k: v for k, v in j.items() if k in ALLOWED_COLUMNS}
    if "tailored" not in row:
        row["tailored"] = False
    if "status" not in row:
        row["status"] = "Not Applied"
    rows.append(row)

print(f"Prepared {len(rows)} rows for upsert  (skipped {skipped} malformed)")

client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)

# Upsert in batches of 50 to stay under PostgREST's ~1MB request limit.
BATCH = 50
inserted = 0
for i in range(0, len(rows), BATCH):
    chunk = rows[i:i + BATCH]
    client.table("jobs").upsert(chunk, on_conflict="id").execute()
    inserted += len(chunk)
    print(f"  batch {i // BATCH + 1}: upserted {len(chunk)} rows  (total {inserted}/{len(rows)})")

print(f"\nMigration complete: {inserted} rows upserted into jobs")
