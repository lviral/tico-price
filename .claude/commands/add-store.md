# Agregar Tienda

Guía el proceso completo de agregar una tienda nueva a TicoPrice.
El nombre/URL de la tienda viene en `$ARGUMENTS`; si falta, pedilo.

El error más común es agregar la tienda a la BD y olvidar el frontend —
seguí TODOS los pasos.

---

## Pasos

### 1. Identificar la plataforma
Visitá la tienda (WebFetch) y determiná el tipo de scraper:
- **magento**: URLs tipo `/categoria.html`, HTML server-rendered
  (Gollo, Monge, Verdugo, Aliss, EPA, RadioShack)
- **vtex**: API pública `/api/catalog_system/pub/products/search`
  (Walmart CR, Siman CR)
- **pricesmart**: caso especial con scraper propio
- Si no es ninguna → hay que escribir un scraper nuevo en `scrapers/`
  siguiendo el patrón de los existentes (devuelve dicts con sku, name, url,
  price, original_price, discount_pct, category, image_url, in_stock)

### 2. Registrar en la BD
- Agregar la migración en `db/database.py` → `init_db()`, en el bloque
  "Migración: insertar tiendas nuevas" (lista de tuplas name/base_url/scraper_type)
- NO editar solo `schema.sql`: las BDs existentes no lo re-ejecutan

### 3. Configurar categorías
- En `scrapers/runner.py`: agregar la tienda a `STORE_CATEGORIES` con los
  slugs de categoría a scrapear
- Mapear slugs nuevos en `CATEGORY_NORMALIZE` → categorías canónicas
  (linea-blanca, celulares, televisores, computacion, electrodomesticos, audio...)
- Recordar: `MIN_PRICE = 20000` filtra accesorios; categorías fuera de
  `CATEGORY_ALLOWLIST` se descartan

### 4. Actualizar el frontend (¡no olvidar!)
- `frontend/index.html`:
  - Footer → `<ul class="footer-stores-list">`: agregar `<li>`
  - Contador "N tiendas" en CUATRO lugares: meta description, og:description,
    twitter:description y el tagline del header
- Los preconnect del `<head>` solo se tocan si la tienda nueva domina el
  trending (revisar después de unos días de datos)

### 5. Probar
- `python run.py --once "Nombre Tienda"` — scrape de prueba solo de esa tienda
- Verificar: productos insertados con categoría normalizada, precios > 0,
  imágenes con URL válida, sin errores en el log
- `GET /stores` debe listar la tienda con `total_products > 0`

### 6. Commit
Un solo commit con todo: migración + runner + frontend. Mensaje en español
siguiendo el estilo del repo (`git log --oneline -5` para ver el formato).
