# Archived jobs

Jobs taken off the dashboard to keep it fast. Their rows stay in Supabase with
status `Archived` (hidden by `/api/jobs`, so the INSERT-only daily sync never
re-adds them), and each archive file here keeps the full rows, including the
original status and the job description.

| File | What |
|---|---|
| `jobs-archived-2026-11-06-added-before-2026-08-01.json` | 1,135 jobs added before 1 Aug 2026 that were Not Applied / No Longer Available (full rows + JD) |
| `jobs-archived-2026-11-06-added-2026-08-01-to-2026-09-01.json` | 308 jobs added in August 2026, same rule |
| `jobs-archived-2026-11-07-senior-or-off-target.json` | 1,979 Not Applied / No Longer Available jobs that fail the scraper filters added on 2026-11-07: non-tech roles such as manufacturing, supply chain, finance and sales (1,640), JD asks for more than 3.5 years (233), senior title (67), gig-work companies (39). Each row has an `archive_reason`. Jobs added by hand (source `Manual`) were kept. |
| `*.csv` | Same jobs without descriptions, for opening in Excel |

Applied, Interviewing, Rejected and Selected jobs were not archived.

**Restore:** set each row's `status` back to the value in the JSON. Note that
`/api/sync-status` refuses more than 5 "Not Applied" writes per minute (a
guard against mass overwrites), so restore in bulk with the Supabase service
key (e.g. from a GitHub Actions job) rather than through that endpoint.
