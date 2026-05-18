/**
 * Vercel Serverless Function — POST /api/sync-status
 *
 * Atomically updates a job's status in the Supabase 'jobs' table.
 * Replaces the previous GitHub Contents-API patcher which hit 409 conflicts
 * under concurrent edits across devices.
 *
 * Body: { jobId: string, status: string }
 * Env:  SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */
const { createClient } = require('@supabase/supabase-js');

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { jobId, status } = req.body || {};
  if (!jobId || typeof jobId !== 'string') {
    return res.status(400).json({ error: 'jobId is required and must be a string' });
  }
  if (!status || typeof status !== 'string') {
    return res.status(400).json({ error: 'status is required and must be a string' });
  }

  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceKey  = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceKey) {
    console.error('Missing Supabase env vars');
    return res.status(500).json({
      error: 'Server misconfigured: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set in Vercel env vars',
    });
  }

  const supabase = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  try {
    const { data, error } = await supabase
      .from('jobs')
      .update({ status })
      .eq('id', jobId)
      .select('id, status, updated_at');

    if (error) {
      console.error('Supabase update error:', error);
      return res.status(500).json({ error: error.message });
    }
    if (!data || data.length === 0) {
      return res.status(404).json({ error: `Job ${jobId} not found` });
    }

    return res.status(200).json({ success: true, job: data[0] });
  } catch (e) {
    console.error('Unexpected error in sync-status:', e);
    return res.status(500).json({ error: e.message || String(e) });
  }
};
