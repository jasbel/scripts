import 'dotenv/config';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Raiz del directorio de templates "default" en el repo PHP.
// Ruta Linux por defecto; sobreescribible via .env (p.ej. en Windows):
//   SOLOCRUCEROS_TEMPLATES_DIR=C:\Users\Rene\projects\symfony-sites\...\templates\default
const TEMPLATES_DIR = process.env.SOLOCRUCEROS_TEMPLATES_DIR
  || '/home/asbel/projects/symfony-sites/sites/solocruceros.com/DDD/4.2MainModule/SoloCrucerosDomain.MainModule/DomainServices/resources/templates/default';

// Raiz del proyecto de plantillas Odoo. Por defecto vive dentro de este repo
// (templates/odoo); con ODOO_TEMPLATES_DIR apunta a un repo externo con layout:
//   <raiz>/templates/*.html   plantillas generadas (build del repo externo)
//   <raiz>/data.json          datos compartidos
//   <raiz>/public/assets      iconos y banners servidos en /assets
const ODOO_TEMPLATES_ROOT = process.env.ODOO_TEMPLATES_DIR
  || path.join(__dirname, 'templates', 'odoo');

export const PATHS = {
  templatesDir: TEMPLATES_DIR,
  mustache: path.join(TEMPLATES_DIR, 'reserve.mustache'),
  referenceHtml: path.join(TEMPLATES_DIR, 'reserve.html'),
  componentsDir: path.join(TEMPLATES_DIR, 'components'),
  dataJson: path.join(__dirname, 'data.json'),
  odooRoot: ODOO_TEMPLATES_ROOT,
  odooTemplatesDir: path.join(ODOO_TEMPLATES_ROOT, 'templates'),
  odooDataJson: path.join(ODOO_TEMPLATES_ROOT, 'data.json'),
  odooAssetsDir: path.join(ODOO_TEMPLATES_ROOT, 'public', 'assets'),
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
