/**
 * Simulación realista de CSS por cliente de email (caniemail-inspired).
 *
 * Pipeline:
 *  1. Filtrar/reescribir propiedades no soportadas en <style> e inline
 *  2. Inyectar CSS "motor" del cliente (forzar fallbacks reales)
 *
 * NO usa juice: el template tiene HTML mal formado y lo corrompe.
 *
 * Clientes: gmail-web, gmail-android, gmail-ios,
 *           outlook-windows, outlook-web, outlook-mac,
 *           apple-mail, yahoo-mail, original
 */

// ============================================================================
// 1. REGLAS POR CLIENTE
// ============================================================================

/**
 * Propiedades CSS que se ELIMINAN del todo (el cliente las ignora).
 * No incluye `display` (se maneja con valores + reescritura).
 */
const UNSUPPORTED_PROPERTIES = {
  'gmail-web': [
    'position', 'z-index', 'float',
    'transform', 'transition', 'animation',
    'box-shadow', 'text-shadow', 'filter', 'backdrop-filter',
    'opacity', 'object-fit', 'object-position',
    'gap', 'row-gap', 'column-gap',
    'flex', 'flex-direction', 'flex-wrap', 'flex-flow',
    'flex-grow', 'flex-shrink', 'flex-basis',
    'justify-content', 'align-items', 'align-content', 'align-self', 'order',
    'grid', 'grid-template', 'grid-template-columns', 'grid-template-rows',
    'grid-gap', 'grid-column', 'grid-row', 'place-items', 'place-content',
    'min-width', 'min-height',
  ],
  'gmail-android': [
    'position', 'z-index', 'float',
    'transform', 'transition', 'animation',
    'box-shadow', 'text-shadow', 'filter', 'backdrop-filter', 'opacity',
    'gap', 'row-gap', 'column-gap',
    'flex', 'flex-direction', 'flex-wrap', 'flex-flow',
    'flex-grow', 'flex-shrink', 'flex-basis',
    'justify-content', 'align-items', 'align-content', 'align-self', 'order',
    'grid', 'grid-template', 'grid-template-columns', 'grid-template-rows',
    'grid-gap', 'grid-column', 'grid-row',
  ],
  'gmail-ios': [
    'position', 'z-index', 'float',
    'transform', 'transition', 'animation',
    'box-shadow', 'text-shadow', 'filter', 'backdrop-filter', 'opacity',
    'gap', 'row-gap', 'column-gap',
    'flex', 'flex-direction', 'flex-wrap', 'flex-flow',
    'flex-grow', 'flex-shrink', 'flex-basis',
    'justify-content', 'align-items', 'align-content', 'align-self', 'order',
    'grid', 'grid-template', 'grid-template-columns', 'grid-template-rows',
  ],
  // Outlook desktop = motor Word: el peor caso
  'outlook-windows': [
    'position', 'z-index', 'float',
    'transform', 'transition', 'animation',
    'box-shadow', 'text-shadow', 'filter', 'backdrop-filter', 'opacity',
    'border-radius', 'border-image',
    'background-size', 'background-clip', 'background-origin',
    'background-attachment', 'object-fit',
    'max-width', 'min-width', 'min-height', 'max-height',
    'gap', 'row-gap', 'column-gap',
    'flex', 'flex-direction', 'flex-wrap', 'flex-flow',
    'flex-grow', 'flex-shrink', 'flex-basis',
    'justify-content', 'align-items', 'align-content', 'align-self', 'order',
    'grid', 'grid-template', 'grid-template-columns', 'grid-template-rows',
    'grid-gap', 'grid-column', 'grid-row', 'place-items', 'place-content',
    'overflow', 'overflow-x', 'overflow-y',
    'white-space', 'word-break', 'text-overflow',
    'outline', 'box-sizing',
  ],
  'outlook-web': [
    'position', 'z-index',
    'transform', 'transition', 'animation',
    'filter', 'backdrop-filter',
    'gap', 'row-gap', 'column-gap',
    'flex', 'flex-direction', 'flex-wrap', 'flex-flow',
    'flex-grow', 'flex-shrink', 'flex-basis',
    'justify-content', 'align-items', 'align-content', 'align-self', 'order',
    'grid', 'grid-template', 'grid-template-columns', 'grid-template-rows',
  ],
  'outlook-mac': [
    'position', 'z-index',
    'transform', 'transition', 'animation',
    'filter', 'backdrop-filter',
    'gap',
    'flex', 'flex-direction', 'flex-wrap',
    'justify-content', 'align-items',
    'grid', 'grid-template-columns', 'grid-template-rows',
  ],
  'apple-mail': [
    // WebKit: casi todo OK; solo rarezas menores
  ],
  'yahoo-mail': [
    'position', 'z-index',
    'transform', 'transition', 'animation',
    'filter', 'backdrop-filter',
    'gap',
    'flex', 'flex-direction', 'flex-wrap',
    'justify-content', 'align-items',
    'grid', 'grid-template-columns',
  ],
  'original': [],
};

