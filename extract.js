import fs from 'node:fs';
import path from 'node:path';
import Mustache from 'mustache';
import { PATHS, ARRAY_SECTIONS, OBJECT_SECTIONS } from './config.js';

/* =========================================================================
 * 1. TOKENIZER (Mustache)
 * ========================================================================= */

function tokenize(src) {
  const tokens = [];
  let i = 0;
  const len = src.length;
  const pushText = (s) => { if (s) tokens.push({ type: 'text', value: s }); };

  while (i < len) {
    const start = src.indexOf('{{', i);
    if (start === -1) { pushText(src.slice(i)); break; }
    pushText(src.slice(i, start));

    const c = src[start + 2];

    // {{{unescaped}}}
    if (c === '{') {
      const end = src.indexOf('}}}', start + 3);
      if (end === -1) { pushText(src.slice(start)); break; }
      tokens.push({ type: 'name', key: src.slice(start + 3, end).trim(), unescaped: true });
      i = end + 3;
      continue;
    }
    // {{&unescaped}}
    if (c === '&') {
      const end = src.indexOf('}}', start + 3);
      tokens.push({ type: 'name', key: src.slice(start + 3, end).trim(), unescaped: true });
      i = end + 2; continue;
    }
    // {{! comment }}
    if (c === '!') {
      const end = src.indexOf('}}', start + 3);
      i = end + 2; continue; // skip
    }
    // {{=newdelim newdelim=}} (set delimiters -> ignore, not used here)
    if (c === '=') {
      const end = src.indexOf('}}', start + 3);
      i = end + 2; continue;
    }
    const end = src.indexOf('}}', start + 2);
    if (end === -1) { pushText(src.slice(start)); break; }
    const inner = src.slice(start + 2, end).trim();

    const name = src.slice(start + 3, end).trim();
    if (c === '#') tokens.push({ type: '#', key: name });
    else if (c === '^') tokens.push({ type: '^', key: name });
    else if (c === '/') tokens.push({ type: '/', key: name });
    else if (c === '>') tokens.push({ type: '>', partial: name });
    else tokens.push({ type: 'name', key: inner, unescaped: false });

    i = end + 2;
  }
  return tokens;
}

/* =========================================================================
 * 2. PARTIAL INLINING
 * ========================================================================= */

function loadPartial(name) {
  const file = path.join(PATHS.componentsDir.replace('/components', ''), name + '.mustache');
  // name p.ej. "components/reserve-transport"
  const direct = path.join(PATHS.templatesDir, name + '.mustache');
  const p = fs.existsSync(direct) ? direct : file;
  return fs.readFileSync(p, 'utf8');
}

function inlinePartials(tokens, depth = 0) {
  if (depth > 5) return tokens;
  const out = [];
  for (const t of tokens) {
    if (t.type === '>') {
      const src = loadPartial(t.partial);
      out.push(...inlinePartials(tokenize(src), depth + 1));
    } else {
      out.push(t);
    }
  }
  return out;
}

/* =========================================================================
 * 3. AST BUILDER
 * ========================================================================= */

function buildAst(tokens) {
  const root = { type: 'root', body: [] };
  const stack = [root];
  for (const t of tokens) {
    const top = stack[stack.length - 1];
    if (t.type === '#' || t.type === '^') {
      const node = { type: t.type, key: t.key, body: [] };
      top.body.push(node);
      stack.push(node);
    } else if (t.type === '/') {
      const popped = stack.pop();
      popped.closeKey = t.key;
    } else {
      top.body.push(t);
    }
  }
  return root;
}

/* =========================================================================
 * 4. HELPERS: whitespace-tolerant literal matching
 * ========================================================================= */

