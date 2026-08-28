import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import chokidar from 'chokidar';
import mjml2html from 'mjml';
import { PATHS } from './config.js';

/* =========================================================================
 * Compilacion MJML -> HTML para plantillas odoo.
 * Convencion: templates/odoo/<id>/body.mjml compila a templates/odoo/<id>/body.html
 * (el mismo body.html que consume el engine odoo-inline). Los placeholders
 * {{ }} de Odoo dentro de <mj-text>/<mj-button>/... pasan intactos al HTML.
 * ========================================================================= */

async function compileMjmlFile(file) {
  const rel = path.relative(process.cwd(), file);
  try {
    const src = fs.readFileSync(file, 'utf8');
    const { html, errors = [] } = await mjml2html(src, { validationLevel: 'soft' });
    if (errors.length) {
      console.error(`[mjml] ${rel}:`);
      for (const e of errors) console.error(`  - ${e.formattedMessage || e.message}`);
      return false;
    }
    const out = file.replace(/\.mjml$/, '.html');
    fs.writeFileSync(out, html);
    console.log(`[mjml] ${rel} -> ${path.relative(process.cwd(), out)}`);
    return true;
  } catch (e) {
    console.error(`[mjml] ${rel}: ${e.message}`);
    return false;
  }
}

export function findMjmlFiles(dir = PATHS.odooTemplatesDir) {
  if (!fs.existsSync(dir)) return [];
  const files = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) files.push(...findMjmlFiles(full));
    else if (entry.name.endsWith('.mjml')) files.push(full);
  }
  return files;
}

export async function compileAll() {
  const files = findMjmlFiles();
  let ok = 0;
  for (const f of files) if (await compileMjmlFile(f)) ok++;
  return { total: files.length, ok };
}

let debounce;
export function watchMjml() {
  const watcher = chokidar.watch(path.join(PATHS.odooTemplatesDir, '**', '*.mjml'), {
    ignoreInitial: true,
    followSymlinks: true,
  });
  watcher.on('error', (e) => console.error('[mjml] watch error:', e.message));
  watcher.on('all', (event, file) => {
    if (event !== 'add' && event !== 'change') return;
    clearTimeout(debounce);
    debounce = setTimeout(() => compileMjmlFile(file), 100);  });
  return watcher;
}

/* CLI: node mjml-build.js [--watch] */
const invokedAsCli =
  process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (invokedAsCli) {
  if (process.argv.includes('--watch')) {
    console.log('[mjml] observando', path.join(PATHS.odooTemplatesDir, '**', '*.mjml'));
    await compileAll();
    watchMjml();
  } else {
    const { total, ok } = await compileAll();
    if (!total) console.log('[mjml] no hay archivos .mjml en', PATHS.odooTemplatesDir);
    else if (ok < total) process.exitCode = 1;
  }
}
