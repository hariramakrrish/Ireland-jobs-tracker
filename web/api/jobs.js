/**
 * Vercel Serverless Function — GET /api/jobs
 *
 * Returns the canonical job list straight from Supabase.
 * Replaces the dashboard's previous fetch('data/jobs.json') so status
 * changes show up the moment they're written, without a sync workflow.
 *
 * Env: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
 */
const { createClient } = require('@supabase/supabase-js');

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');

  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'GET') return res.status(405).json({ error: 'Method not allowed' });

  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceKey  = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceKey) {
    return res.status(500).json({
      error: 'Server misconfigured: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set in Vercel env vars',
    });
  }

  const supabase = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  try {
    // Page through ALL rows. PostgREST caps a single .select() at 1000 rows
    // by default, so once the table crosses 1000 jobs a plain select would
    // silently truncate — hiding jobs from the dashboard. We fetch in 1000-
    // row pages via .range() until a short page comes back.
    const PAGE = 1000;
    let all = [];
    for (let from = 0; ; from += PAGE) {
      const { data, error } = await supabase
        .from('jobs')
        .select('*')
        .order('num', { ascending: true })
        .range(from, from + PAGE - 1);
      if (error) {
        console.error('Supabase select error:', error);
        return res.status(500).json({ error: error.message });
      }
      all = all.concat(data || []);
      if (!data || data.length < PAGE) break;   // last page
    }

    // 10s edge cache with SWR so rapid status changes feel snappy without
    // hitting the DB on every request.
    res.setHeader('Cache-Control', 'public, s-maxage=10, stale-while-revalidate=30');
    return res.status(200).json(all);
  } catch (e) {
    console.error('Unexpected error in /api/jobs:', e);
    return res.status(500).json({ error: e.message || String(e) });
  }
};
