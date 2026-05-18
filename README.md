# Precio Tracker CR

Rastrea el historial de precios de electrodomésticos en tiendas de Costa Rica.
Detecta descuentos reales vs. precios inflados y expone los datos via API REST.

## Tiendas soportadas

| Tienda | Plataforma | Categoría |
|---|---|---|
| Gollo | Magento 2 | Línea Blanca |
| Monge | Magento 2 | Hogar y Línea Blanca |
| Verdugo | Magento 2 | Hogar y Línea Blanca |
| Walmart CR | VTEX | Electrónica / Línea Blanca |
| Siman CR | VTEX | Línea Blanca |

## Estructura del proyecto

```
precio-tracker-cr/
├── run.py                  # Punto de entrada único (--once / --schedule / --api)
├── requirements.txt
├── db/
│   ├── schema.sql          # DDL completo + datos iniciales de tiendas
│   └── database.py         # Capa de acceso a datos (SQLite)
├── scrapers/
│   ├── base.py             # Clase base y dataclass ProductData
│   ├── magento.py          # Scraper Playwright para Magento 2
│   ├── vtex.py             # Scraper httpx para API VTEX
│   └── runner.py           # Orquestador: coordina scrapers y persiste en BD
├── scheduler/
│   └── cron.py             # Scheduler con `schedule`: 6am y 6pm, logs diarios
├── api/
│   └── main.py             # FastAPI: /products /history /deals /stores
└── logs/                   # Logs diarios (generados en runtime, ignorados por git)
```

## Requisitos

- Python 3.12+
- Windows / Linux / macOS

## Instalación

```bash
# 1. Clonar el repositorio
git clone <url-del-repo>
cd precio-tracker-cr

# 2. Crear entorno virtual
python -m venv .venv

# Windows
.\.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Instalar el browser de Playwright (solo primera vez)
playwright install chromium
```

## Uso

### Scrape inmediato

```bash
# Todas las tiendas
python run.py --once

# Tiendas específicas
python run.py --once Gollo Monge
python run.py --once "Walmart CR"
```

Sale con código 0 si todo fue bien, 1 si hubo errores.

### Scheduler automático

```bash
python run.py --schedule
```

- Ejecuta el scrape completo a las **06:00** y **18:00** todos los días.
- Guarda logs en `logs/scraper_YYYY-MM-DD.log` (rotación diaria automática).
- Si una tienda falla **3 veces consecutivas**, la marca como `requires_attention`
  y emite una alerta `CRITICAL` en el log.

### API REST

```bash
# Producción
python run.py --api

# Desarrollo con hot-reload
python run.py --api --reload --port 8000
```

Documentación interactiva disponible en `http://localhost:8000/docs`.

#### Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/products` | Busca productos. Params: `q`, `category`, `store` |
| `GET` | `/products/{id}/history` | Historial 90 días con min/max/avg y flag `oferta_real` |
| `GET` | `/deals` | Descuentos engañosos ordenados por `deception_gap` |
| `GET` | `/stores` | Tiendas con total de productos y última fecha de scrape |

#### Ejemplos

```bash
# Buscar lavadoras en Gollo
curl "http://localhost:8000/products?q=lavadora&store=Gollo"

# Historial de precios del producto 42
curl "http://localhost:8000/products/42/history"

# Top 20 descuentos sospechosos
curl "http://localhost:8000/deals?limit=20"

# Estado de todas las tiendas
curl "http://localhost:8000/stores"
```

## Base de datos

SQLite en `db/prices.db` (creado automáticamente en el primer scrape).

```
stores          — tiendas (name, base_url, scraper_type, active, status)
products        — productos únicos por tienda (store_id + sku)
price_history   — cada scrape genera un registro con precio y timestamp
scrape_runs     — historial de ejecuciones por tienda (para detectar fallos)
```

### Agregar tiendas

1. Insertar en `stores` (directamente en SQLite o en `schema.sql`):
   ```sql
   INSERT INTO stores (name, base_url, scraper_type)
   VALUES ('Nueva Tienda', 'https://tienda.com', 'vtex');
   ```
2. Añadir la categoría en `scrapers/runner.py` → `STORE_CATEGORIES`.

### Agregar categorías a tiendas existentes

Editar `STORE_CATEGORIES` en `scrapers/runner.py`:
```python
STORE_CATEGORIES = {
    "Gollo": [
        "https://www.gollo.com/c/linea-blanca",
        "https://www.gollo.com/c/tecnologia",   # nueva categoría
    ],
    ...
}
```

## Logs

Los logs del scheduler se guardan en `logs/scraper_YYYY-MM-DD.log`.

```
2026-05-18 06:00:01 [INFO]  scheduler: Job de scraping iniciado
2026-05-18 06:00:03 [INFO]  runner: ── Gollo (magento)  categorías=1
2026-05-18 06:12:45 [INFO]  runner:   ✓ Gollo  nuevos=0  precios=290  errores=0
...
2026-05-18 06:45:00 [CRITICAL] scheduler: ALERTA: 'Verdugo' ha fallado 3 veces
                                          consecutivas → marcada como requires_attention
```

## Desarrollo

```bash
# Verificar que la API arranca sin errores
python run.py --api --reload

# Scrape de una sola tienda para pruebas rápidas
python run.py --once Gollo

# Consultar la BD directamente
python -c "
from db.database import search_products
for p in search_products('lavadora')[:3]:
    print(p['store_name'], p['product_name'], p['price'])
"
```
