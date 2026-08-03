/**
 * POST /api/bulk-delete-nla
 *
 * SOFT-deletes every row in the Supabase 'jobs' table whose status is
 * "No Longer Available" by setting status = 'Deleted'. Used by the
 * dashboard's red "Clear NLA" button to declutter the tracker.
 *
 * Why soft delete: rows hard-deleted from Supabase get RESURRECTED by the
 * daily migrate_to_supabase.py sync — their IDs still exist in jobs.json,
 * so the INSERT-only sync sees them as "new" and re-inserts them as
 * "Not Applied" (bug observed 2026-08-03: 184 cleared rows came back).
 * Keeping the row with status 'Deleted' means it stays in existing_ids
 * and is never re-inserted. /api/jobs filters 'Deleted' rows out, so the
 * dashboard never shows them.
 *
 * Recovery path: rows are still in the table (status 'Deleted') and in the
 * daily snapshots web/data/jobs-snapshot-YYYY-MM-DD.json. Restore by
 * setting status back via /api/sync-status.
 *
 * Returns: { success, deletedCount }
 */
const { createClient } = require('@supabase/supabase-js');

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const supabaseUrl = process.env.SUPABASE_URL;
  const serviceKey  = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!supabaseUrl || !serviceKey) {
    return res.status(500).json({ error: 'Server misconfigured: SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY not set' });
  }

  const supabase = createClient(supabaseUrl, serviceKey, {
    auth: { persistSession: false, autoRefreshToken: false },
  });

  try {
    // First count how many rows we're about to delete (for the response)
    const { count } = await supabase
      .from('jobs')
      .select('id', { count: 'exact', head: true })
      .eq('status', 'No Longer Available');

    if (!count || count === 0) {
      return res.status(200).json({ success: true, deletedCount: 0, message: 'Nothing to delete.' });
    }

    // Soft delete: keep the rows so the INSERT-only daily sync never
    // re-inserts them; /api/jobs hides status 'Deleted' from the dashboard.
    const { error } = await supabase
      .from('jobs')
      .update({ status: 'Deleted' })
      .eq('status', 'No Longer Available');
    if (error) {
      console.error('Soft-delete error:', error);
      return res.status(500).json({ error: error.message });
    }
    return res.status(200).json({ success: true, deletedCount: count });
  } catch (e) {
    return res.status(500).json({ error: e.message || String(e) });
  }
};
