/**
 * TEMPORARY diagnostic endpoint — returns metadata about env wiring.
 * Does NOT leak the service-role key. Delete after debugging.
 * GET /api/_diag
 */
module.exports = async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store');

  const url = process.env.SUPABASE_URL || '';
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

  let supabaseSdkLoadable = false;
  let sdkLoadError = null;
  try {
    require('@supabase/supabase-js');
    supabaseSdkLoadable = true;
  } catch (e) {
    sdkLoadError = e.message;
  }

  // Try a raw fetch to Supabase to confirm reachability + auth without using the SDK.
  let restProbe = null;
  if (url && key) {
    try {
      const r = await fetch(`${url}/rest/v1/jobs?select=id&limit=1`, {
        headers: { apikey: key, Authorization: `Bearer ${key}` },
      });
      restProbe = {
        status: r.status,
        bodyPreview: (await r.text()).slice(0, 200),
      };
    } catch (e) {
      restProbe = { error: e.message };
    }
  }

  return res.status(200).json({
    supabase_url_value: url || '(empty)',
    supabase_url_length: url.length,
    service_role_key_length: key.length,
    service_role_key_prefix: key ? key.slice(0, 6) + '…' : '(empty)',
    supabase_sdk_loadable: supabaseSdkLoadable,
    sdk_load_error: sdkLoadError,
    raw_rest_probe: restProbe,
  });
};
