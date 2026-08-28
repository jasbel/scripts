import 'dotenv/config';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Raiz del directorio de templates "default" en el repo PHP.
// Ruta Linux por defecto; sobreescribible via .env (p.ej. en Windows):
//   SOLOCRUCEROS_TEMPLATES_DIR=C:\Users\Rene\projects\symfony-sites\...\templates\default
const TEMPLATES_DIR = process.env.SOLOCRUCEROS_TEMPLATES_DIR
  || '/home/asbel/projects/symfony-sites/sites/solocruceros.com/DDD/4.2MainModule/SoloCrucerosDomain.MainModule/DomainServices/resources/templates/default';

// Plantillas Odoo viven dentro de este repo (multiplataforma)
const ODOO_TEMPLATES_DIR = path.join(__dirname, 'templates', 'odoo');

export const PATHS = {
  templatesDir: TEMPLATES_DIR,
  mustache: path.join(TEMPLATES_DIR, 'reserve.mustache'),
  referenceHtml: path.join(TEMPLATES_DIR, 'reserve.html'),
  componentsDir: path.join(TEMPLATES_DIR, 'components'),
  dataJson: path.join(__dirname, 'data.json'),
  odooTemplatesDir: ODOO_TEMPLATES_DIR,
  previewHtml: path.join(__dirname, 'preview.html'),
};

// Campos que son ARRAYS (bucles {{#key}}...{{/key}}) segun ReserveBudgetRQ + uso en template.
// Todo {{#key}} cuyo key este aqui se trata como bucle (N items).
export const ARRAY_SECTIONS = new Set([
  'itineraryInfo',
  'cabins',
  'passengerListCabin',
  'serviceInclude',
  'serviceNotInclude',
  'serviceInformation',
  'priceInfo',
  'paymentCalendarInfo',
  'bankAccounts',
  'transPort',
  'outboundInfo',
  'returnInfo',
  'categoriesInfo',
  'promotions',
  'passengersInfo',
]);

// Secciones que son un OBJETO unico (render una vez con sub-contexto), no bool ni array.
export const OBJECT_SECTIONS = new Set([
  'agent',
  'agentAddress',
  'truspilotInformation',
]);
