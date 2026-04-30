#!/usr/bin/env node
/**
 * Build script: injects GITHUB_TOKEN into index.html at Vercel build time.
 * The token never appears in the git repo — only in the deployed output.
 */
const fs   = require('fs');
const path = require('path');

const token = process.env.GITHUB_TOKEN || '';
if (!token) {
  console.warn('⚠  GITHUB_TOKEN not set — status sync will be disabled in production');
}

// Read source index.html
const src = path.join(__dirname, 'index.html');
let html  = fs.readFileSync(src, 'utf8');

// Inject token into the placeholder
html = html.replace('__GITHUB_TOKEN_PLACEHOLDER__', token);

// Write output (Vercel will serve from dist/)
const distDir = path.join(__dirname, 'dist');
fs.mkdirSync(distDir, { recursive: true });
fs.writeFileSync(path.join(distDir, 'index.html'), html);

// Copy data/ and resumes/ into dist/
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
copyDir(path.join(__dirname, 'data'),    path.join(distDir, 'data'));
copyDir(path.join(__dirname, 'resumes'), path.join(distDir, 'resumes'));

console.log(`✅  Build complete → dist/  (token injected: ${token ? 'yes' : 'NO'})`);
