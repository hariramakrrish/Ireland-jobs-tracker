/**
 * Vercel serverless function: POST /api/sync-status
 * Updates a job's status in jobs.json on GitHub.
 * Reads GITHUB_TOKEN from Vercel environment variable — never exposed to the browser.
 *
 * Body: { jobId: string, status: string }
 * Returns: { ok: true } or { error: string }
 */

const https = require('https');

const GH_OWNER = 'hariramakrrish';
const GH_REPO  = 'Ireland-jobs-tracker';
const GH_PATH  = 'web/data/jobs.json';

function ghRequest(method, path, token, body) {
  return new Promise((resolve, reject) => {
    const data = body ? JSON.stringify(body) : undefined;
    const req  = https.request({
      hostname: 'api.github.com',
      path,
      method,
      headers: {
        Authorization: `Bearer ${token}`,
        Accept:        'application/vnd.github.v3+json',
        'Content-Type': 'application/json',
        'User-Agent':  'ireland-jobs-tracker/1.0',
        ...(data ? { 'Content-Length': Buffer.byteLength(data) } : {}),
      },
    }, res => {
      let raw = '';
      res.on('data', c => raw += c);
      res.on('end', () => {
        try { resolve({ status: res.statusCode, body: JSON.parse(raw) }); }
        catch (e) { resolve({ status: res.statusCode, body: raw }); }
      });
    });
    req.on('error', reject);
    if (data) req.write(data);
    req.end();
  });
}

module.exports = async function handler(req, res) {
  // CORS headers so the browser fetch succeeds
  res.setHeader('Access-Control-Allow-Origin',  '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST')    return res.status(405).json({ error: 'Method not allowed' });

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    // Tell the client to fall back to its own token
    return res.status(503).json({ error: 'Server token not configured — use client PAT' });
  }

  const { jobId, status } = req.body || {};
  if (!jobId || !status) {
    return res.status(400).json({ error: 'jobId and status are required' });
  }

  try {
    // 1. Fetch current jobs.json from GitHub
    const getRes = await ghRequest('GET', `/repos/${GH_OWNER}/${GH_REPO}/contents/${GH_PATH}`, token);
    if (getRes.status !== 200) {
      return res.status(502).json({ error: `GitHub GET failed: ${getRes.status}` });
    }

    const sha  = getRes.body.sha;
    const jobs = JSON.parse(Buffer.from(getRes.body.content.replace(/\n/g, ''), 'base64').toString('utf8'));

    // 2. Update the target job
    const job = jobs.find(j => j.id === jobId);
    if (!job) return res.status(404).json({ error: `Job ${jobId} not found` });
    job.status = status;

    // 3. Push updated file back to GitHub
    const content = Buffer.from(JSON.stringify(jobs, null, 2)).toString('base64');
    const putRes  = await ghRequest('PUT', `/repos/${GH_OWNER}/${GH_REPO}/contents/${GH_PATH}`, token, {
      message: `chore: status ${jobId} → ${status}`,
      content,
      sha,
    });

    if (putRes.status !== 200 && putRes.status !== 201) {
      return res.status(502).json({ error: `GitHub PUT failed: ${putRes.status} ${putRes.body?.message || ''}` });
    }

    return res.status(200).json({ ok: true });
  } catch (e) {
    console.error('sync-status error:', e);
    return res.status(500).json({ error: e.message });
  }
};
