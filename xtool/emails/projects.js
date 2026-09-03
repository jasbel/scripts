import fs from 'node:fs';
import path from 'node:path';
import Mustache from 'mustache';
import { PATHS } from './config.js';
import { renderOdooInline } from './odoo-render.js';

/* =========================================================================
 * Registro de proyectos de plantillas. Cada proyecto declara un engine y
 * donde viven sus plantillas; el servidor monta rutas genericas a partir
 * de aqui:
 *   - solocruceros: engine mustache, template en el repo PHP externo
 *   - odoo:        engine odoo-inline, plantillas en este repo
 * ========================================================================= */

const ENGINES = {
  mustache: {
    render(templateSrc, data, ctx) {
      const partials = {};
      if (fs.existsSync(ctx.partialsDir)) {
        for (const f of fs.readdirSync(ctx.partialsDir)) {
          if (f.endsWith('.mustache')) {
            partials['components/' + f.replace(/\.mustache$/, '')] =
              fs.readFileSync(path.join(ctx.partialsDir, f), 'utf8');
          }
        }
      }
      // Igualar escape al de Mustache.php: solo & < > " (no / ' ` =)
      Mustache.escape = (s) =>
        String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
      Mustache.tags = ['{{', '}}'];
      return Mustache.render(templateSrc, data, partials);
    },
  },
  'odoo-inline': {
    render(templateSrc, data) {
      return renderOdooInline(templateSrc, data, {
        onUnresolved(p) {
          console.warn(`[odoo] placeholder sin datos: {{ ${p} }}`);
        },
      });
    },
  },
};

function readJsonSafe(file) {
  try {
    return JSON.parse(fs.readFileSync(file, 'utf8'));
  } catch (e) {
    console.warn(`[data] no se pudo leer ${file}:`, e.message);
    return {};
  }
}

/* Todos los templates odoo comparten un unico data.json en <raiz odoo>/data.json
 * y los assets viven en <raiz odoo>/public/assets (servidos en /assets).
 * Layout plano: <raiz odoo>/templates/<id>.html (salida del build del repo
 * externo, ya con includes resueltos). */
function odooTemplates() {
  const dir = PATHS.odooTemplatesDir;
  if (!fs.existsSync(dir)) return [];
  return fs.readdirSync(dir, { withFileTypes: true })
    .filter((d) => d.isFile() && d.name.endsWith('.html'))
    .map((d) => ({
      id: d.name.replace(/\.html$/, ''),
      entry: path.join(dir, d.name),
      dataJson: PATHS.odooDataJson,
    }));
}

export function listProjects() {
  const solocrucerosAvailable = fs.existsSync(PATHS.mustache);
  return [
    {
      id: 'solocruceros',
      engine: 'mustache',
      available: solocrucerosAvailable,
      reason: solocrucerosAvailable
        ? null
        : `No se encuentra ${PATHS.mustache}. Define SOLOCRUCEROS_TEMPLATES_DIR en .env apuntando al directorio de templates del repo PHP.`,
      templates: [
        {
          id: 'reserve',
          entry: PATHS.mustache,
          dataJson: PATHS.dataJson,
          partialsDir: PATHS.componentsDir,
        },
      ],
    },
    {
      id: 'odoo',
      engine: 'odoo-inline',
      available: true,
      reason: null,
      templates: odooTemplates(),
    },
  ];
}

export function getTemplate(projectId, tplId) {
  const project = listProjects().find((p) => p.id === projectId);
  if (!project) {
    const err = new Error(`Proyecto desconocido: ${projectId}`);
    err.status = 404;
    throw err;
  }
  if (!project.available) {
    const err = new Error(project.reason);
    err.status = 503;
    throw err;
  }
  const tpl = project.templates.find((t) => t.id === tplId);
  if (!tpl) {
    const err = new Error(`Plantilla desconocida: ${projectId}/${tplId}`);
    err.status = 404;
    err.supported = project.templates.map((t) => t.id);
    throw err;
  }
  return {
    project,
    id: tpl.id,
    entry: tpl.entry,
    dataJson: tpl.dataJson,
    loadTemplateSrc: () => fs.readFileSync(tpl.entry, 'utf8'),
    loadData: () => readJsonSafe(tpl.dataJson),
    render() {
      const engine = ENGINES[project.engine];
      return engine.render(this.loadTemplateSrc(), this.loadData(), {
        partialsDir: tpl.partialsDir,
      });
    },
  };
}

// Rutas para el watcher (solo las que existen en esta maquina)
export function watchTargets() {
  const targets = [];
  const solocrucerosDir = PATHS.templatesDir;
  if (fs.existsSync(solocrucerosDir)) {
    targets.push(path.join(solocrucerosDir, '**', '*.mustache'));
  }
  if (fs.existsSync(PATHS.dataJson)) targets.push(PATHS.dataJson);
  if (fs.existsSync(PATHS.odooRoot)) {
    // Fuentes del repo externo (cambian -> rebuild externo -> cambia templates/)
    targets.push(path.join(PATHS.odooRoot, 'src', 'template', '**', '*.html'));
    targets.push(path.join(PATHS.odooTemplatesDir, '**', '*.html'));
    targets.push(PATHS.odooDataJson);
  }
  return targets;
}