/**
 * Valores de `display` no soportados → se reescriben a un fallback realista.
 * Gmail/Outlook ignoran flex/grid y el elemento cae a block (o el default del tag).
 */
const DISPLAY_REWRITE = {
  'gmail-web': {
    flex: 'block',
    'inline-flex': 'inline-block',
    grid: 'block',
    'inline-grid': 'inline-block',
    contents: 'block',
  },
  'gmail-android': {
    flex: 'block', 'inline-flex': 'inline-block',
    grid: 'block', 'inline-grid': 'inline-block', contents: 'block',
  },
  'gmail-ios': {
    flex: 'block', 'inline-flex': 'inline-block',
    grid: 'block', 'inline-grid': 'inline-block', contents: 'block',
  },
  'outlook-windows': {
    flex: 'block',
    'inline-flex': 'inline-block',
    grid: 'block',
    'inline-grid': 'inline-block',
    contents: 'block',
    // Word no entiende display:table* en divs; las tablas HTML sí funcionan
  },
  'outlook-web': {
    flex: 'block', 'inline-flex': 'inline-block',
    grid: 'block', 'inline-grid': 'inline-block',
  },
  'outlook-mac': {
    flex: 'block', 'inline-flex': 'inline-block',
    grid: 'block', 'inline-grid': 'inline-block',
  },
  'apple-mail': {},
  'yahoo-mail': {
    flex: 'block', 'inline-flex': 'inline-block',
    grid: 'block', 'inline-grid': 'inline-block',
  },
  'original': {},
};

const UNSUPPORTED_SELECTORS = {
  'gmail-web': [
    ':hover', ':active', ':focus', ':visited', ':focus-within',
    ':before', ':after', '::before', '::after',
    '::placeholder', ':nth-child', ':nth-of-type', ':not(',
  ],
  'gmail-android': [':hover', ':before', ':after', '::before', '::after'],
  'gmail-ios': [':hover', ':before', ':after', '::before', '::after'],
  'outlook-windows': [
    ':hover', ':active', ':focus', ':visited',
    ':before', ':after', '::before', '::after',
    ':nth-child', ':nth-of-type', ':not(',
    '>', '+', '~',
  ],
  'outlook-web': [':before', ':after', '::before', '::after'],
  'outlook-mac': [':before', ':after', '::before', '::after'],
  'apple-mail': [],
  'yahoo-mail': [':before', ':after', '::before', '::after'],
  'original': [],
};

/**
 * CSS extra inyectado al final del head para forzar el comportamiento del motor.
 * Simula lo que el cliente hace con CSS residual o atributos no filtrados.
 */
