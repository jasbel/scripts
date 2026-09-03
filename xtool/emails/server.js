import 'dotenv/config';
import express from 'express';
import WebSocket, { WebSocketServer } from 'ws';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import chokidar from 'chokidar';
import { PATHS } from './config.js';
import { listProjects, getTemplate, watchTargets } from './projects.js';
import { sendTestHtml, SMTP_ENV } from './send.js';
import { filterForClient, getSupportedClients } from './email-client-filter.js';
import { wrapInMockup, hasMockup, buildMockupContext } from './email-mockups.js';
import { compileAll, watchMjml } from './mjml-build.js';

const PORT = process.env.PORT || 3466;

const app = express();

/* =========================================================================
 * Helpers
 * ========================================================================= */

function sendErr(res, e) {
  const status = e.status || 500;
  const body = { ok: false, error: e.message };
  if (e.supported) body.supported = e.supported;
  res.status(status).json(body);
}

/* Cliente WS de hot-reload para las paginas servidas directamente
 * (/render, /preview): preview.html ya tiene el suyo, pero estas rutas
 * navegadas solas no recargaban al guardar. Con innerHTML no se ejecuta,
 * asi que no hay doble conexion dentro del iframe de preview.html. */
const HOT_RELOAD_SNIPPET = `<script>(function () {
  if (window.__emailHotReload) return;
  window.__emailHotReload = true;
  var dropped = false;
  function connect() {
    var proto = location.protocol === 'https:' ? 'wss' : 'ws';
    var ws = new WebSocket(proto + '://' + location.host + '/ws');
    ws.onopen = function () { if (dropped) location.reload(); };
    ws.onmessage = function (ev) {
      try { if (JSON.parse(ev.data).type === 'reload') location.reload(); } catch (e) {}
    };
    ws.onclose = function () {
      dropped = true;
      setTimeout(connect, 1000);
    };
  }
  connect();
})();</script>`;

function withHotReload(html) {
  if (typeof html !== 'string') return html;
  return /<\/body>/i.test(html)
    ? html.replace(/<\/body>/i, HOT_RELOAD_SNIPPET + '$&')
    : html + HOT_RELOAD_SNIPPET;
}

function templateFrom(req) {
  return getTemplate(req.params.project, req.params.tpl);
}

function checkClient(res, client) {
  if (!getSupportedClients().includes(client) && client !== 'original') {
    res.status(400).json({
      error: 'Cliente no soportado',
      supported: ['original', ...getSupportedClients()],
    });
    return false;
  }
  return true;
}

/* =========================================================================
 * API: registro de proyectos/plantillas (lo consume el selector de preview)
 * ========================================================================= */

app.get('/api/templates', (_req, res) => {
  res.json({
    projects: listProjects().map((p) => ({
      id: p.id,
      engine: p.engine,
      available: p.available,
      reason: p.reason,
      templates: p.templates.map((t) => t.id),
    })),
  });
});

/* Defaults de envio leidos de .env: prellenan el panel de "Enviar prueba" */
app.get('/api/send-config', (_req, res) => {
  res.json({
    to: SMTP_ENV.to || '',
    cc: SMTP_ENV.cc || '',
    subject: SMTP_ENV.subject || '',
  });
});

/* Assets de los templates odoo: /assets/<file> desde <raiz odoo>/public/assets.
 * Debe ir antes de las rutas genericas /:project/:tpl/render/:client
 * para que "assets" no se interprete como :client. */
app.get('/assets/*', (req, res) => {
  const file = path.resolve(PATHS.odooAssetsDir, req.params[0]);
  if (!file.startsWith(PATHS.odooAssetsDir + path.sep) || !fs.existsSync(file)) {
    return res.status(404).json({ ok: false, error: 'Asset no encontrado' });
  }
  res.sendFile(file);
});

/* =========================================================================
 * Rutas genericas: /:project/:tpl/...
 *   /:project/:tpl/render            HTML renderizado
 *   /:project/:tpl/render/:client    HTML filtrado para un cliente
 *   /:project/:tpl/preview/:client   HTML filtrado + mockup del cliente
 *   /:project/:tpl/data              JSON de datos
 *   POST /:project/:tpl/send-test    envio SMTP de prueba
 * ========================================================================= */

app.get('/:project/:tpl/render', (req, res) => {
  try {
    const t = templateFrom(req);
    res.type('html').send(withHotReload(t.render()));
  } catch (e) {
    sendErr(res, e);
  }
});

app.get('/:project/:tpl/render/:client', (req, res) => {
  if (!checkClient(res, req.params.client)) return;
  try {
    const t = templateFrom(req);
    res.type('html').send(withHotReload(filterForClient(t.render(), req.params.client)));
  } catch (e) {
    sendErr(res, e);
  }
});

app.get('/:project/:tpl/preview/:client', (req, res) => {
  if (!checkClient(res, req.params.client)) return;
  try {
    const t = templateFrom(req);
    const filtered = filterForClient(t.render(), req.params.client);

    if (!hasMockup(req.params.client)) {
      return res.type('html').send(withHotReload(filtered));
    }

    const ctx = buildMockupContext({
      smtpEnv: { user: SMTP_ENV.user, to: SMTP_ENV.to, subject: SMTP_ENV.subject },
      data: t.loadData(),
    });
    res.type('html').send(withHotReload(wrapInMockup(req.params.client, filtered, ctx)));
  } catch (e) {
    sendErr(res, e);
  }
});

