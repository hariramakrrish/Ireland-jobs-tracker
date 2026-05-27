/**
 * Vercel Serverless Function — POST /api/sync-category
 *
 * Updates a job's category in the Supabase 'jobs' table.
 * Sibling of /api/sync-status; used for back-fixing miscategorised entries.
 *
 * Body: { jobId: string, category: string }
 * Env:  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */
const { createClient } = require('@supabase/supabase-js');

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { jobId, category } = req.body || {};
  if (!jobId || typeof jobId !== 'string') {
    return res.status(400).json({ error: 'jobId is required and must be a string' });
  }
  if (!category || typeof category !== 'string') {
    return res.status(400).json({ error: 'category is required and must be a string' });
  }

  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceKey  = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceKey) {
    return res.status(500).json({
      error: 'Server misconfigured: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set',
    });
  }

  const supabase = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  try {
    const { data, error } = await supabase
      .from('jobs')
      .update({ category })
      .eq('id', jobId)
      .select('id, category, updated_at');

    if (error) return res.status(500).json({ error: error.message });
    if (!data || data.length === 0) {
      return res.status(404).json({ error: `Job ${jobId} not found` });
    }
    return res.status(200).json({ success: true, job: data[0] });
  } catch (e) {
    return res.status(500).json({ error: e.message || String(e) });
  }
};
