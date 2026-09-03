/* =========================================================================
 * Motor de render compatible con los "dynamic placeholders" de Odoo 18
 * (mail.render.mixin, modo inline_template).
 *
 * Sintaxis soportada en el preview:
 *   {{ path.to.field }}          -> lookup por puntos contra data.json
 *   {{ path, opcion=valor }}     -> opciones de Odoo (format_datetime, etc.):
 *                                    se resuelve el path y se ignora el resto
 *
 * Convenciones del preview:
 *   - data.json anidado: { "object": {...}, "ctx": {...}, ... }. Los lookups
 *     prueban la ruta exacta y, como fallback, con/sin el prefijo "object."
 *     (asi funcionan {{ object.name }} y {{ name }} con el mismo JSON).
 *   - Escapado HTML por defecto. Lista "_raw": ["ruta", ...] en data.json
 *     para insertar valores sin escapar (equivalente a {{{x}}} de Mustache).
 *   - null/false -> cadena vacia (como Odoo con campos vacios).
 *   - Variable sin datos -> el placeholder queda visible tal cual
 *     (facilita detectar qué falta antes de pegar en Odoo).
 * ========================================================================= */

const PLACEHOLDER_RE = /\{\{\s*([^{}]+?)\s*\}\}/g;

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// "  object.partner_id.name , format_datetime=%d " -> "object.partner_id.name"
function extractPath(expression) {
  const path = expression.split(',')[0].trim();
  // Odoo permite prefijos de layout p.ej. "t-out=" en algunos contextos: los limpiamos.
  return path.replace(/^[a-zA-Z_]+\s*=\s*/, '').trim();
}

function lookup(data, path) {
  const segments = path.split('.').map((s) => s.trim()).filter(Boolean);
  if (!segments.length) return undefined;

  const candidates = [segments];
  // Fallback con/sin prefijo "object" para soportar ambos estilos de naming
  if (segments[0] === 'object' && segments.length > 1) {
    candidates.push(segments.slice(1));
  } else {
    candidates.push(['object', ...segments]);
  }

  for (const segs of candidates) {
    let cur = data;
    let ok = true;
    for (const seg of segs) {
      if (cur == null || typeof cur !== 'object' || !(seg in cur)) {
        ok = false;
        break;
      }
      cur = cur[seg];
    }
    if (ok && cur !== undefined) return cur;
  }
  return undefined;
}

/**
 * Renderiza `template` (HTML con placeholders {{ }}) contra `data`.
 * @param {string} template
 * @param {object} data            datos anidados (object, ctx, ...)
 * @param {object} [opts]
 * @param {(path: string) => void} [opts.onUnresolved] callback por placeholder sin datos
 * @returns {string} HTML renderizado
 */
export function renderOdooInline(template, data, opts = {}) {
  const rawPaths = new Set(Array.isArray(data?._raw) ? data._raw : []);
  const unresolved = [];

  const out = template.replace(PLACEHOLDER_RE, (match, expression) => {
    const path = extractPath(expression);
    if (!path || path.startsWith('_')) return match; // _raw y _meta: internos

    const value = lookup(data, path);
    if (value === undefined) {
      unresolved.push(path);
      return match; // placeholder visible
    }
    if (value === null || value === false) return '';
    const str = String(value);
    return rawPaths.has(path) ? str : escapeHtml(str);
  });

  if (opts.onUnresolved) for (const p of unresolved) opts.onUnresolved(p);
  return out;
}

/** Lista los paths de placeholders que usa un template (sin renderizar). */
export function collectPlaceholderPaths(template) {
  const paths = new Set();
  for (const m of template.matchAll(PLACEHOLDER_RE)) {
    const path = extractPath(m[1]);
    if (path && !path.startsWith('_')) paths.add(path);
  }
  return [...paths];
}
