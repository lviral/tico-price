# Lighthouse Fix

Analizá un reporte JSON de Lighthouse y proponé SOLO los fixes con impacto
real, filtrando los falsos positivos conocidos de este proyecto.

**Input**: la ruta al JSON viene en `$ARGUMENTS`. Si no viene, pedila.

Usá Python (`.venv/Scripts/python.exe`) para parsear el JSON — no lo leas
entero con Read, puede medir varios MB.

---

## Qué extraer

1. **Scores** de las 4 categorías
2. **Métricas core**: FCP, LCP, TBT, CLS, Speed Index con sus scores
3. **Audits con score < 0.9** de performance
4. **Fallos de accesibilidad** (color-contrast con los colores y ratios exactos)
5. **Elemento LCP** y su checklist de discovery (fetchpriority, discoverable, eager)

## Falsos positivos conocidos — NO proponer fixes para esto

- `cache-insight` / `uses-long-cache-ttl` en localhost: uvicorn no cachea
  estáticos, pero en producción Caddy sirve `Cache-Control: public, max-age=3600`
- `document-latency-insight` (compresión): Caddy comprime con zstd/gzip en prod
- `image-delivery-insight` sobre imágenes de productos: vienen de los CDNs de
  las tiendas (gollo.com, vteximg.com.br) — no controlamos ese servidor
- `unused-javascript` de `chart.umd.min.js`: ya se carga bajo demanda vía `lc()`
- Errores de consola por MIME type del service worker: artefacto de SW viejo
  en el browser de prueba, se resuelve solo

## Contexto del frontend (para proponer fixes correctos)

- JS minificado a mano en `frontend/static/js/app.js` (IIFE, sin build step) —
  los edits se hacen con Python por posición/anchor, NUNCA reescribir el archivo
- CSP estricto `script-src 'self'`: nada inline, ni handlers `onerror=`
- El trending renderiza 12 cards + resto en `requestIdleCallback`
- La primera card lleva `loading=eager fetchpriority=high` (es el LCP)
- Dark mode vía `[data-theme=dark]` — todo fix de contraste necesita AMBOS modos;
  verificá ratios matemáticamente (WCAG AA: 4.5:1 texto normal, 3:1 texto grande)

---

## Output esperado

1. Comparación contra el reporte anterior si lo conocés (¿qué mejoró/empeoró?)
2. Causas reales del score con su peso estimado
3. Fixes propuestos en orden de impacto, con archivo y cambio concreto
4. Lista de falsos positivos ignorados (una línea c/u)

No apliques cambios — reportá y esperá confirmación.
