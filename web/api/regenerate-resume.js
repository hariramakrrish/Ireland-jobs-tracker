/**
 * Vercel Serverless Function — trigger an on-demand resume regen.
 * POST /api/regenerate-resume  { jobId: string, jd: string }
 *
 * Fires a GitHub `repository_dispatch` event of type "regen-resume".
 * The .github/workflows/regen-single-resume.yml workflow listens for that
 * event, runs scripts/regen_single.py with the JD, and commits the new PDF.
 *
 * Returns 202 (Accepted) once dispatch is queued — the regen itself takes
 * about 30-60s in CI plus Vercel rebuild time.
 */
module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { jobId, jd } = req.body || {};
  if (!jobId || typeof jobId !== 'string') {
    return res.status(400).json({ error: 'jobId is required' });
  }
  // jd is optional — if not provided, regen will use the stored description.
  const jdText = typeof jd === 'string' ? jd.trim() : '';
  // GitHub client_payload total is capped at 64KB. Be conservative.
  if (jdText.length > 50000) {
    return res.status(400).json({ error: 'JD too long (max 50000 chars)' });
  }

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    return res.status(500).json({
      error: 'GITHUB_TOKEN not configured — add it in Vercel → Settings → Environment Variables (needs repo scope)',
    });
  }

  const owner = 'hariramakrrish';
  const repo  = 'Ireland-jobs-tracker';

  try {
    const ghRes = await fetch(`https://api.github.com/repos/${owner}/${repo}/dispatches`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
        'User-Agent': 'ireland-job-tracker',
      },
      body: JSON.stringify({
        event_type: 'regen-resume',
        client_payload: { jobId, jd: jdText },
      }),
    });
    if (!ghRes.ok) {
      const errBody = await ghRes.text();
      console.error('GitHub dispatch failed:', ghRes.status, errBody);
      return res.status(502).json({ error: `GitHub dispatch failed: ${ghRes.status}` });
    }
    return res.status(202).json({
      success: true,
      message: 'Regeneration started. Refresh in 1-2 minutes to download the new PDF.',
    });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ error: e.message });
  }
};