const ENGINE_CSS = {
  'gmail-web': `
/* Gmail engine sim — flex/grid no existen */
.email-body-wrapper [style*="display: flex"],
.email-body-wrapper [style*="display:flex"],
.email-body-wrapper [style*="display: grid"],
.email-body-wrapper [style*="display:grid"],
.email-body-wrapper [style*="display: inline-flex"],
.email-body-wrapper [style*="display:inline-flex"] {
  display: block !important;
}
/* Gmail no soporta gap ni flex-* residuales */
.email-body-wrapper * {
  gap: unset !important;
  row-gap: unset !important;
  column-gap: unset !important;
}
`,
  'gmail-android': `
.email-body-wrapper [style*="display: flex"],
.email-body-wrapper [style*="display:flex"],
.email-body-wrapper [style*="display: grid"],
.email-body-wrapper [style*="display:grid"] { display: block !important; }
`,
  'gmail-ios': `
.email-body-wrapper [style*="display: flex"],
.email-body-wrapper [style*="display:flex"],
.email-body-wrapper [style*="display: grid"],
.email-body-wrapper [style*="display:grid"] { display: block !important; }
`,
  'outlook-windows': `
/* Outlook Word engine sim */
.email-body-wrapper [style*="display: flex"],
.email-body-wrapper [style*="display:flex"],
.email-body-wrapper [style*="display: grid"],
.email-body-wrapper [style*="display:grid"],
.email-body-wrapper [style*="display: inline-flex"],
.email-body-wrapper [style*="display:inline-flex"] {
  display: block !important;
}
/* Word ignora border-radius */
.email-body-wrapper * {
  border-radius: 0 !important;
  box-shadow: none !important;
  max-width: none !important;
  gap: unset !important;
}
/* Fondos con gradientes se pierden: solo color sólido si hay */
.email-body-wrapper [style*="linear-gradient"],
.email-body-wrapper [style*="radial-gradient"] {
  background-image: none !important;
}
`,
  'outlook-web': `
.email-body-wrapper [style*="display: flex"],
.email-body-wrapper [style*="display:flex"],
.email-body-wrapper [style*="display: grid"],
.email-body-wrapper [style*="display:grid"] { display: block !important; }
`,
  'outlook-mac': `
.email-body-wrapper [style*="display: flex"],
.email-body-wrapper [style*="display:flex"],
.email-body-wrapper [style*="display: grid"],
.email-body-wrapper [style*="display:grid"] { display: block !important; }
`,
  'apple-mail': '',
  'yahoo-mail': `
.email-body-wrapper [style*="display: flex"],
.email-body-wrapper [style*="display:flex"],
.email-body-wrapper [style*="display: grid"],
.email-body-wrapper [style*="display:grid"] { display: block !important; }
`,
  'original': '',
};

// ============================================================================
// 2. PARSEO CSS
// ============================================================================

