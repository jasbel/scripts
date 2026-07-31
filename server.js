import 'dotenv/config';
import express from 'express';
import WebSocket, { WebSocketServer } from 'ws';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import Mustache from 'mustache';
import chokidar from 'chokidar';
import { PATHS } from './config.js';
import { sendTestHtml, SMTP_ENV } from './send.js';

const PORT = process.env.PORT || 3456;

const app = express();

function loadPartials() {
  const partials = {};
  const compDir = PATHS.componentsDir;
  if (fs.existsSync(compDir)) {
    for (const f of fs.readdirSync(compDir)) {
      if (f.endsWith('.mustache')) {
        const name = 'components/' + f.replace(/\.mustache$/, '');
        partials[name] = fs.readFileSync(path.join(compDir, f), 'utf8');
      }
    }
  }
  return partials;
}

function loadData() {
  try {
    return JSON.parse(fs.readFileSync(PATHS.dataJson, 'utf8'));
  } catch (e) {
    console.warn('[data] no se pudo leer data.json:', e.message);
    return {};
  }
}

function render() {
  const template = fs.readFileSync(PATHS.mustache, 'utf8');
  const partials = loadPartials();
  const data = loadData();
  // Igualar escape al de Mustache.php: solo & < > " (no / ' ` =)
  Mustache.escape = (s) =>
    String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  Mustache.tags = ['{{', '}}'];
  return Mustache.render(template, data, partials);
}

// HTML ya renderizado con datos reales (lo carga el iframe de preview.html)
app.get('/render', (_req, res) => {
  res.type('html').send(render());
});

// Devuelve el JSON de datos por si se quiere editar en el cliente
app.get('/data', (_req, res) => {
  res.json(loadData());
});

// Envia el email renderizado a TEST_TO por SMTP (prueba local)
app.use(express.json());
app.post('/send-test', async (req, res) => {
  const cfg = !SMTP_ENV.user || !SMTP_ENV.pass ? null : {
    user: SMTP_ENV.user ? '****' + SMTP_ENV.user.slice(-12) : '(vacio)',
    to:   SMTP_ENV.to || '(vacio)',
    cc:   SMTP_ENV.cc || '(vacio)',
  };
  try {
    const html = render();
    const { to, cc, subject, messageId } = await sendTestHtml({
      html,
      subject: req.body?.subject,
      to: req.body?.to,
      cc: req.body?.cc,
    });
    console.log(`[send] enviado a ${to} · cc=${cc} · subject="${subject}" · id=${messageId}`);
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
    res.status(500).json({ ok: false, error: e.message });
  }
});

// Preview con marco Desktop/Mobile + hot-reload
app.get('/', (_req, res) => {
  res.type('html').send(previewShell());
});

function previewShell() {
  return fs.readFileSync(path.join(path.dirname(new URL(import.meta.url).pathname), 'preview.html'), 'utf8');
}

const server = http.createServer(app);
const wss = new WebSocketServer({ server, path: '/ws' });

function broadcast(msg) {
  const payload = JSON.stringify(msg);
  for (const client of wss.clients) {
    if (client.readyState === WebSocket.OPEN) client.send(payload);
  }
}

let debounce;
const watcher = chokidar.watch(
  [path.join(PATHS.templatesDir, '**/*.mustache'), PATHS.dataJson],
  { ignoreInitial: true, followSymlinks: true }
);
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
  console.log(`  Render:    http://localhost:${PORT}/render`);
  console.log(`  Datos:     http://localhost:${PORT}/data\n`);
});