function escapeRegex(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

// Decodifica entidades HTML (para campos {{x}} escapados que se capturan ya escapados del HTML).
function decodeEntities(s) {
  return s
    .replace(/&lt;/g, '<')
    .replace(/&gt;/g, '>')
    .replace(/&quot;/g, '"')
    .replace(/&#0?39;/g, "'")
    .replace(/&amp;/g, '&');
}

// Convierte un literal en un patron regex tolerante a espacios: trozos no
// vacios separados por \s+ (acepta cualquier cantidad/ tipo de whitespace).
function litPattern(literal) {
  const parts = literal.split(/[ \t\r\n\f\v]+/).filter(Boolean).map(escapeRegex);
  return parts.join('\\s+');
}

// Coincide `literal` exactamente en html[pos..] (sticky), devuelve longitud consumida o -1.
function matchLiteralAt(html, pos, literal) {
  const pat = litPattern(literal);
  if (!pat) return 0;
  // \s* inicial: el text-node puede empezar con whitespace cuya cantidad difiere
  // entre template y HTML producido (standalone line stripping del motor Mustache).
  const re = new RegExp('\\s*' + pat, 'y');
  re.lastIndex = pos;
  const m = re.exec(html);
  return m ? m[0].length : -1;
}

// Encuentra la primera posicion >= pos donde `literal` encaja. Devuelve {index,len} o null.
function findLiteral(html, pos, literal) {
  const pat = litPattern(literal);
  if (!pat) return { index: pos, len: 0 };
  const re = new RegExp(pat, 'g');
  re.lastIndex = pos;
  const m = re.exec(html);
  if (!m) return null;
  return { index: m.index, len: m[0].length };
}

// Primer ancla "significativa" (texto no solo-whitespace) dentro de una lista de nodos.
function firstSignificantAnchor(nodes) {
  for (const n of nodes) {
    if (n.type === 'text') {
      if (n.value.trim().length > 0) return n.value;
    } else if (n.type === '#' || n.type === '^') {
      const a = firstSignificantAnchor(n.body);
      if (a) return a;
    }
  }
  return null;
}

// Primer ancla significativa mirando ADELANTE en la lista de hermanos desde fromIdx.
function continuationAnchor(nodes, fromIdx) {
  for (let j = fromIdx; j < nodes.length; j++) {
    if (nodes[j].type === 'text' && nodes[j].value.trim().length > 0) return nodes[j].value;
    if (nodes[j].type === '#' || nodes[j].type === '^') {
      const a = firstSignificantAnchor(nodes[j].body);
      if (a) return a;
    }
  }
  return null;
}

// ¿Cuerpo de seccion compuesto unicamente por {{key}} (sin texto)?
function bodyIsOnlySelfName(node) {
  return node.body.length === 1 && node.body[0].type === 'name' && node.body[0].key === node.key;
}

const DIAG = { log: [] };
function diag(msg) { DIAG.log.push(msg); }

/* =========================================================================
 * 5. ALIGNER: camina el AST contra el HTML producido -> data
 * ========================================================================= */

function alignBlock(nodes, html, pos, ctx) {
  for (let idx = 0; idx < nodes.length; idx++) {
    const node = nodes[idx];

    if (node.type === 'text') {
      const consumed = matchLiteralAt(html, pos, node.value);
      if (consumed < 0) {
        // Tolerancia: si el literal es solo whitespace lo saltamos (pegado a marker standalone).
        if (node.value.trim().length === 0) continue;
        // Recuperacion: el HTML producido puede tener contenido extra insertado a mano
        // (ej. un <p> adicional). Buscamos el mismo ancla mas adelante y saltamos el gap.
        // Ventana acotada: un gap grande indica desalineacion (ancla generica como <tr>),
        // no una insercion real.
        const found = findLiteral(html, pos, node.value);
        if (found && found.index > pos && found.index - pos < 800) {
          const gap = html.slice(pos, found.index);
          diag(`TEXT recuperado en pos ${pos}: salto de ${found.index - pos} chars (contenido insertado/extra). gap="${gap.slice(0, 60).replace(/\n/g, '\\n')}..."`);
          pos = found.index + found.len;
          continue;
        }
        diag(`TEXT no casa en pos ${pos}: "${node.value.slice(0, 60).replace(/\n/g, '\\n')}..."`);
        diag(`   html en pos: "${html.slice(pos, pos + 100).replace(/\n/g, '\\n')}"`);
        if (process.env.DEBUG_ALIGN) diag(`   html[-40..+40]: "${html.slice(Math.max(0, pos - 40), pos + 40).replace(/\n/g, '\\n')}"`);
        // Ultimo recurso: el HTML producido no contiene este literal (ej. comentarios
        // editados/eliminados a mano). Saltamos el nodo sin avanzar pos y continuamos.
        continue;
      }
      pos += consumed;
      if (process.env.DEBUG_ALIGN && consumed > 1000) diag(`TEXT grande consumido=${consumed} en pos ${pos - consumed}: "${node.value.slice(0, 50).replace(/\n/g, '\\n')}..."`);
      continue;
    }

    if (node.type === 'name') {
      // capturar valor = texto hasta el proximo ancla (siguiente text sibling o fin)
      let anchor = null;
      for (let j = idx + 1; j < nodes.length; j++) {
        if (nodes[j].type === 'text' && nodes[j].value.trim().length > 0) { anchor = nodes[j].value; break; }
        if (nodes[j].type === '#' || nodes[j].type === '^') {
          const a = firstSignificantAnchor(nodes[j].body);
          if (a) { anchor = a; break; }
        }
      }
      let value;
      if (anchor) {
        const found = findLiteral(html, pos, anchor);
        if (process.env.DEBUG_ALIGN) diag(`NAME "${node.key}" pos=${pos} anchorFound=${!!found} anchor="${anchor.slice(0, 40).replace(/\n/g, '\\n')}"`);
        if (found) {
          value = html.slice(pos, found.index);
          pos = found.index;
        } else {
          value = html.slice(pos);
          pos = html.length;
          diag(`NAME "${node.key}": ancla no encontrada, capturo hasta el final`);
        }
      } else {
        value = html.slice(pos);
        pos = html.length;
      }
      value = value.trim();
      // Los campos escapados {{x}} se capturan ya escapados del HTML producido:
      // los decodificamos para que el re-render los escape una sola vez.
      if (!node.unescaped) value = decodeEntities(value);
      if (!(node.key in ctx) || ctx[node.key] === undefined || ctx[node.key] === '') {
        ctx[node.key] = value;
      }
      continue;
    }

    if (node.type === '#') {
      // Patron valor-o-default: {{#x}}{{x}}{{/x}}{{^x}}-{{/x}}
      // El cuerpo de #x es solo {{x}} (sin texto ancla) y le sigue ^x con el default.
      const next = nodes[idx + 1];
      if (bodyIsOnlySelfName(node) && next && next.type === '^' && next.key === node.key) {
        const defaultText = (next.body.find((n) => n.type === 'text') || {}).value || '';
        const contAnchor = continuationAnchor(nodes, idx + 2);
        let value;
        if (contAnchor) {
          const found = findLiteral(html, pos, contAnchor);
          if (found) { value = html.slice(pos, found.index); pos = found.index; }
          else { value = html.slice(pos); pos = html.length; }
        } else { value = html.slice(pos); pos = html.length; }
        value = value.trim();
        const def = defaultText.trim();
        ctx[node.key] = value && value !== def ? decodeEntities(value) : false;
        idx++; // consumir tambien el ^x
        continue;
      }
      // Patron simple: {{#x}}{{x}}{{/x}} sin texto ancla -> valor hasta la continuacion.
      if (bodyIsOnlySelfName(node)) {
        const contAnchor = continuationAnchor(nodes, idx + 1);
        let value;
        if (contAnchor) {
          const found = findLiteral(html, pos, contAnchor);
          if (found) { value = html.slice(pos, found.index); pos = found.index; }
          else { value = html.slice(pos); pos = html.length; }
        } else { value = html.slice(pos); pos = html.length; }
        value = value.trim();
        ctx[node.key] = value ? decodeEntities(value) : false;
        continue;
      }
      pos = alignSection(node, html, pos, ctx, false);
      continue;
    }
    if (node.type === '^') {
      pos = alignSection(node, html, pos, ctx, true);
      continue;
    }
  }
  return pos;
}

function alignSection(node, html, pos, ctx, inverted) {
  const key = node.key;

  // helpers de Mustache @first/@index/@last -> no afectan data (contexto de bucle)
  if (key.startsWith('@')) {
    // renderizar el cuerpo sin modificar data (su ancla ya viene del padre)
    return alignBlock(node.body, html, pos, ctx);
  }

  const isArray = ARRAY_SECTIONS.has(key);
  const isObject = OBJECT_SECTIONS.has(key);
  const leadingAnchor = firstSignificantAnchor(node.body);
  if (process.env.DEBUG_ALIGN) diag(`SEC ^${key} pos=${pos} ctx[key]=${ctx[key]} leading="${(leadingAnchor || '').slice(0, 40).replace(/\n/g, '\\n')}"`);

  // Para invertido ^: el cuerpo aparece cuando la clave es FALSA.
  if (inverted) {
    // Par if/else #X.../X ^X.../X: si un #X previo ya dejo X truthy, el ^X se omite
    // (mutuamente excluyente). Evita doble consumo cuando ambos cuerpos comparten
    // anclas genericas (ej. los parciales de transporte empiezan con <tr>).
    if (ctx[key]) return pos;

    let matches = false;
    if (leadingAnchor) {
      const found = findLiteral(html, pos, leadingAnchor);
      matches = found && found.index <= pos + 200; // ancla cerca de la posicion actual
    }
    if (matches) {
      if (!(key in ctx)) ctx[key] = false;
      return alignBlock(node.body, html, pos, ctx);
    }
    // clave truthy: no renderizar el cuerpo invertido
    if (!(key in ctx)) ctx[key] = true;
    return pos;
  }

  // Seccion normal #
  // 1) decidir si el cuerpo aparece en esta posicion
  let appears = false;
  if (leadingAnchor) {
    const found = findLiteral(html, pos, leadingAnchor);
    appears = !!(found && found.index <= pos + 200);
  }
  if (process.env.DEBUG_ALIGN) diag(`SEC #${key} pos=${pos} appears=${appears} isArray=${isArray} isObject=${isObject} leading="${(leadingAnchor || '').slice(0, 40).replace(/\n/g, '\\n')}"`);

  if (!appears) {
    // falsy / vacio
    if (isArray) { if (!(key in ctx)) ctx[key] = []; }
    else if (isObject) { /* no seteamos nada */ }
    else { if (!(key in ctx)) ctx[key] = false; }
    return pos;
  }

  if (isArray) {
    const arr = [];
    let safety = 0;
    while (safety++ < 500) {
      // condicion de continuacion: el ancla inicial encaja aqui
      const found = findLiteral(html, pos, leadingAnchor);
      if (!found || found.index > pos + 200) break;
      const item = {};
      pos = alignBlock(node.body, html, pos, item);
      arr.push(item);
    }
    ctx[key] = arr;
    return pos;
  }

  if (isObject) {
    const sub = {};
    pos = alignBlock(node.body, html, pos, sub);
    ctx[key] = sub;
    return pos;
  }

  // bool / escalar condicional truthy
  pos = alignBlock(node.body, html, pos, ctx);
  if (!(key in ctx) || ctx[key] === undefined) ctx[key] = true;
  return pos;
}

/* =========================================================================
 * 6. VALIDACION: re-render + diff (tolerante a whitespace)
 * ========================================================================= */

function normalizeWs(s) { return s.replace(/\s+/g, ' ').trim(); }

function renderWithPartials(data) {
  const template = fs.readFileSync(PATHS.mustache, 'utf8');
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
  // Mustache.php escapa con htmlspecialchars(ENT_COMPAT): & < > " (NO '/' ni comilla simple).
  // mustache.js por defecto escapa ademas / ' ` = -> lo igualamos a PHP.
  Mustache.escape = (s) => String(s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  return Mustache.render(template, data, partials);
}

function firstDiffIndex(a, b) {
  const n = Math.min(a.length, b.length);
  for (let i = 0; i < n; i++) if (a[i] !== b[i]) return i;
  return n;
}

function validate(data) {
  const rendered = renderWithPartials(data);
  const ref = fs.readFileSync(PATHS.referenceHtml, 'utf8');
  const a = normalizeWs(rendered);
  const b = normalizeWs(ref);
  if (a === b) return { ok: true };
  const di = firstDiffIndex(a, b);
  return {
    ok: false,
    renderedLen: a.length,
    refLen: b.length,
    diffAt: di,
    renderedCtx: a.slice(Math.max(0, di - 80), di + 80),
    refCtx: b.slice(Math.max(0, di - 80), di + 80),
  };
}

/* =========================================================================
 * 7. MAIN
 * ========================================================================= */

function main() {
  const tplSrc = fs.readFileSync(PATHS.mustache, 'utf8');
  const htmlSrc = fs.readFileSync(PATHS.referenceHtml, 'utf8');

  let tokens = tokenize(tplSrc);
  tokens = inlinePartials(tokens);
  const ast = buildAst(tokens);

  const data = {};
  alignBlock(ast.body, htmlSrc, 0, data);

  fs.writeFileSync(PATHS.dataJson, JSON.stringify(data, null, 2), 'utf8');

  console.log('=== data.json generado ===');
  console.log(`Campos escalares: ${Object.keys(data).filter(k => !Array.isArray(data[k]) && typeof data[k] !== 'object').length}`);
  for (const k of Object.keys(data)) {
    if (Array.isArray(data[k])) console.log(`  array ${k}: ${data[k].length} item(s)`);
  }
  console.log('\n=== Diagnosticos del alineador ===');
  console.log(DIAG.log.length ? DIAG.log.join('\n') : '(sin advertencias)');

  console.log('\n=== Validacion (re-render vs reserve.html) ===');
  const v = validate(data);
  if (v.ok) {
    console.log('OK: el render con data.json coincide con reserve.html (diff vacio tras normalizar whitespace).');
  } else {
    console.log('DIFF detectado en caracter', v.diffAt, `(render ${v.renderedLen} vs ref ${v.refLen})`);
    console.log('--- renderizado ---\n' + v.renderedCtx);
    console.log('--- referencia   ---\n' + v.refCtx);
  }
}

main();
