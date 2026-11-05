/**
 * Resumes generated on demand by /api/generate_resume live in the private
 * Supabase Storage bucket "resumes".
 *
 * GET /api/resume-store             → { files: [...] }  names of stored PDFs
 * GET /api/resume-store?name=<pdf>  → that PDF
 *
 * vercel.json rewrites /resumes/<pdf> here when no static PDF exists, so
 * on-demand resumes keep the same URLs as the pipeline's.
 *
 * Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */
const BUCKET = 'resumes';

module.exports = async function handler(req, res) {
  const base = process.env.SUPABASE_URL;
  const key  = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!base || !key) return res.status(500).json({ error: 'Server misconfigured: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set' });
  const auth = { apikey: key, Authorization: `Bearer ${key}` };
  res.setHeader('Cache-Control', 'no-store');

  const name = String(req.query.name || '');
  if (!name) {
    const r = await fetch(`${base}/storage/v1/object/list/${BUCKET}`, {
      method: 'POST',
      headers: { ...auth, 'Content-Type': 'application/json' },
      body: JSON.stringify({ prefix: '', limit: 1000, offset: 0, sortBy: { column: 'name', order: 'asc' } }),
    });
    // The bucket is created on the first generation; until then there's nothing.
    if (r.status === 400 || r.status === 404) return res.status(200).json({ files: [] });
    if (!r.ok) return res.status(502).json({ error: `Storage list failed: HTTP ${r.status}` });
    const items = await r.json();
    return res.status(200).json({ files: items.map(i => i.name).filter(n => n.endsWith('.pdf')) });
  }

  if (!/^[\w.-]+\.pdf$/.test(name)) return res.status(400).send('Bad file name');
  const r = await fetch(`${base}/storage/v1/object/${BUCKET}/${encodeURIComponent(name)}`, { headers: auth });
  if (!r.ok) return res.status(404).send('PDF not found');
  res.setHeader('Content-Type', 'application/pdf');
  res.setHeader('Content-Disposition', `inline; filename="${name}"`);
  return res.status(200).send(Buffer.from(await r.arrayBuffer()));
};
