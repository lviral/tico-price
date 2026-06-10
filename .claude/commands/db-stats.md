# DB Stats

Snapshot rápido de salud de la base de datos de TicoPrice. Solo lectura,
sin juicios largos — números y una línea de interpretación por sección.

Usá el Python del venv (`.venv/Scripts/python.exe` / `.venv/bin/python`)
contra `db/prices.db`.

---

## Métricas

### Cobertura
- Productos totales y por tienda (con % del total)
- Productos con precio en los últimos 2 días ("activos") vs el total
- Productos sin precio en más de 7 días (probablemente descontinuados)

### Historial
- Total de filas en `price_history`
- Lecturas por día, últimos 7 días — debe ser ~1 por producto activo por día
  (invariante del índice único `idx_ph_product_day`)
- Duplicados por (product_id, día): debe ser SIEMPRE 0; si hay, el índice
  único falta o fue eliminado

### Actividad de scraping
- Últimas 5 corridas de `scrape_runs`: tienda, éxito, precios, errores
- Tiendas en `requires_attention`

### Físico
- Tamaño de `prices.db`, `prices.db-wal`, `prices.db-shm`
- WAL grande (>1MB) en reposo = el checkpoint TRUNCATE no está corriendo
- `PRAGMA quick_check`
- Filas en `products_fts` vs `products` (deben coincidir; si no, el índice
  FTS está desincronizado de los triggers)

### Calidad de datos
- Precios sospechosos: price <= 0, o price > 10,000,000 colones
- Productos sin imagen (`image_url IS NULL`) por tienda
- Productos sin categoría o con categoría fuera de las canónicas

---

## Output esperado

Tablas compactas con los números y máximo una línea de interpretación por
sección. Cerrar con un semáforo: 🟢 sano / 🟡 revisar X / 🔴 problema en X.
