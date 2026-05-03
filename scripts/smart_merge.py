"""
Smart merge for GitHub Actions commit step.
Reads /tmp/pipeline_jobs.json and merges with latest remote jobs.json so
remote statuses are preserved and only new jobs are added.
"""
import json, subprocess, sys

with open("/tmp/pipeline_jobs.json") as f:
    pipeline_jobs = json.load(f)

result = subprocess.run(
    ["git", "show", "origin/main:web/data/jobs.json"],
    capture_output=True, text=True
)
if result.returncode != 0:
    print("Could not read remote jobs.json — using pipeline output as-is")
    sys.exit(0)

remote_jobs = json.loads(result.stdout)
remote_ids  = {j["id"] for j in remote_jobs}
new_jobs    = [j for j in pipeline_jobs if j["id"] not in remote_ids]
merged      = remote_jobs + new_jobs

for i, j in enumerate(merged, 1):
    j["num"] = i

with open("web/data/jobs.json", "w") as f:
    json.dump(merged, f, indent=2)

print(f"Remote: {len(remote_jobs)}, New: {len(new_jobs)}, Total: {len(merged)}")
