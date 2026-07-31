# TODO — email-dev-solocruceros

## Pendiente: limpiar el diff de extracción (`extract.js`)

El extractor funciona pero el re-render contra `reserve.html` todavía deja
campos sin extraer en la sección del FOOTER (después de
`showSectionGoogleOpinion`). El campo `apiUrl` en el bloque
"¿Por qué reservar" (línea ~1323 del template) no encuentra su ancla
`/uploads/email/2020/solocruceros-email-icons.jpg` y captura hasta el final
del HTML, arrastrando tras de sí a `urlTermsConditionsSale`,
`urlPrivacyPolicy`, los `apiUrl` de los iconos de condiciones,
`siteUrl` (x2) y `currentYear`.

### Causa conocida
- El `reserve.html` de referencia tiene **hand-edits**: falta el `<li>` de
  `icon-clip.png` ("Check-in Online obligatorio") y hay ediciones en
  `descriptionMailContent` (párrafo extra "MSC").
- Un text-node largo entre `{{/showSectionGoogleOpinion}}` y el primer
  `{{apiUrl}}` cascaría la coincidencia literal y el recovery no logra
  recolocar `pos`, por lo que todo lo posterior se pierde.

### Cómo reproducir / iterar
```bash
cd /home/asbel/projects/email-dev-solocruceros
DEBUG_ALIGN=1 node extract.js
```
Buscar `NAME "apiUrl" pos=... anchorFound=false` con `anchor="/uploads/email/2020/solocruceros-email-i`.

### Próximo paso para cerrarlo
1. Hacer `matchLiteralAt` más tolerante con literales largos (p.ej. permitir
   saltar un chunk discordante en vez de fallar el nodo entero) o acotar el
   recovery al primer `{{apiUrl}}` del footer.
2. Re-correr hasta que el diff sólo deje la discrepancia conocida del
   párrafo "MSC" en `descriptionMailContent`.

### Estado actual de `data.json`
- 46 escalares + itineraryInfo(4), cabins(1), serviceInclude(5),
  serviceNotInclude(6), serviceInformation(2), priceInfo(4),
  paymentCalendarInfo(2), bankAccounts(4) — **OK**.
- Faltan (footer): `apiUrl`, `urlTermsConditionsSale`, `urlPrivacyPolicy`,
  `currentYear` (en blanco en el JSON actual) — impacto bajo porque son
  URLs/year constantes que se rellenan a mano para la previsualización.
