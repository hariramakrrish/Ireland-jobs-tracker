/**
 * POST /api/bulk-delete-nla
 *
 * Permanently removes every row in the Supabase 'jobs' table whose status
 * is "No Longer Available". Used by the dashboard's red "Clear NLA" button
 * to declutter the tracker after the user has decided those roles aren't
 * relevant.
 *
 * Recovery path: the daily snapshot workflow stores a full dump of every
 * row in web/data/jobs-snapshot-YYYY-MM-DD.json (committed to git). If
 * something is deleted by mistake, restore from the previous day's
 * snapshot.
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

    // Delete
    const { error } = await supabase
      .from('jobs')
      .delete()
      .eq('status', 'No Longer Available');
    if (error) {
      console.error('Delete error:', error);
      return res.status(500).json({ error: error.message });
    }
    return res.status(200).json({ success: true, deletedCount: count });
  } catch (e) {
    return res.status(500).json({ error: e.message || String(e) });
  }
};
