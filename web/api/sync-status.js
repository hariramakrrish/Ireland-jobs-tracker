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

  // ── Mass-overwrite guard ──────────────────────────────────────────────
  // On 2026-05-31 a buggy migrate script blindly overwrote 41 Applied
  // statuses to 'Not Applied'. This guard catches the same failure mode
  // if it ever recurs via this endpoint: if more than 5 rows have been
  // set to 'Not Applied' in the last 60 seconds, refuse further such
  // writes until things settle. Manual user clicks rarely reset to
  // 'Not Applied' so this almost never triggers on legitimate use.
  if (status === 'Not Applied') {
    try {
      const sixtySecondsAgo = new Date(Date.now() - 60 * 1000).toISOString();
      const { count, error: countErr } = await supabase
        .from('jobs')
        .select('id', { count: 'exact', head: true })
        .eq('status', 'Not Applied')
        .gte('updated_at', sixtySecondsAgo);
      if (!countErr && typeof count === 'number' && count >= 5) {
        console.warn(`Mass-NA-overwrite guard tripped: ${count} jobs set to Not Applied in last 60s; refusing ${jobId}`);
        return res.status(429).json({
          error: 'Mass-overwrite guard: more than 5 rows set to Not Applied in the last 60 seconds. Refusing to prevent accidental data loss. Wait a minute and retry, or inspect what is hitting this endpoint.',
          recentNotAppliedCount: count,
        });
      }
    } catch (e) {
      // Guard check failure must NOT block legitimate writes — log and proceed.
      console.warn('Mass-NA-overwrite guard check failed; allowing write:', e.message);
    }
  }

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
