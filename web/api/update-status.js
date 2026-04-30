/**
 * Vercel Serverless Function — PATCH job status
 * POST /api/update-status  { id: string, status: string }
 * Updates web/data/jobs.json in GitHub so all devices stay in sync.
 */
module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { id, status } = req.body || {};
  if (!id || !status) return res.status(400).json({ error: 'Missing id or status' });

  const token = process.env.GITHUB_TOKEN;
  if (!token) {
    console.error('GITHUB_TOKEN env var is not set in Vercel project settings');
    return res.status(500).json({ error: 'GITHUB_TOKEN not configured — add it in Vercel → Settings → Environment Variables' });
  }

  const owner = 'hariramakrrish';
  const repo  = 'Ireland-jobs-tracker';
  const path  = 'web/data/jobs.json';
  const base  = 'https://api.github.com';
  const hdrs  = {
    Authorization: `Bearer ${token}`,
    Accept: 'application/vnd.github.v3+json',
    'Content-Type': 'application/json',
    'User-Agent': 'ireland-job-tracker',
  };

  try {
    // 1. Read current file + SHA
    const getRes = await fetch(`${base}/repos/${owner}/${repo}/contents/${path}`, { headers: hdrs });
    if (!getRes.ok) throw new Error(`GitHub GET ${getRes.status}`);
    const fileData = await getRes.json();
    const jobs = JSON.parse(Buffer.from(fileData.content, 'base64').toString('utf-8'));

    // 2. Update the matching job
    const job = jobs.find(j => j.id === id);
    if (!job) return res.status(404).json({ error: 'Job not found' });
    job.status = status;

    // 3. Commit back
    const putRes = await fetch(`${base}/repos/${owner}/${repo}/contents/${path}`, {
      method: 'PUT',
      headers: hdrs,
      body: JSON.stringify({
        message: `chore: status update ${id} → ${status}`,
        content: Buffer.from(JSON.stringify(jobs, null, 2)).toString('base64'),
        sha: fileData.sha,
      }),
    });
    if (!putRes.ok) {
      const err = await putRes.json();
      throw new Error(`GitHub PUT ${putRes.status}: ${JSON.stringify(err.message)}`);
    }

    return res.status(200).json({ success: true });
  } catch (e) {
    console.error(e);
    return res.status(500).json({ error: e.message });
  }
};
