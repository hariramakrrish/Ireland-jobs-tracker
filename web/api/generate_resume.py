"""
POST /api/generate_resume   { jobId, jd? }

Generates one job's resume right here (~10 s) and stores the PDF in the private
Supabase Storage bucket "resumes", served by /api/resume-store. No GitHub token,
no Actions run and no redeploy are involved, so ✨ Add JD and ✱ work the moment
a job is saved.

Uses the pipeline's own generator: scripts/gen_resumes.py is fetched from the
repo's main branch on cold start, so prompts, layouts, the Trust & Safety
format and the client-name guard never drift from the daily pipeline.

Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GEMINI_API_KEY. Without the
Gemini key the generator uses its static template and the response says
tailored=false.
"""
import contextlib, importlib.util, io, json, os, time
import urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler

GENERATOR_URL = ("https://raw.githubusercontent.com/hariramakrrish/"
                 "Ireland-jobs-tracker/main/scripts/gen_resumes.py")
# gen_resumes derives web/resumes and web/data from its own location, so it is
# saved under a writable root that mirrors the repo layout.
WORK_ROOT = "/tmp/resume-gen"
BUCKET = "resumes"

_gen = None
_bucket_ready = False


def _supabase(method, path, body=None, headers=None):
    key = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
    h = {"apikey": key, "Authorization": f"Bearer {key}"}
    if isinstance(body, (dict, list)):
        body = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    h.update(headers or {})
    req = urllib.request.Request(os.environ["SUPABASE_URL"].rstrip("/") + path,
                                 data=body, method=method, headers=h)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def _ensure_bucket():
    global _bucket_ready
    if _bucket_ready:
        return
    try:
        _supabase("GET", f"/storage/v1/bucket/{BUCKET}")
    except urllib.error.HTTPError:
        try:
            _supabase("POST", "/storage/v1/bucket",
                      {"id": BUCKET, "name": BUCKET, "public": False})
        except urllib.error.HTTPError as e:
            if e.code != 409:          # already created by a concurrent call
                raise
    _bucket_ready = True


def _load_generator():
    global _gen
    if _gen is None:
        scripts = os.path.join(WORK_ROOT, "scripts")
        data = os.path.join(WORK_ROOT, "web", "data")
        os.makedirs(scripts, exist_ok=True)
        os.makedirs(data, exist_ok=True)
        jobs_file = os.path.join(data, "jobs.json")
        if not os.path.exists(jobs_file):       # generate_for_jobs() bails without one
            with open(jobs_file, "w") as f:
                f.write("[]")
        path = os.path.join(scripts, "gen_resumes.py")
        with urllib.request.urlopen(GENERATOR_URL, timeout=20) as r:
            src = r.read()
        with open(path, "wb") as f:
            f.write(src)
        spec = importlib.util.spec_from_file_location("gen_resumes", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _gen = mod
    return _gen


def generate(job_id, jd=""):
    t0 = time.time()
    q = urllib.parse.quote(job_id)
    rows = json.loads(_supabase(
        "GET", f"/rest/v1/jobs?id=eq.{q}&select=id,company,title,category,description,resume"))
    if not rows:
        raise LookupError(f"job {job_id} not found")
    job = rows[0]
    if jd:
        # Keep the pasted JD so later regenerations use it too.
        job["description"] = jd
        _supabase("PATCH", f"/rest/v1/jobs?id=eq.{q}", {"description": jd},
                  {"Prefer": "return=minimal"})

    gen = _load_generator()
    gen.GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
    gen._DAILY_QUOTA_HIT = False        # per-run flag in the pipeline; per-request here
    if not job.get("resume"):
        job["resume"] = f"hari_{gen.slug(job.get('company', ''))}_{gen.slug(job.get('title', ''))}.pdf"

    log = io.StringIO()
    with contextlib.redirect_stdout(log):
        gen.generate_for_jobs([job], force_regen=True)
    out = log.getvalue()
    pdf_path = os.path.join(gen.RESUME_DIR, job["resume"])
    if not os.path.exists(pdf_path):
        raise RuntimeError("generator produced no PDF: " + out[-400:])
    with open(pdf_path, "rb") as f:
        pdf = f.read()
    os.remove(pdf_path)

    _ensure_bucket()
    _supabase("POST", f"/storage/v1/object/{BUCKET}/{urllib.parse.quote(job['resume'])}", pdf,
              {"Content-Type": "application/pdf", "x-upsert": "true", "cache-control": "no-cache"})
    return {
        "success": True,
        "jobId": job_id,
        "file": job["resume"],
        "tailored": "[AI" in out,      # generate_for_jobs logs [AI] / [AI T&S] on success
        "seconds": round(time.time() - t0, 1),
        "log": out[-600:],
    }


class handler(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self._send(200, {})

    def do_POST(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
            body = json.loads(self.rfile.read(n) or b"{}")
            job_id = str(body.get("jobId") or "").strip()
            if not job_id:
                return self._send(400, {"error": "jobId is required"})
            jd = body.get("jd") if isinstance(body.get("jd"), str) else ""
            self._send(200, generate(job_id, jd.strip()))
        except LookupError as e:
            self._send(404, {"error": str(e)})
        except Exception as e:
            self._send(500, {"error": f"{type(e).__name__}: {e}"})