function extractStyles(html) {
  const styles = { inline: [], blocks: [] };
  const styleRegex = /<style[^>]*>([\s\S]*?)<\/style>/gi;
  let match;
  while ((match = styleRegex.exec(html)) !== null) {
    styles.blocks.push({
      fullMatch: match[0],
      content: match[1],
      start: match.index,
      end: match.index + match[0].length,
    });
  }
  // Solo style= de atributos HTML (no dentro de <style>)
  const inlineRegex = /\s+style=(["'])([\s\S]*?)\1/gi;
  while ((match = inlineRegex.exec(html)) !== null) {
    styles.inline.push({
      fullMatch: match[0],
      quote: match[1],
      content: match[2],
      start: match.index,
      end: match.index + match[0].length,
    });
  }
  return styles;
}

function parseCssRule(cssText) {
  const declarations = [];
  for (const part of cssText.split(';')) {
    const trimmed = part.trim();
    if (!trimmed) continue;
    const colonPos = trimmed.indexOf(':');
    if (colonPos === -1) continue;
    const property = trimmed.slice(0, colonPos).trim();
    const value = trimmed.slice(colonPos + 1).trim();
    if (property && value) declarations.push({ property, value });
  }
  return declarations;
}

function parseCssBlock(cssText) {
  const rules = [];
  let pos = 0;
  while (pos < cssText.length) {
    while (pos < cssText.length && /[\s\n\r\t]/.test(cssText[pos])) pos++;
    if (pos >= cssText.length) break;

    // Saltar @media / @keyframes / @font-face como bloques opacos
    if (cssText[pos] === '@') {
      const braceStart = cssText.indexOf('{', pos);
      if (braceStart === -1) break;
      let braceEnd = braceStart + 1;
      let depth = 1;
      while (braceEnd < cssText.length && depth > 0) {
        if (cssText[braceEnd] === '{') depth++;
        if (cssText[braceEnd] === '}') depth--;
        braceEnd++;
      }
      const atRule = cssText.slice(pos, braceStart).trim();
      const inner = cssText.slice(braceStart + 1, braceEnd - 1);
      rules.push({ selector: atRule, content: inner, isAtRule: true, start: pos, end: braceEnd });
      pos = braceEnd;
      continue;
    }

    const braceStart = cssText.indexOf('{', pos);
    if (braceStart === -1) break;
    const selector = cssText.slice(pos, braceStart).trim();
    let braceEnd = braceStart + 1;
    let depth = 1;
    while (braceEnd < cssText.length && depth > 0) {
      if (cssText[braceEnd] === '{') depth++;
      if (cssText[braceEnd] === '}') depth--;
      braceEnd++;
    }
    if (depth !== 0) break;
    const content = cssText.slice(braceStart + 1, braceEnd - 1).trim();
    rules.push({ selector, content, isAtRule: false, start: pos, end: braceEnd });
    pos = braceEnd;
  }
  return rules;
}

// ============================================================================
// 3. FILTRADO
// ============================================================================

function rewriteDeclaration({ property, value }, client) {
  const prop = property.toLowerCase();
  const unsupported = UNSUPPORTED_PROPERTIES[client] || [];
  if (unsupported.includes(prop)) return null;

  // Prefijos flex-/grid- ya cubiertos arriba; display se reescribe
  if (prop === 'display') {
    const displayValue = value.toLowerCase().split(/\s+/)[0];
    const rewrites = DISPLAY_REWRITE[client] || {};
    if (rewrites[displayValue]) {
      return { property, value: rewrites[displayValue] };
    }
  }

  // Gradientes en outlook-windows → quitar background-image
  if (client === 'outlook-windows' && (prop === 'background' || prop === 'background-image')) {
    if (/gradient\s*\(/i.test(value)) return null;
  }

  return { property, value };
}

function filterDeclarations(declarations, client) {
  const out = [];
  for (const decl of declarations) {
    const rewritten = rewriteDeclaration(decl, client);
    if (rewritten) out.push(rewritten);
  }
  return out;
}

function filterSelector(selector, client) {
  const unsupported = UNSUPPORTED_SELECTORS[client] || [];
  for (const pattern of unsupported) {
    if (selector.includes(pattern)) return false;
  }
  return true;
}

function filterCssBlock(cssText, client) {
  const rules = parseCssBlock(cssText);
  const filtered = [];

  for (const rule of rules) {
    if (rule.isAtRule) {
      // Outlook Windows: media queries se ignoran a menudo → descartar
      if (client === 'outlook-windows' && /^@media/i.test(rule.selector)) {
        continue;
      }
      // Recursivo sobre el interior de @media
      if (/^@media/i.test(rule.selector)) {
        const inner = filterCssBlock(rule.content, client);
        if (inner) filtered.push({ selector: rule.selector, content: '\n' + inner + '\n', isAtRule: true });
      } else {
        // @font-face, @keyframes: gmail/outlook los ignoran a menudo
        if (client === 'outlook-windows' || client.startsWith('gmail-')) {
          if (/^@(keyframes|font-face)/i.test(rule.selector)) continue;
        }
        filtered.push({ selector: rule.selector, content: rule.content, isAtRule: true });
      }
      continue;
    }

    if (!filterSelector(rule.selector, client)) continue;

    const declarations = parseCssRule(rule.content);
    const filteredDecls = filterDeclarations(declarations, client);
    if (filteredDecls.length > 0) {
      filtered.push({
        selector: rule.selector,
        content: filteredDecls.map(({ property, value }) => `${property}: ${value};`).join(' '),
        isAtRule: false,
      });
    }
  }

  return filtered.map((r) => {
    if (r.isAtRule) return `${r.selector} {${r.content}}`;
    return `${r.selector} { ${r.content} }`;
  }).join('\n');
}

function filterInlineStyle(cssText, client) {
  const declarations = parseCssRule(cssText);
  const filtered = filterDeclarations(declarations, client);
  return filtered.map(({ property, value }) => `${property}: ${value}`).join('; ');
}

/**
 * Inyecta el CSS del "motor" del cliente antes de </head>, o al inicio del doc.
 * Envuelve el body en .email-body-wrapper si aún no está (vista /render sin mockup).
 */
function injectEngineCss(html, client) {
  const engine = (ENGINE_CSS[client] || '').trim();
  if (!engine) return html;

  const tag = `<style data-email-engine="${client}">\n${engine}\n</style>`;

  if (/<\/head>/i.test(html)) {
    return html.replace(/<\/head>/i, tag + '\n</head>');
  }
  if (/<body[^>]*>/i.test(html)) {
    return html.replace(/<body([^>]*)>/i, `<body$1>\n${tag}`);
  }
  return tag + html;
}

/**
 * En /render/:client el email no pasa por mockup, así que no hay .email-body-wrapper.
 * Envolvemos el body para que el ENGINE_CSS aplique igual.
 */
function ensureBodyWrapper(html) {
  if (html.includes('email-body-wrapper')) return html;

  const bodyOpen = html.match(/<body([^>]*)>/i);
  if (!bodyOpen) return html;

  const openTag = bodyOpen[0];
  const attrs = bodyOpen[1] || '';
  const start = bodyOpen.index + openTag.length;
  const after = html.slice(start);

  // Quitar cierres finales del body para reinsertarlos fuera
  const bodyInner = after
    .replace(/<\/body>\s*<\/html>\s*$/i, '')
    .replace(/<\/body>\s*$/i, '')
    .replace(/<\/html>\s*$/i, '');

  // Conservar style/bgcolor del body en el wrapper
  const keep = [];
  const styleM = attrs.match(/\sstyle\s*=\s*(["'])([\s\S]*?)\1/i);
  if (styleM) keep.push('style=' + styleM[1] + styleM[2] + styleM[1]);
  const bgM = attrs.match(/\sbgcolor\s*=\s*(["']?)([^"' >]+)\1/i);
  if (bgM) keep.push('bgcolor="' + bgM[2] + '"');
  const wrapAttrs = keep.length ? ' ' + keep.join(' ') : '';

  return (
    html.slice(0, bodyOpen.index) +
    '<body>' +
    `<div class="email-body-wrapper"${wrapAttrs}>` +
    bodyInner +
    '</div></body></html>'
  );
}

// ============================================================================
// 4. API PRINCIPAL
// ============================================================================

/**
 * Filtra y simula el HTML según el cliente objetivo.
 * @param {string} html
 * @param {string} client
 * @returns {string}
 */
function filterForClient(html, client = 'original') {
  if (!UNSUPPORTED_PROPERTIES[client] && client !== 'original') {
    console.warn(`[email-client-filter] Cliente desconocido: ${client}`);
    client = 'original';
  }
  if (client === 'original') return html;

  let filteredHtml = html;

  // 1) Filtrar bloques <style> (de atrás hacia adelante)
  const styles = extractStyles(filteredHtml);
  for (let i = styles.blocks.length - 1; i >= 0; i--) {
    const block = styles.blocks[i];
    const filteredCss = filterCssBlock(block.content, client);
    const replacement = filteredCss ? `<style>${filteredCss}</style>` : '';
    filteredHtml =
      filteredHtml.slice(0, block.start) +
      replacement +
      filteredHtml.slice(block.end);
  }

  // 2) Filtrar inline styles (re-extraer tras modificar bloques)
  const updated = extractStyles(filteredHtml);
  for (let i = updated.inline.length - 1; i >= 0; i--) {
    const inline = updated.inline[i];
    // No tocar style= dentro de lo que ya es un <style> reescrito (no debería)
    const filteredStyle = filterInlineStyle(inline.content, client);
    const replacement = filteredStyle
      ? ` style=${inline.quote}${filteredStyle}${inline.quote}`
      : '';
    filteredHtml =
      filteredHtml.slice(0, inline.start) +
      replacement +
      filteredHtml.slice(inline.end);
  }

  // 3) Wrapper + CSS del motor del cliente
  filteredHtml = ensureBodyWrapper(filteredHtml);
  filteredHtml = injectEngineCss(filteredHtml, client);

  return filteredHtml;
}

function getSupportedClients() {
  return Object.keys(UNSUPPORTED_PROPERTIES).filter((c) => c !== 'original');
}

function getClientInfo(client) {
  return {
    client,
    unsupportedProperties: UNSUPPORTED_PROPERTIES[client] || [],
    unsupportedSelectors: UNSUPPORTED_SELECTORS[client] || [],
    displayRewrite: DISPLAY_REWRITE[client] || {},
    hasEngineCss: Boolean((ENGINE_CSS[client] || '').trim()),
  };
}

export {
  filterForClient,
  getSupportedClients,
  getClientInfo,
  extractStyles,
  filterCssBlock,
  filterInlineStyle,
  UNSUPPORTED_PROPERTIES,
  UNSUPPORTED_SELECTORS,
  DISPLAY_REWRITE,
  ENGINE_CSS,
};
