import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

// Raiz del directorio de templates "default" en el repo PHP
const TEMPLATES_DIR = '/home/asbel/projects/symfony-sites/sites/solocruceros.com/DDD/4_Domain/4.2MainModule/SoloCrucerosDomain.MainModule/DomainServices/resources/templates/default';

export const PATHS = {
  templatesDir: TEMPLATES_DIR,
  mustache: path.join(TEMPLATES_DIR, 'reserve.mustache'),
  referenceHtml: path.join(TEMPLATES_DIR, 'reserve.html'),
  componentsDir: path.join(TEMPLATES_DIR, 'components'),
  dataJson: path.join(__dirname, 'data.json'),
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
