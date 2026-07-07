/**
 * POST /api/add-job
 *
 * Adds a manual job entry to Supabase and triggers a resume regen for it.
 * Used by the "✨ Add JD" button on the dashboard when the user has a JD
 * the scrapers haven't found.
 *
 * Body: { company, title, jd, category?, apply_url?, location? }
 *
 * Behaviour:
 *   1. Generate a stable id = md5(slug(company)_slug(title))[:10]
 *      (same algorithm as scripts/search_jobs.py so duplicate adds collide).
 *   2. INSERT into Supabase (ignored if id already exists).
 *   3. Fire repository_dispatch event 'regen-resume' so the existing
 *      single-resume workflow tailors and pushes the PDF.
 *
 * Returns: { success, jobId, alreadyExisted }
 *
 * Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, GITHUB_TOKEN
 */
const { createClient } = require('@supabase/supabase-js');
const crypto           = require('crypto');

function slug(text) {
  return (text || '')
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, '')
    .trim()
    .replace(/\s+/g, '_')
    .slice(0, 40);
}
function jobId(company, title) {
  return crypto.createHash('md5')
    .update(`${slug(company)}_${slug(title)}`)
    .digest('hex')
    .slice(0, 10);
}

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { company, title, jd, category, apply_url, location } = req.body || {};
  if (!company || !title) {
    return res.status(400).json({ error: 'company and title are required' });
  }

  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceKey  = process.env.SUPABASE_SERVICE_ROLE_KEY;
  const ghToken     = process.env.GITHUB_TOKEN;
  if (!supabaseUrl || !serviceKey) {
    return res.status(500).json({ error: 'Server misconfigured: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set' });
  }
  // NOTE: GITHUB_TOKEN is optional. If it's missing/expired the job still
  // gets saved to Supabase; only the automatic resume-regen is skipped.

  const supabase = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  const id  = jobId(company, title);
  const today = new Date().toISOString().slice(0, 10);

  // Check if row already exists
  let alreadyExisted = false;
  try {
    const { data: existing } = await supabase
      .from('jobs').select('id').eq('id', id).maybeSingle();
    if (existing) alreadyExisted = true;
  } catch (e) { /* fall through and try insert */ }

  if (!alreadyExisted) {
    // Compute next num
    let next_num = 1;
    try {
      const { data: maxRow } = await supabase
        .from('jobs').select('num').order('num', { ascending: false }).limit(1).maybeSingle();
      if (maxRow && typeof maxRow.num === 'number') next_num = maxRow.num + 1;
    } catch (e) {}

    const row = {
      id,
      num:        next_num,
      category:   category || 'Full Stack',
      title,
      company,
      location:   location || 'Ireland',
      source:     'Manual',
      posted:     today,
      apply_url:  apply_url || '',
      resume:     `hari_${slug(company)}_${slug(title)}.pdf`,
      description: jd || '',
      status:     'Not Applied',
      tailored:   false,
      added:      today,
    };
    const { error: insErr } = await supabase.from('jobs').insert(row);
    if (insErr) {
      console.error('Insert error:', insErr);
      return res.status(500).json({ error: insErr.message });
    }
  }

  // Best-effort: trigger the single-resume regen workflow with this JD.
  // IMPORTANT: the job row is ALREADY saved in Supabase above, so even if
  // the GitHub token is expired/invalid, the job still appears in the
  // tracker. We never fail the whole request just because the resume
  // couldn't be auto-queued — that was the old bug where a stale
  // GITHUB_TOKEN made "Add JD" return 502 and appear completely broken.
  let resumeQueued = false;
  let resumeError  = null;
  if (ghToken) {
    try {
      const ghRes = await fetch('https://api.github.com/repos/hariramakrrish/Ireland-jobs-tracker/dispatches', {
        method: 'POST',
        headers: {
          'Accept':        'application/vnd.github+json',
          'Authorization': `Bearer ${ghToken}`,
          'X-GitHub-Api-Version': '2022-11-28',
          'Content-Type':  'application/json',
        },
        body: JSON.stringify({
          event_type: 'regen-resume',
          client_payload: { jobId: id, jd: jd || '' },
        }),
      });
      if (ghRes.ok) {
        resumeQueued = true;
      } else {
        resumeError = `GitHub dispatch HTTP ${ghRes.status}`;
        console.error('GH dispatch failed (job still saved):', ghRes.status, await ghRes.text());
      }
    } catch (e) {
      resumeError = 'GitHub dispatch network error: ' + e.message;
      console.error(resumeError);
    }
  } else {
    resumeError = 'GITHUB_TOKEN not set — resume not auto-queued';
  }

  return res.status(200).json({ success: true, jobId: id, alreadyExisted, resumeQueued, resumeError });
};
