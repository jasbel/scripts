import fs from 'node:fs';
import path from 'node:path';
import { PATHS } from './config.js';
import { listProjects } from './projects.js';
import { renderOdooInline } from './odoo-render.js';

/* =========================================================================
 * Render estatico de las plantillas odoo: aplica data.json a templates/*.html
 * (mismo engine odoo-inline que el preview) y escribe el HTML final en
 * <raiz odoo>/dist/<id>.html.
 *
 * CLI: node dist.js [--data <file>]
 *   --data <file>  JSON alternativo (ruta relativa a la raiz odoo o absoluta);
 *                  default: <raiz odoo>/data.json
 * ========================================================================= */

function parseArgs(argv) {
  const out = { dataFile: null };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--data' && i + 1 < argv.length) out.dataFile = argv[++i];
    else if (argv[i] === '--data') {
      console.error('--data requiere la ruta de un JSON');
      process.exit(1);
    }
  }
  return out;
}

const { dataFile } = parseArgs(process.argv.slice(2));

const project = listProjects().find((p) => p.id === 'odoo');
if (!project || !project.available) {
  console.error(project?.reason || '[dist] proyecto odoo no disponible');
  process.exit(1);
}

const dataPath = dataFile
  ? path.resolve(PATHS.odooRoot, dataFile)
  : PATHS.odooDataJson;
if (!fs.existsSync(dataPath)) {
  console.error(`[dist] no se encuentra ${dataPath}`);
  process.exit(1);
}
const data = JSON.parse(fs.readFileSync(dataPath, 'utf8'));

const outDir = path.join(PATHS.odooRoot, 'dist');
fs.mkdirSync(outDir, { recursive: true });

// Reportes generados dentro de templates/ que no son plantillas de email.
const IGNORED = new Set(['css-report.html']);

const rel = (p) => path.relative(PATHS.odooRoot, p);
const emails = project.templates.filter((t) => !IGNORED.has(path.basename(t.entry)));
let written = 0;
let failed = false;
for (const tpl of emails) {
  try {
    const unresolved = [];
    const src = fs.readFileSync(tpl.entry, 'utf8');
    const html = renderOdooInline(src, data, {
      onUnresolved(p) { unresolved.push(p); },
    });
    const outFile = path.join(outDir, path.basename(tpl.entry));
    fs.writeFileSync(outFile, html);
    written++;
    const warn = unresolved.length
      ? ` (${unresolved.length} sin datos: ${[...new Set(unresolved)].slice(0, 3).join(', ')}${unresolved.length > 3 ? '...' : ''})`
      : '';
    console.log(`[dist] ${rel(tpl.entry)} -> ${rel(outFile)}${warn}`);
  } catch (e) {
    failed = true;
    console.error(`[dist] ${rel(tpl.entry)}: ${e.message}`);
  }
}

console.log(`[dist] ${written}/${emails.length} plantillas renderizadas con ${rel(dataPath)} -> dist/`);
if (failed) process.exitCode = 1;
