# Implementación del nuevo diseño de email

## Objetivo

Implementar el nuevo diseño del email de reservas utilizando los diseños de Figma.

Archivo principal:

- `@reserve.mustache`

Tomar como referencia la implementación actual en:

- `@default/reserve.mustache`

La implementación debe ser completamente responsive, diferenciando las versiones Mobile y Desktop.

## Requisitos generales

- Mantener compatibilidad con clientes de correo (Gmail, Outlook, Apple Mail, Yahoo, etc.).
- Priorizar HTML para email sobre HTML web convencional.
- Evitar técnicas con baja compatibilidad.
- Reutilizar componentes cuando sea posible.
- Mantener el código limpio y organizado por secciones.
- Conservar las variables Mustache existentes siempre que sea posible.
- Si alguna estructura actual no es adecuada para el nuevo diseño, proponer una alternativa antes de implementarla.
- Si una sección del diseño no es recomendable para emails (por compatibilidad o mantenibilidad), indicarlo y sugerir una mejor solución.

---

# HEADER

## Objetivo

Reemplazar completamente la sección `header` existente.

Referencia actual:

- `@default/reserve.mustache`
- bloque `id="header"`

### Revisión

Antes de implementarlo:

- Revisar si realmente es conveniente mantener `id="header"` en un email.
- Si no aporta ninguna ventaja, reemplazarlo por clases CSS.

---

## Mobile

Figma:

https://...

Implementar:

- Logo SoloCruceros centrado.

---

## Desktop

Figma:

https://...

Implementar una estructura de tres columnas:

Columna 1

- Logo

Columna 2

- Horario
- Correo

Columna 3

- Teléfonos

---

# BODY

Diseño general

Mobile

https://...

Desktop

https://...

Dividir el cuerpo en componentes independientes.

---

## Hero

Mobile

https://...

Desktop

https://...

Contenido:

- título
- número de presupuesto
- saludo
- mensaje principal
- botón "Ver mi presupuesto"

---

## Item Cruise

Mobile

https://...

Desktop

https://...

Contenido:

- imagen barco
- nombre crucero
- salida
- cantidad personas

Revisión:

El logo flotante del diseño probablemente no sea apropiado para emails. Evaluar si debe eliminarse o adaptarse.

---

## Item Map

Mobile

https://...

Desktop

https://...

Contenido

- imagen
- ruta
- duración

---

## Item Cabin

Mobile

https://...

Desktop

https://...

Contenido

- imagen
- nombre
- ubicación de cabina

---

## Presupuesto

Mobile

https://...

Desktop

https://...

Contenido

- número presupuesto
- botón

---

# FOOTER

Implementar un nuevo footer.

Mobile

https://...

Desktop

https://...

El footer estará compuesto por las siguientes subsecciones.

---

## Persona / Agente

Mobile

https://...

Desktop

https://...

Contenido

- fotografía
- nombre
- cargo
- correo

Revisión requerida:

Actualmente esta sección es la única dinámica del footer.

Evaluar si es más apropiado ubicarla:

- dentro del footer
- al final del body

Justificar la decisión antes de implementarla.

---

## Contactos

Mobile

https://...

Desktop

https://...

Contenido

- teléfonos por país
- correo
- horario

---

## Ventajas

Mobile

https://...

Desktop

https://...

Contenido

- título
- logo
- subtítulo
- cuatro ventajas

En Mobile:

- mostrar en una cuadrícula 2x2.

El logo puede recrearse con HTML/CSS si resulta más conveniente que usar una imagen.

---

## Trustpilot

Mobile

https://...

Desktop

https://...

Contenido

- logo
- descripción

Implementar con el borde mostrado en Figma.

---

## Logo Footer

Mobile

https://...

Desktop

https://...

Contenido

- logo
- descripción

---

# Entregables

La implementación debe incluir:

- HTML Mustache
- CSS compatible con email
- comentarios únicamente cuando aporten contexto
- revisión de compatibilidad con clientes de correo
- observaciones sobre cualquier elemento del diseño que no sea recomendable implementar exactamente igual en un email