app.get('/:project/:tpl/data', (req, res) => {
  try {
    res.json(templateFrom(req).loadData());
  } catch (e) {
    sendErr(res, e);
  }
});

app.use(express.json());

async function sendTestRoute(req, res) {
  const cfg = !SMTP_ENV.user || !SMTP_ENV.pass ? null : {
    user: SMTP_ENV.user ? '****' + SMTP_ENV.user.slice(-12) : '(vacio)',
    to:   SMTP_ENV.to || '(vacio)',
    cc:   SMTP_ENV.cc || '(vacio)',
  };
  try {
    const t = templateFrom(req);
    const html = t.render();
    const { to, cc, subject, messageId } = await sendTestHtml({
      html,
      subject: req.body?.subject,
      to: req.body?.to,
      cc: req.body?.cc,
    });
    console.log(`[send] ${t.project.id}/${t.id} enviado a ${to} · cc=${cc} · subject="${subject}" · id=${messageId}`);
    res.json({ ok: true, to, subject, messageId });
  } catch (e) {
    console.error('[send] error:', e.message);
    if (e.code === 'NO_CONFIG') {
      return res.status(400).json({
        ok: false,
        error: e.message,
        hint: 'Crea .env a partir de .env.example con tus credenciales de Gmail.',
        currentConfig: cfg,
      });
    }
    sendErr(res, e);
  }
}

app.post('/:project/:tpl/send-test', sendTestRoute);

/* =========================================================================
 * Rutas legacy (solocruceros/reserve) — compatibilidad con bookmarks
 * ========================================================================= */

app.get('/render', (_req, res) => {
  try {
    res.type('html').send(withHotReload(getTemplate('solocruceros', 'reserve').render()));
  } catch (e) {
    sendErr(res, e);
  }
});

app.get('/render/:client', (req, res) => {
  if (!checkClient(res, req.params.client)) return;
  try {
    res.type('html').send(withHotReload(filterForClient(getTemplate('solocruceros', 'reserve').render(), req.params.client)));
  } catch (e) {
    sendErr(res, e);
  }
});

app.get('/preview/:client', (req, res) => {
  if (!checkClient(res, req.params.client)) return;
  try {
    const t = getTemplate('solocruceros', 'reserve');
    const filtered = filterForClient(t.render(), req.params.client);
    if (!hasMockup(req.params.client)) {
      return res.type('html').send(withHotReload(filtered));
    }
    const ctx = buildMockupContext({
      smtpEnv: { user: SMTP_ENV.user, to: SMTP_ENV.to, subject: SMTP_ENV.subject },
      data: t.loadData(),
    });
    res.type('html').send(withHotReload(wrapInMockup(req.params.client, filtered, ctx)));
  } catch (e) {
    sendErr(res, e);
  }
});

app.get('/data', (_req, res) => {
  try {
    res.json(getTemplate('solocruceros', 'reserve').loadData());
  } catch (e) {
    sendErr(res, e);
  }
});

app.post('/send-test', (req, res) => {
  req.params.project = 'solocruceros';
  req.params.tpl = 'reserve';
  sendTestRoute(req, res);
});

/* =========================================================================
 * Preview con marco Desktop/Mobile + hot-reload
 * ========================================================================= */

app.get('/', (_req, res) => {
  res.type('html').send(fs.readFileSync(PATHS.previewHtml, 'utf8'));
});

const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: '/ws' });

function broadcast(msg) {
  const payload = JSON.stringify(msg);
  for (const client of wss.clients) {
    if (client.readyState === WebSocket.OPEN) client.send(payload);
  }
}

/* MJML -> HTML: sincroniza al arrancar y recompila al guardar un .mjml.
 * La escritura de body.html dispara el watcher de arriba (hot-reload). */
compileAll();
watchMjml();

const targets = watchTargets();
if (!targets.length) {
  console.warn('[watch] sin rutas vigiables: no hay plantillas accesibles en esta maquina');
}
let debounce;
const watcher = chokidar.watch(targets, { ignoreInitial: true, followSymlinks: true });
watcher.on('error', (e) => console.error('[watch] error:', e.message));
watcher.on('all', (_event, file) => {
  console.log('[watch] cambio detectado:', file);
  clearTimeout(debounce);
  debounce = setTimeout(() => {
    try {
      broadcast({ type: 'reload' });
    } catch (e) {
      console.error('[watch] error al re-renderizar:', e.message);
    }
  }, 250);
});

server.listen(PORT, () => {
  console.log(`\n  Preview:   http://localhost:${PORT}`);
  for (const p of listProjects()) {
    for (const t of p.templates) {
      const flag = p.available ? '' : '  (NO DISPONIBLE en esta maquina)';
      console.log(`  ${p.id}/${t.id}:  http://localhost:${PORT}/${p.id}/${t.id}/render${flag}`);
    }
  }
  console.log(`  Datos:     http://localhost:${PORT}/api/templates\n`);
});
