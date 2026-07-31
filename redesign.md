# Rediseño email *Reserve* — prompts por sección

**Cómo usar:** copia UN bloque y pégalo en el asistente. Cada bloque es autónomo (incluye sus reglas). Revisa e integra antes de seguir con el siguiente.

/* Estilos base (desktop) */
.container {
    width: 600px;
}

/* Mobile */
@media only screen and (max-width: 600px) {
    .container {
        width: 100% !important;
    }
}

---

```text
=== HEADER ===  reemplazar en template @default/reserve.mustache seccion <!-- Header --> … <!-- Hero -->

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=161-580&m=dev
FIGMA Desktop: https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=218-1805&m=dev
VARIABLES: {{siteUrl}} {{logoPhoneImg}} {{siteName}}

- Mobile: solo logo SoloCruceros, centrado.
- Desktop: 3 columnas → [logo] [horario + email] [teléfonos].
- Columnas 2 y 3 ocultas en mobile (clase hide-mobile). Logo clickable a {{siteUrl}}.
```

```text
=== HERO ===  reemplazar en template @default/reserve.mustache seccion <!-- Hero --> … <!-- Client -->

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=161-526&m=dev
FIGMA Desktop: https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=708-1844&m=dev  (nº de presupuesto va DEBAJO de Client)
VARIABLES: {{{titleMailContent}}} {{locatorReserve}}

- Título + nº de presupuesto {{locatorReserve}}.
- En desktop el nº se reubica bajo Client; en mobile se muestra aquí.
```

```text
=== CLIENT ===  reemplazar en template @default/reserve.mustache seccion <!-- Client --> … <!-- Cruise -->

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=89-1311&m=dev
FIGMA Desktop: https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=664-1167&m=dev
VARIABLES: {{nameClient}} {{{descriptionMailContent}}} {{urlReserve}} {{locatorReserve}}

- Saludo "Hola, {{nameClient}}".
- Anuncio con {{{descriptionMailContent}}} (mover aquí desde Hero).
- Botón "Ver mi Presupuesto" → enlace a confirmar (candidato: {{urlReserve}}).
- Desktop: debajo, mostrar nº de presupuesto {{locatorReserve}}.
```

```text
=== CRUISE ===  reemplazar en template @default/reserve.mustache seccion <!-- Cruise --> … <!-- Itinerary -->

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=111-190&m=dev
FIGMA Desktop: https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=218-1839&m=dev
VARIABLES: {{shipPrimaryImg}} {{cruiseName}} {{departureDate}} {{passengers}}  ({{shipName}})

- Imagen del barco + nombre del crucero.
- Salida + nº de pasajeros en UNA sola fila.
- Logo flotante del diseño: NO flotando (Outlook no soporta position). Si se quiere, inline encima de la imagen; preferible omitir.
```

```text
=== ITINERARY ===  reemplazar en template @default/reserve.mustache seccion <!-- Itinerary --> … <!-- Cabin -->

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=89-1358&m=dev
FIGMA Desktop: https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=218-2190&m=dev
VARIABLES: {{itineraryImg}} {{#itineraryInfo}}{{day}} {{port}} {{arrival}} {{departure}}{{/itineraryInfo}}

- Imagen de la ruta + días. Iterar itineraryInfo. Duración total = nº de items.
```

```text
=== CABIN ===  reemplazar en template @default/reserve.mustache seccion <!-- Cabin --> … <!-- Presupuesto -->

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=89-1332&m=dev
FIGMA Desktop: https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=218-1859&m=dev
VARIABLES: {{#cabins}}{{imageCabin}} {{categoryCabin}} {{descriptionCabin}} {{numberCabin}}{{/cabins}}

- Iterar cabins: imagen, nombre ({{categoryCabin}}), ubicación ({{numberCabin}}).
```

```text
=== PRESUPUESTO ===  reemplazar en template @default/reserve.mustache seccion <!-- Presupuesto --> … <!-- Agent -->

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=450-635&m=dev
Desktop: NO existe → ocultar en desktop.
VARIABLES: {{locatorReserve}} {{urlReserve}}

- Nº de presupuesto + botón "Ver mi Presupuesto" (enlace a confirmar, candidato {{urlReserve}}). Solo mobile.
```

```text
=== AGENT ===  reemplazar en template @default/reserve.mustache seccion <!-- Agent --> … <!-- Contact -->, envolver en {{#agent}}…{{/agent}}

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=460-399&m=dev
FIGMA Desktop: https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=461-933&m=dev
VARIABLES: {{#agent}}{{photo}} {{name}} {{surname}} {{email}} {{phone}} {{phoneInt}} {{#agentAddress}}{{address}} {{googlemaps}}{{/agentAddress}}{{/agent}}

- Foto, nombre+apellido, cargo, correo (y teléfonos si figuran).
```

```text
=== CONTACT ===  reemplazar en template @default/reserve.mustache seccion <!-- Contact --> … <!-- Advantages -->

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=656-298&m=dev
FIGMA Desktop: https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=656-646&m=dev
VARIABLES: {{siteEmail}}  (teléfonos y horario: HARDCODE — constantes de empresa)

- Teléfonos por país (hardcodear). Correo {{siteEmail}}. Horario.
- Si los teléfonos vienen del backend, usar loop {{#phones}}; si no, hardcode.
```

```text
=== ADVANTAGES ===  reemplazar en template @default/reserve.mustache seccion <!-- Advantages --> … (siguiente bloque)

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=864-1151&m=dev  (grid 2x2)
FIGMA Desktop: https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=864-1720&m=dev
VARIABLES: {{apiUrl}}  (iconos)

- Título con logo "SoloCruceros.com" recreado en CSS (Solo en #057AFF).
- Subtítulo + 4 items (icono+descripción). Mobile 2x2, desktop en fila.
```

```text
=== TRUSTPILOT ===  bloque NUEVO entre Advantages y Footer; envolver en {{#showSectionTrustPilot}}…{{/showSectionTrustPilot}}

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=330-713&m=dev
FIGMA Desktop: https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=381-1245&m=dev


- Caja con borde, descripción + logo. Tabla con border + padding.
tengo el truspilot image esta en, `{apiUrl}}/uploads/email/icons/trustpilot.png`
```

```text
=== FOOTER (logo-footer) ===  reemplazar en template @default/reserve.mustache seccion <!-- Footer --> … cierre

EMAIL HTML (tablas + CSS inline, contenedor 700px, responsive @media max-width:700px).
Compat: Gmail/Outlook/Apple/Yahoo — sin position:absolute, flex/grid, form, JS.
Mantener <!-- marcadores -->, no usar id. Variables {{{x}}}=HTML, {{x}}=texto; no inventar vars.

FIGMA Mobile : https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=161-499&m=dev
FIGMA Desktop: https://www.figma.com/design/gKZZzF8CGKwjrfByWuLyGj/Email-marketing---Reservas?node-id=226-376&m=dev
VARIABLES: {{siteUrl}} {{logoPhoneImg}} {{currentYear}} {{urlTermsConditionsSale}} {{urlPrivacyPolicy}}

- Logo (una sola imagen {{logoPhoneImg}}; si el desktop es SVG, servir 1 imagen unificada). Descripción + enlaces legales.
```
