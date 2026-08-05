/**
 * Mockups visuales de clientes de email (Gmail, Outlook).
 * Envuelve el HTML del email con el chrome del cliente.
 */

function buildMockupContext({ smtpEnv = {}, data = {} } = {}) {
  const senderEmail = smtpEnv.user || 'noreply@solocruceros.com';
  const senderName = data.siteName || 'SoloCruceros';
  const subject = smtpEnv.subject || 'TEST - Email SoloCruceros';
  const toName = data.nameClient || 'Destinatario';
  const toEmail = smtpEnv.to || 'destinatario@example.com';
  const dateStr = data.dateBudget || new Date().toLocaleDateString('es-ES', {
    day: '2-digit', month: 'short', year: 'numeric',
  });
  const timeStr = new Date().toLocaleTimeString('es-ES', {
    hour: '2-digit', minute: '2-digit',
  });
  return { senderEmail, senderName, subject, toName, toEmail, dateStr, timeStr };
}

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Extrae body + <style> del head para incrustar en el mockup
 * sin anidar documentos HTML completos.
 */
function extractEmailBody(html) {
  const headMatch = html.match(/<head[^>]*>([\s\S]*?)<\/head>/i);
  const headContent = headMatch ? headMatch[1] : '';

  const headKeep = [];
  const styleRe = /<style[^>]*>[\s\S]*?<\/style>/gi;
  let m;
  while ((m = styleRe.exec(headContent)) !== null) headKeep.push(m[0]);

  // Comentarios condicionales MSO del head (si los hay)
  const msoRe = /<!--\[if[\s\S]*?<!\[endif\]-->/gi;
  while ((m = msoRe.exec(headContent)) !== null) headKeep.push(m[0]);

  const bodyOpen = html.match(/<body([^>]*)>/i);
  let rawBodyAttrs = '';
  let bodyContent;
  if (bodyOpen) {
    rawBodyAttrs = bodyOpen[1] || '';
    const afterBody = html.slice(bodyOpen.index + bodyOpen[0].length);
    bodyContent = afterBody
      .replace(/<\/body>/gi, '')
      .replace(/<\/html>/gi, '')
      .replace(/\s+$/, '');
  } else {
    bodyContent = html;
  }

  const keep = [];
  const styleM = rawBodyAttrs.match(/\sstyle\s*=\s*(["'])([\s\S]*?)\1/i);
  if (styleM) keep.push('style=' + styleM[1] + styleM[2] + styleM[1]);
  const bgM = rawBodyAttrs.match(/\sbgcolor\s*=\s*(["']?)([^"' >]+)\1/i);
  if (bgM) keep.push('bgcolor="' + bgM[2] + '"');
  const bgImgM = rawBodyAttrs.match(/\sbackground\s*=\s*(["']?)([^"' >]+)\1/i);
  if (bgImgM) keep.push('background="' + bgImgM[2] + '"');

  return {
    styles: headKeep.join('\n'),
    bodyAttrs: keep.length ? ' ' + keep.join(' ') : '',
    bodyContent,
  };
}

function gmailMockup(emailHtml, ctx) {
  const { senderName, senderEmail, subject, toName, toEmail, dateStr, timeStr } = ctx;
  const initial = (senderName || '?').trim().charAt(0).toUpperCase();

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Gmail · ${esc(subject)}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: 'Google Sans', Roboto, -apple-system, Arial, sans-serif;
    background: #f6f8fc;
    color: #202124;
    display: flex;
    flex-direction: column;
    min-height: 100vh;
  }
  .gmail-topbar {
    display: flex; align-items: center; gap: 16px;
    padding: 8px 16px; background: #fff;
    border-bottom: 1px solid #e0e0e0; flex: 0 0 auto;
  }
  .gmail-burger {
    width: 40px; height: 40px; display: grid; place-items: center;
    color: #5f6368; border-radius: 50%; cursor: pointer;
  }
  .gmail-burger:hover { background: #f1f3f4; }
  .gmail-logo {
    display: flex; align-items: center; gap: 6px;
    font-size: 22px; color: #5f6368; padding: 6px 8px;
  }
  .gmail-logo b { color: #4285f4; font-weight: 500; }
  .gmail-logo .red { color: #ea4335; }
  .gmail-logo .yel { color: #fbbc04; }
  .gmail-logo .grn { color: #34a853; }
  .gmail-search { flex: 1; max-width: 720px; position: relative; }
  .gmail-search input {
    width: 100%; height: 46px; border-radius: 24px;
    border: 1px solid #dadce0; background: #f1f3f4;
    padding: 0 60px 0 56px; font-size: 16px; outline: none; color: #202124;
  }
  .gmail-search input:focus { background: #fff; box-shadow: 0 1px 6px rgba(32,33,36,.18); }
  .gmail-search .ico-l {
    position: absolute; left: 18px; top: 50%; transform: translateY(-50%);
    color: #5f6368; width: 24px; height: 24px;
  }
  .gmail-actions { display: flex; align-items: center; gap: 6px; margin-left: auto; }
  .gmail-icon-btn {
    width: 40px; height: 40px; border-radius: 50%;
    display: grid; place-items: center; color: #5f6368; cursor: pointer;
  }
  .gmail-icon-btn:hover { background: #f1f3f4; }
  .gmail-avatar {
    width: 32px; height: 32px; border-radius: 50%;
    background: linear-gradient(135deg, #db4437, #fbbc04);
    color: #fff; font-weight: 600; font-size: 14px;
    display: grid; place-items: center; margin-left: 8px; cursor: pointer;
  }
  .gmail-layout { display: flex; flex: 1 1 auto; min-height: 0; }
  .gmail-side {
    flex: 0 0 256px; padding: 8px 0 8px 8px; overflow-y: auto;
  }
  .gmail-compose {
    display: inline-flex; align-items: center; gap: 12px;
    background: #c2e7ff; color: #001d35;
    padding: 0 24px 0 16px; height: 56px; border-radius: 16px;
    box-shadow: 0 1px 3px rgba(0,0,0,.1);
    font-weight: 500; font-size: 14px; margin-bottom: 8px; cursor: pointer;
  }
  .gmail-side ul { list-style: none; }
  .gmail-side li {
    display: flex; align-items: center; gap: 16px;
    padding: 0 26px 0 24px; height: 32px; color: #202124;
    font-size: 14px; border-radius: 0 24px 24px 0;
    margin-right: 8px; cursor: pointer;
  }
  .gmail-side li:hover { background: #eaecef; }
  .gmail-side li.active { background: #d3e3fd; color: #001d35; font-weight: 600; }
  .gmail-side li .ico { color: #5f6368; width: 20px; height: 20px; }
  .gmail-side li.active .ico { color: #001d35; }
  .gmail-side li .badge { margin-left: auto; font-size: 12px; color: #5f6368; }
  .gmail-main {
    flex: 1 1 auto; background: #fff; overflow: hidden;
    display: flex; flex-direction: column; min-width: 0;
  }
  .gmail-toolbar2 {
    flex: 0 0 auto; display: flex; align-items: center; gap: 4px;
    padding: 8px 12px; border-bottom: 1px solid #f0f0f0;
    color: #5f6368; font-size: 13px;
  }
  .gmail-toolbar2 .tb-btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 6px 12px; border-radius: 4px; cursor: pointer; color: #5f6368;
  }
  .gmail-toolbar2 .tb-btn:hover { background: #f1f3f4; }
  .gmail-toolbar2 .ico { width: 18px; height: 18px; }
  .gmail-toolbar2 .spacer { flex: 1; }
  .gmail-msg { flex: 1 1 auto; overflow: auto; padding: 0; background: #fff; }
  .gmail-msg-subject {
    font-size: 22px; font-weight: 400; color: #202124;
    padding: 16px 24px 8px;
  }
  .gmail-msg-head {
    display: flex; align-items: flex-start; gap: 12px;
    padding: 8px 24px 16px; border-bottom: 1px solid #f0f0f0;
  }
  .gmail-from-avatar {
    width: 40px; height: 40px; border-radius: 50%;
    background: #db4437; color: #fff; font-weight: 600; font-size: 18px;
    display: grid; place-items: center; flex: 0 0 40px;
  }
  .gmail-from-info { flex: 1; min-width: 0; }
  .gmail-from-name { font-size: 15px; color: #202124; font-weight: 500; }
  .gmail-from-name .email { color: #5f6368; font-weight: 400; margin-left: 6px; font-size: 14px; }
  .gmail-to { font-size: 13px; color: #5f6368; margin-top: 2px; }
  .gmail-head-actions { display: flex; gap: 4px; color: #5f6368; align-items: center; }
  .gmail-head-actions .ico-btn {
    width: 32px; height: 32px; border-radius: 50%;
    display: grid; place-items: center; cursor: pointer;
  }
  .gmail-head-actions .ico-btn:hover { background: #f1f3f4; }
  .gmail-date { font-size: 12px; color: #5f6368; padding: 8px 0 0; white-space: nowrap; }
  .gmail-body { padding: 16px 24px 48px; overflow: auto; }
  @media (max-width: 768px) {
    .gmail-side { display: none; }
    .gmail-search { max-width: none; }
  }
</style>
</head>
<body>
  <div class="gmail-topbar">
    <div class="gmail-burger" title="Menú">
      <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z"/></svg>
    </div>
    <div class="gmail-logo">
      <svg width="40" height="40" viewBox="0 0 48 48">
        <path fill="#4285f4" d="M45.16 6H2.84A2.84 2.84 0 0 0 0 8.84v30.32A2.84 2.84 0 0 0 2.84 42h42.32A2.84 2.84 0 0 0 48 39.16V8.84A2.84 2.84 0 0 0 45.16 6z"/>
        <path fill="#fff" d="M24 27.5l-21.16-16v-2.66A2.84 2.84 0 0 1 5.68 6h36.64a2.84 2.84 0 0 1 2.84 2.84v2.66L24 27.5z"/>
        <path fill="#ea4335" d="M0 12.34L24 30.66l24-18.32"/>
        <path fill="#34a853" d="M0 12.34v23.82"/>
        <path fill="#fbbc04" d="M48 12.34v23.82L24 30.66z"/>
      </svg>
      <span><b>G</b><span class="red">o</span><span class="yel">o</span><b>g</b><span class="red">l</span><span class="grn">e</span></span>
    </div>
    <div class="gmail-search">
      <svg class="ico-l" viewBox="0 0 24 24" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14z"/></svg>
      <input type="text" placeholder="Buscar en el correo" value="${esc(subject)}" readonly>
    </div>
    <div class="gmail-actions">
      <div class="gmail-icon-btn" title="Configuración">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor"><path d="M19.14 12.94a7.07 7.07 0 0 0 0-1.88l2.03-1.58-2-3.46-2.4 1a7 7 0 0 0-1.62-.94l-.36-2.54h-4l-.36 2.54a7 7 0 0 0-1.62.94l-2.4-1-2 3.46L4.86 11.06a7.07 7.07 0 0 0 0 1.88l-2.03 1.58 2 3.46 2.4-1a7 7 0 0 0 1.62.94l.36 2.54h4l.36-2.54a7 7 0 0 0 1.62-.94l2.4 1 2-3.46zM12 15a3 3 0 1 1 3-3 3 3 0 0 1-3 3z"/></svg>
      </div>
      <div class="gmail-avatar">Y</div>
    </div>
  </div>

  <div class="gmail-layout">
    <aside class="gmail-side">
      <div class="gmail-compose">
        <svg width="24" height="24" viewBox="0 0 24 24" fill="currentColor"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a.996.996 0 0 0 0-1.41l-2.34-2.34a.996.996 0 0 0-1.41 0l-1.83 1.83 3.75 3.75 1.83-1.83z"/></svg>
        Redactar
      </div>
      <ul>
        <li class="active">
          <svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm-1 14H6V8l6 4 6-4z"/></svg>
          Entrada <span class="badge">1</span>
        </li>
        <li><svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg> Destacados</li>
        <li><svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z"/></svg> Enviados</li>
        <li><svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg> Borradores</li>
      </ul>
    </aside>

    <main class="gmail-main">
      <div class="gmail-toolbar2">
        <div class="tb-btn"><svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z"/></svg></div>
        <div class="tb-btn"><svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg></div>
        <div class="spacer"></div>
        <span class="count">1 de 1</span>
      </div>

      <div class="gmail-msg">
        <div class="gmail-msg-subject">${esc(subject)}</div>
        <div class="gmail-msg-head">
          <div class="gmail-from-avatar">${esc(initial)}</div>
          <div class="gmail-from-info">
            <div class="gmail-from-name">${esc(senderName)} <span class="email">&lt;${esc(senderEmail)}&gt;</span></div>
            <div class="gmail-to">para ${esc(toName)} &lt;${esc(toEmail)}&gt;</div>
          </div>
          <div class="gmail-head-actions">
            <div class="gmail-date">${esc(dateStr)}, ${esc(timeStr)}</div>
            <div class="ico-btn" title="Responder">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M10 9V5l-7 7 7 7v-4.1c5 0 8.5 1.6 11 5.1-1-5-4-10-11-11z"/></svg>
            </div>
          </div>
        </div>
        <div class="gmail-body">
          ${emailHtml}
        </div>
      </div>
    </main>
  </div>
</body>
</html>`;
}

function outlookMockup(emailHtml, ctx) {
  const { senderName, senderEmail, subject, toName, toEmail, dateStr, timeStr } = ctx;
  const initial = (senderName || '?').trim().charAt(0).toUpperCase();

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Outlook · ${esc(subject)}</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  html, body { height: 100%; }
  body {
    font-family: 'Segoe UI', -apple-system, Roboto, Arial, sans-serif;
    background: #faf9f8; color: #323130;
    display: flex; flex-direction: column; min-height: 100vh;
  }
  .out-topbar {
    display: flex; align-items: center; gap: 16px;
    padding: 0 16px; background: #106ebe; color: #fff;
    height: 48px; flex: 0 0 auto;
  }
  .out-logo { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 16px; }
  .out-new {
    display: inline-flex; align-items: center; gap: 8px;
    background: #106ebe; border: 1px solid #fff; color: #fff;
    padding: 6px 14px; font-size: 13px; border-radius: 2px; cursor: pointer;
  }
  .out-new:hover { background: #0a5d9c; }
  .out-search { flex: 1; max-width: 480px; position: relative; margin-left: 8px; }
  .out-search input {
    width: 100%; height: 32px; border: 0;
    background: rgba(255,255,255,.18); color: #fff;
    padding: 0 12px 0 36px; font-size: 13px; outline: none; border-radius: 2px;
  }
  .out-search input::placeholder { color: rgba(255,255,255,.8); }
  .out-search input:focus { background: #fff; color: #323130; }
  .out-search .ico {
    position: absolute; left: 10px; top: 50%; transform: translateY(-50%);
    color: rgba(255,255,255,.9); width: 16px; height: 16px;
  }
  .out-top-spacer { flex: 1; }
  .out-top-icon {
    width: 36px; height: 36px; display: grid; place-items: center;
    color: #fff; cursor: pointer; border-radius: 2px;
  }
  .out-top-icon:hover { background: rgba(255,255,255,.15); }
  .out-avatar {
    width: 32px; height: 32px; border-radius: 50%;
    background: #b4009e; color: #fff; font-weight: 600; font-size: 14px;
    display: grid; place-items: center; margin-left: 8px; cursor: pointer;
  }
  .out-layout { display: flex; flex: 1 1 auto; min-height: 0; }
  .out-side {
    flex: 0 0 220px; background: #faf9f8; padding: 12px 0;
    border-right: 1px solid #edebe9; overflow-y: auto;
  }
  .out-side .nav-item {
    display: flex; align-items: center; gap: 12px;
    padding: 0 16px; height: 32px; color: #323130;
    font-size: 13px; cursor: pointer; border-left: 2px solid transparent;
  }
  .out-side .nav-item:hover { background: #f3f2f1; }
  .out-side .nav-item.active {
    background: #eaeaea; border-left-color: #106ebe; font-weight: 600;
  }
  .out-side .nav-item .ico { color: #605e5c; width: 18px; height: 18px; }
  .out-side .nav-item.active .ico { color: #106ebe; }
  .out-side .nav-item .badge { margin-left: auto; color: #605e5c; font-size: 12px; }
  .out-side .section-title {
    padding: 12px 16px 6px; color: #605e5c;
    font-size: 12px; text-transform: uppercase; letter-spacing: .5px;
  }
  .out-main {
    flex: 1 1 auto; background: #fff;
    display: flex; flex-direction: column; min-width: 0;
  }
  .out-subject {
    flex: 0 0 auto; padding: 16px 24px;
    font-size: 21px; font-weight: 400; color: #201f1e;
    border-bottom: 1px solid #edebe9;
    display: flex; align-items: center; gap: 12px;
  }
  .out-subject .ico-star { color: #605e5c; cursor: pointer; width: 20px; height: 20px; }
  .out-head {
    flex: 0 0 auto; display: flex; gap: 12px;
    padding: 16px 24px; border-bottom: 1px solid #edebe9;
  }
  .out-avatar-from {
    width: 40px; height: 40px; border-radius: 50%;
    background: #106ebe; color: #fff; font-weight: 600; font-size: 16px;
    display: grid; place-items: center; flex: 0 0 40px;
  }
  .out-head-info { flex: 1; min-width: 0; }
  .out-from { font-size: 14px; color: #201f1e; }
  .out-from .email { color: #605e5c; margin-left: 6px; }
  .out-to { font-size: 12px; color: #605e5c; margin-top: 2px; }
  .out-head-right { display: flex; flex-direction: column; align-items: flex-end; gap: 8px; }
  .out-date { font-size: 12px; color: #605e5c; white-space: nowrap; }
  .out-actions { display: flex; gap: 4px; }
  .out-actions .btn {
    display: inline-flex; align-items: center; gap: 6px;
    padding: 4px 10px; font-size: 13px; color: #323130;
    border-radius: 2px; cursor: pointer;
  }
  .out-actions .btn:hover { background: #f3f2f1; }
  .out-actions .btn .ico { width: 14px; height: 14px; color: #106ebe; }
  .out-body { flex: 1 1 auto; overflow: auto; padding: 24px; background: #fff; }
  @media (max-width: 768px) {
    .out-side { display: none; }
    .out-search { max-width: none; }
  }
</style>
</head>
<body>
  <div class="out-topbar">
    <div class="out-logo">
      <svg width="28" height="28" viewBox="0 0 32 32">
        <rect width="32" height="32" rx="4" fill="#0a5d9c"/>
        <text x="16" y="22" font-family="Segoe UI, Arial" font-size="18" font-weight="700" fill="#fff" text-anchor="middle">O</text>
      </svg>
      Outlook
    </div>
    <button class="out-new">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6z"/></svg>
      Nuevo mensaje
    </button>
    <div class="out-search">
      <svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M15.5 14h-.79l-.28-.27a6.5 6.5 0 1 0-.7.7l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0A4.5 4.5 0 1 1 14 9.5 4.5 4.5 0 0 1 9.5 14z"/></svg>
      <input type="text" placeholder="Buscar en Outlook" value="${esc(subject)}" readonly>
    </div>
    <div class="out-top-spacer"></div>
    <div class="out-top-icon" title="Configuración">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor"><path d="M19.14 12.94a7.07 7.07 0 0 0 0-1.88l2.03-1.58-2-3.46-2.4 1a7 7 0 0 0-1.62-.94l-.36-2.54h-4l-.36 2.54a7 7 0 0 0-1.62.94l-2.4-1-2 3.46L4.86 11.06a7.07 7.07 0 0 0 0 1.88l-2.03 1.58 2 3.46 2.4-1a7 7 0 0 0 1.62.94l.36 2.54h4l.36-2.54a7 7 0 0 0 1.62-.94l2.4 1 2-3.46zM12 15a3 3 0 1 1 3-3 3 3 0 0 1-3 3z"/></svg>
    </div>
    <div class="out-avatar">Y</div>
  </div>

  <div class="out-layout">
    <aside class="out-side">
      <div class="nav-item active">
        <svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm-1 14H6V8l6 4 6-4z"/></svg>
        Bandeja de entrada <span class="badge">1</span>
      </div>
      <div class="nav-item">
        <svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>
        Marcados
      </div>
      <div class="section-title">Carpetas</div>
      <div class="nav-item">
        <svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M10 9V5l-7 7 7 7v-4.1c5 0 8.5 1.6 11 5.1-1-5 4-10 11-11z"/></svg>
        Enviados
      </div>
      <div class="nav-item">
        <svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/></svg>
        Borradores
      </div>
      <div class="nav-item">
        <svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z"/></svg>
        Elementos eliminados
      </div>
    </aside>

    <main class="out-main">
      <div class="out-subject">
        ${esc(subject)}
        <svg class="ico-star" viewBox="0 0 24 24" fill="currentColor"><path d="M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z"/></svg>
      </div>
      <div class="out-head">
        <div class="out-avatar-from">${esc(initial)}</div>
        <div class="out-head-info">
          <div class="out-from">${esc(senderName)} <span class="email">&lt;${esc(senderEmail)}&gt;</span></div>
          <div class="out-to">Para: ${esc(toName)} &lt;${esc(toEmail)}&gt;</div>
        </div>
        <div class="out-head-right">
          <div class="out-date">${esc(dateStr)} ${esc(timeStr)}</div>
          <div class="out-actions">
            <div class="btn"><svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M10 9V5l-7 7 7 7v-4.1c5 0 8.5 1.6 11 5.1-1-5-4-10-11-11z"/></svg> Responder</div>
            <div class="btn"><svg class="ico" viewBox="0 0 24 24" fill="currentColor"><path d="M14 9V5l7 7-7 7v-4.1c-5 0-8.5 1.6-11 5.1 1-5 4-10 11-11z"/></svg> Reenviar</div>
          </div>
        </div>
      </div>
      <div class="out-body">
        ${emailHtml}
      </div>
    </main>
  </div>
</body>
</html>`;
}

const CLIENT_MOCKUP = {
  'gmail-web': 'gmail',
  'gmail-android': 'gmail',
  'gmail-ios': 'gmail',
  'outlook-windows': 'outlook',
  'outlook-web': 'outlook',
  'outlook-mac': 'outlook',
  'apple-mail': null,
  'yahoo-mail': null,
  'original': null,
};

function wrapInMockup(client, emailHtml, ctx) {
  const kind = CLIENT_MOCKUP[client];
  if (kind == null) return emailHtml;

  const { styles, bodyAttrs, bodyContent } = extractEmailBody(emailHtml);

  // Si filterForClient ya envolvió en .email-body-wrapper, no duplicar
  let wrappedEmail;
  if (bodyContent.includes('email-body-wrapper')) {
    wrappedEmail = (styles ? styles + '\n' : '') + bodyContent;
  } else {
    wrappedEmail =
      (styles ? styles + '\n' : '') +
      '<div class="email-body-wrapper"' + bodyAttrs + '>' +
      bodyContent +
      '</div>';
  }

  if (kind === 'gmail') return gmailMockup(wrappedEmail, ctx);
  if (kind === 'outlook') return outlookMockup(wrappedEmail, ctx);
  return emailHtml;
}

function hasMockup(client) {
  return CLIENT_MOCKUP[client] != null;
}

export {
  gmailMockup,
  outlookMockup,
  wrapInMockup,
  hasMockup,
  buildMockupContext,
  extractEmailBody,
  CLIENT_MOCKUP,
};
