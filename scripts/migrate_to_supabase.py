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

# ──────────────────────────────────────────────────────────────────────────
# DAILY-SAFE MODE: INSERT-only-on-new.
# Originally this script UPSERTed every row. That was safe for the one-time
# bootstrap (the script's first purpose), but the daily pipeline now calls
# this script too. UPSERT was OVERWRITING user-set status/category/notes on
# every daily run with jobs.json's stale values from git — silently wiping
# Applied/Rejected/Interviewing markers the user set on the dashboard.
# (Confirmed 2026-05-31: 41 Applied rows reset to Not Applied.)
#
# Fix: fetch existing IDs, INSERT only the NEW rows. Existing rows are
# never touched — their status/category stay whatever the user set.
# ──────────────────────────────────────────────────────────────────────────
print("Fetching existing job IDs from Supabase...")
existing_ids = set()
page = 0
PAGE_SIZE = 1000
while True:
    res = client.table("jobs").select("id").range(page * PAGE_SIZE,
                                                  (page + 1) * PAGE_SIZE - 1).execute()
    if not res.data:
        break
    existing_ids.update(r["id"] for r in res.data)
    if len(res.data) < PAGE_SIZE:
        break
    page += 1
print(f"  {len(existing_ids)} jobs already in Supabase")

new_rows = [r for r in rows if r["id"] not in existing_ids]
skipped_existing = len(rows) - len(new_rows)
print(f"  {len(new_rows)} new rows to insert  (skipping {skipped_existing} existing — their status/category preserved)")

if not new_rows:
    print("\nNothing new to insert. Done.")
    sys.exit(0)

BATCH = 50
inserted = 0
for i in range(0, len(new_rows), BATCH):
    chunk = new_rows[i:i + BATCH]
    client.table("jobs").insert(chunk).execute()
    inserted += len(chunk)
    print(f"  batch {i // BATCH + 1}: inserted {len(chunk)} new rows  (total {inserted}/{len(new_rows)})")

print(f"\nDaily sync complete: {inserted} new rows inserted (existing rows untouched)")
