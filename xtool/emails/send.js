import nodemailer from 'nodemailer';

const ENV = {
  host:     process.env.SMTP_HOST || 'smtp.gmail.com',
  port:     Number(process.env.SMTP_PORT) || 465,
  user:     process.env.EMAIL_USER,
  pass:     process.env.EMAIL_APP_PASSWORD,
  to:       process.env.EMAIL_TO,
  cc:       process.env.EMAIL_CC,
  subject:  process.env.EMAIL_SUBJECT || 'TEST - Email SoloCruceros',
};

function checkConfig() {
  const missing = [];
  if (!ENV.user) missing.push('EMAIL_USER');
  if (!ENV.pass) missing.push('EMAIL_APP_PASSWORD');
  if (!ENV.to)   missing.push('EMAIL_TO');
  if (missing.length) {
    const err = new Error('Faltan credenciales en .env: ' + missing.join(', '));
    err.code = 'NO_CONFIG';
    throw err;
  }
}

function makeTransport() {
  return nodemailer.createTransport({
    host: ENV.host,
    port: ENV.port,
    secure: ENV.port === 465,
    auth: { user: ENV.user, pass: ENV.pass.trim() },
  });
}

function splitList(v) {
  if (!v) return undefined;
  const arr = String(v).split(/[,;\n\r]+/).map(s => s.trim()).filter(Boolean);
  return arr.length ? arr.join(', ') : undefined;
}

export async function sendTestHtml({ html, subject, to, cc } = {}) {
  checkConfig();
  const transport = makeTransport();
  const subjectFinal = subject || ENV.subject;
  const toFinal = to || ENV.to;
  const ccFinal = splitList(cc !== undefined ? cc : ENV.cc);

  const info = await transport.sendMail({
    from: ENV.user,
    to: toFinal,
    cc: ccFinal,
    subject: subjectFinal,
    html: html || '<p>(email vacio)</p>',
  });
  return {
    messageId: info.messageId,
    to: toFinal,
    cc: ccFinal || '(sin CC)',
    subject: subjectFinal,
  };
}

export { ENV as SMTP_ENV };
