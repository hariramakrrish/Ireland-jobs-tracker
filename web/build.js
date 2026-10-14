#!/usr/bin/env node
/**
 * Build script: copies index.html + resumes/ into dist/ and writes
 * dist/resumes.json (every PDF in this deployment) so the dashboard can tell
 * a ready resume from a missing one instead of linking to a 404.
 * Nothing secret goes into dist/ — everything there is public.
 */
const fs   = require('fs');
const path = require('path');

// Write output (Vercel will serve from dist/)
const distDir = path.join(__dirname, 'dist');
fs.mkdirSync(distDir, { recursive: true });
fs.copyFileSync(path.join(__dirname, 'index.html'), path.join(distDir, 'index.html'));

// Copy resumes/ into dist/. data/ is deliberately NOT deployed: it holds
// jobs.json plus ~900 MB of daily Supabase snapshots that are git-only
// backups — nothing on the site reads them (the dashboard uses /api/jobs),
// and shipping them made every deployment ~1 GB.
function copyDir(src, dest) {
  if (!fs.existsSync(src)) return;
  fs.mkdirSync(dest, { recursive: true });
  for (const entry of fs.readdirSync(src, { withFileTypes: true })) {
    const s = path.join(src, entry.name);
    const d = path.join(dest, entry.name);
    if (entry.isDirectory()) copyDir(s, d);
    else fs.copyFileSync(s, d);
  }
}
const resumesDir = path.join(__dirname, 'resumes');
copyDir(resumesDir, path.join(distDir, 'resumes'));

const pdfs = fs.existsSync(resumesDir)
  ? fs.readdirSync(resumesDir).filter(f => f.endsWith('.pdf')).sort()
  : [];
fs.writeFileSync(path.join(distDir, 'resumes.json'), JSON.stringify(pdfs));

console.log(`✅  Build complete → dist/  (${pdfs.length} resumes)`);
