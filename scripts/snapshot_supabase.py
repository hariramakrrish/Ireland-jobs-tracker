#!/usr/bin/env python3
"""
Daily snapshot of Supabase 'jobs' table → committed to git as a dated JSON file.

Purpose: recovery backstop. Supabase free tier has no point-in-time recovery,
so if anything ever nukes status/category fields (as happened on 2026-05-31
when a buggy UPSERT in the daily pipeline wiped 41 Applied statuses), we
need a way to restore from a known-good earlier state.

Strategy: every day at 06:00 UTC (before the 07:00 pipeline runs), pull
/api/jobs and write the full table to web/data/jobs-snapshot-YYYY-MM-DD.json.
Commit and push. Git history preserves every snapshot — full table history
is ~500 KB per day compressed, fine for git indefinitely.

To restore from a snapshot: cherry-pick the file, run a small replay script
that POSTs each row's status/category back via /api/sync-status.
"""
import os, sys, json, urllib.request
from datetime import datetime, timezone

ROOT      = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP_DIR  = os.path.join(ROOT, "web", "data")
API_URL   = os.environ.get(
    "TRACKER_API_URL",
    "https://ireland-jobs-tracker.vercel.app/api/jobs",
)

date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
out_path = os.path.join(SNAP_DIR, f"jobs-snapshot-{date_str}.json")

print(f"Fetching {API_URL} ...")
with urllib.request.urlopen(API_URL, timeout=30) as r:
    jobs = json.load(r)

# Sort by id so daily diffs are minimal and readable.
jobs.sort(key=lambda j: j.get("id", ""))

with open(out_path, "w") as f:
    json.dump(jobs, f, indent=2, ensure_ascii=False)
    f.write("\n")

size_kb = os.path.getsize(out_path) / 1024
from collections import Counter
status_counts = Counter(j.get("status", "(none)") for j in jobs)
print(f"Wrote {out_path}")
print(f"  rows  : {len(jobs)}")
print(f"  size  : {size_kb:.1f} KB")
print(f"  status: " + ", ".join(f"{s}={n}" for s, n in status_counts.most_common()))
