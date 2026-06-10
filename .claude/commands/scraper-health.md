# Scraper Health Check

Asumís el rol de operador del sistema de scraping de TicoPrice. Tu trabajo
es diagnosticar la salud de los scrapers leyendo la BD (`db/prices.db`) y
reportar problemas accionables, sin alarmismo.

Usá el Python del venv del proyecto (`.venv/Scripts/python.exe` en Windows,
`.venv/bin/python` en Linux) para consultar SQLite.

---

## Chequeos a ejecutar

### 1. Corridas recientes (`scrape_runs`)
- Últimas corridas por tienda (7 días): success, prices_added, errors, duración
- Tiendas con 2+ fallos consecutivos (el sistema alerta a los 3 — detectalas ANTES)
- Tiendas en status `requires_attention` en la tabla `stores`
- Si `scrape_runs` está vacía con el timer activo, algo está roto en el camino
  `run.py --once` → `runner.run_all` → `_record_and_alert`

### 2. Frescura de datos (`price_history`)
- Fecha del último precio por tienda — más de 24h sin datos = problema
  (el timer corre a las 00:00 y 12:00 UTC = 6pm y 6am hora CR)
- Lecturas por día de los últimos 7 días — la invariante es UNA lectura por
  producto por día (índice único `idx_ph_product_day`)

### 3. Caída de cobertura
- Productos con precio HOY vs promedio de los últimos 7 días, por tienda
- Una caída > 40% en una tienda casi siempre significa que cambió su HTML/API
  y el scraper (magento/vtex/pricesmart) necesita ajuste
- Productos "muertos": sin precio en más de 7 días (¿descontinuados o scraper roto?)

### 4. Integridad física
- Tamaño de `prices.db` y `prices.db-wal` — el WAL debe quedar pequeño después
  de cada corrida (checkpoint TRUNCATE en `run_all`); un WAL de varios MB en
  reposo indica que el checkpoint no está corriendo
- `PRAGMA integrity_check` (rápido con `quick_check`)

---

## Output esperado

1. **Semáforo general**: 🟢 todo bien / 🟡 atención / 🔴 acción requerida
2. **Tabla por tienda**: última corrida, último precio, productos activos, tendencia
3. **Problemas detectados** con causa probable y comando para investigar
   (ej: `python run.py --once "Gollo"` para reproducir un scrape fallido)
4. Si todo está bien, decilo en una línea y no inventes problemas
