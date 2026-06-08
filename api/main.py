"""API REST para consultar precios históricos de electrodomésticos en CR.

Iniciar:
    uvicorn api.main:app --reload
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
SITE_URL = os.getenv("SITE_URL", "http://localhost:8000").rstrip("/")

limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

from db.database import (
    get_categories,
    get_deals,
    get_inflation_index,
    get_price_history,
    get_product_with_stats,
    get_stores_summary,
    get_top_increases,
    search_products,
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="TicoPrice API",
    description="Historial de precios de electrodomésticos, celulares y tecnología en Costa Rica.",
    version="1.0.0",
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Cache-Control middleware
# Scrapers corren 2x/día → datos frescos cada ~12h.
# Endpoints lentos (full-scan + subconsultas) se cachean agresivamente.
# ---------------------------------------------------------------------------

_CACHE_RULES: dict[str, str] = {
    "/categories": "public, max-age=3600, stale-while-revalidate=7200",
    "/stores":     "public, max-age=3600, stale-while-revalidate=7200",
    "/version":    "public, max-age=60",
}
_CACHE_DEFAULT_API = "public, max-age=300, stale-while-revalidate=600"


@app.middleware("http")
async def cache_control(request: Request, call_next):
    response = await call_next(request)
    path = request.url.path

    # No tocar respuestas de error ni archivos estáticos (Caddy los maneja)
    if response.status_code >= 400 or path.startswith("/static/"):
        return response

    if path in _CACHE_RULES:
        response.headers["Cache-Control"] = _CACHE_RULES[path]
    elif any(path.startswith(p) for p in ("/products", "/deals", "/trending", "/inflation")):
        response.headers["Cache-Control"] = _CACHE_DEFAULT_API

    return response

app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def serve_frontend() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


# ---------------------------------------------------------------------------
# Modelos de respuesta
# ---------------------------------------------------------------------------

def _pct_change(current: float | None, old: float | None) -> float | None:
    """Variación porcentual entre dos precios. None si no hay datos suficientes."""
    if current is None or old is None or old == 0:
        return None
    return round((current - old) * 100.0 / old, 1)


class ProductSummary(BaseModel):
    product_id: int
    sku: str
    name: str
    url: str
    category: str | None
    image_url: str | None = None
    store: str
    price: float | None
    original_price: float | None
    discount_pct: float | None
    in_stock: bool | None
    last_seen: str | None
    price_change_7d: float | None = Field(
        None, description="Variación % del precio vs hace 7 días. Positivo = aumentó."
    )
    price_change_30d: float | None = Field(
        None, description="Variación % del precio vs hace 30 días. Positivo = aumentó."
    )


class PricePoint(BaseModel):
    price: float
    original_price: float | None
    discount_pct: float | None
    in_stock: bool
    scraped_at: str


class ProductHistory(BaseModel):
    product_id: int
    name: str
    store: str
    url: str
    category: str | None
    current_price: float | None
    price_min: float | None = Field(description="Precio mínimo en el período")
    price_max: float | None = Field(description="Precio máximo en el período")
    price_avg: float | None = Field(description="Precio promedio en el período")
    oferta_real: bool = Field(
        description="True si el precio actual es más de 10 % menor al promedio histórico"
    )
    sample_count: int = Field(description="Registros en el período")
    history: list[PricePoint]


class DealItem(BaseModel):
    product_id: int
    name: str
    url: str
    category: str | None
    store: str
    current_price: float
    original_price: float | None
    advertised_discount: float = Field(description="Descuento anunciado por la tienda (%)")
    real_discount: float = Field(description="Descuento real vs máximo histórico 90 días (%)")
    deception_gap: float = Field(
        description="advertised_discount - real_discount. "
        "Positivo = la tienda exagera el descuento."
    )
    price_max_90d: float
    sample_count: int


class CategoryInflation(BaseModel):
    category: str | None
    avg_change_pct: float
    product_count: int


class WeeklyPoint(BaseModel):
    week: str = Field(description="Semana en formato YYYY-Www")
    avg_price: float
    product_count: int


class InflationIndex(BaseModel):
    days: int = Field(description="Ventana de comparación en días")
    overall_change_pct: float | None = Field(
        description="Variación % promedio de todos los productos"
    )
    product_count: int = Field(description="Productos con datos comparables")
    by_category: list[CategoryInflation]
    weekly_trend: list[WeeklyPoint]


class StoreSummary(BaseModel):
    id: int
    name: str
    base_url: str
    scraper_type: str
    active: bool
    total_products: int
    last_scraped_at: str | None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get(
    "/products",
    response_model=list[ProductSummary],
    summary="Buscar productos",
    description=(
        "Busca productos por nombre con filtros opcionales de categoría y tienda. "
        "Retorna cada producto con su último precio registrado. "
        "Si `q` está vacío devuelve todos los productos (hasta 200)."
    ),
)
@limiter.limit("30/minute")
def list_products(
    request: Request,
    q: Annotated[str, Query(description="Texto a buscar en el nombre")] = "",
    category: Annotated[str | None, Query(description="Filtrar por categoría")] = None,
    store: Annotated[str | None, Query(description="Filtrar por nombre de tienda")] = None,
) -> list[ProductSummary]:
    rows = search_products(q, category=category, store=store)
    return [
        ProductSummary(
            product_id=r["product_id"],
            sku=r["sku"],
            name=r["product_name"],
            url=r["url"],
            category=r["category"],
            image_url=r["image_url"],
            store=r["store_name"],
            price=r["price"],
            original_price=r["original_price"],
            discount_pct=r["discount_pct"],
            in_stock=bool(r["in_stock"]) if r["in_stock"] is not None else None,
            last_seen=r["scraped_at"],
            price_change_7d=_pct_change(r["price"], r["price_7d_ago"]),
            price_change_30d=_pct_change(r["price"], r["price_30d_ago"]),
        )
        for r in rows
    ]


@app.get(
    "/products/{product_id}/history",
    response_model=ProductHistory,
    summary="Historial de precios de un producto",
    description=(
        "Retorna los últimos 90 días de historial de precios junto con estadísticas "
        "del período (mínimo, máximo, promedio). "
        "El campo `oferta_real` es `true` cuando el precio actual es más de un 10 % "
        "inferior al promedio histórico, indicando una baja genuina de precio."
    ),
)
@limiter.limit("60/minute")
def product_history(request: Request, product_id: int) -> ProductHistory:
    stats_row = get_product_with_stats(product_id, days=90)
    if stats_row is None:
        raise HTTPException(status_code=404, detail="Producto no encontrado")

    history_rows = get_price_history(product_id, days=90)

    current = stats_row["current_price"]
    avg = stats_row["price_avg"]
    oferta_real = bool(
        current is not None
        and avg is not None
        and avg > 0
        and current < avg * 0.9
    )

    return ProductHistory(
        product_id=stats_row["product_id"],
        name=stats_row["product_name"],
        store=stats_row["store_name"],
        url=stats_row["url"],
        category=stats_row["category"],
        current_price=current,
        price_min=stats_row["price_min"],
        price_max=stats_row["price_max"],
        price_avg=round(avg, 2) if avg is not None else None,
        oferta_real=oferta_real,
        sample_count=stats_row["sample_count"] or 0,
        history=[
            PricePoint(
                price=r["price"],
                original_price=r["original_price"],
                discount_pct=r["discount_pct"],
                in_stock=bool(r["in_stock"]),
                scraped_at=r["scraped_at"],
            )
            for r in history_rows
        ],
    )


@app.get(
    "/deals",
    response_model=list[DealItem],
    summary="Detectar descuentos engañosos",
    description=(
        "Lista productos donde el descuento *anunciado* por la tienda no se corresponde "
        "con la variación real del precio histórico. "
        "El campo `deception_gap` mide la diferencia: un valor positivo alto significa "
        "que la tienda anuncia, por ejemplo, 40 % de descuento pero el precio máximo "
        "de los últimos 90 días era solo un 5 % más caro. "
        "Solo incluye productos con ≥ 3 registros históricos para evitar falsos positivos."
    ),
)
@limiter.limit("20/minute")
def deals(
    request: Request,
    limit: Annotated[int, Query(ge=1, le=200, description="Máximo de resultados")] = 50,
) -> list[DealItem]:
    rows = get_deals(limit=limit)
    return [
        DealItem(
            product_id=r["product_id"],
            name=r["product_name"],
            url=r["url"],
            category=r["category"],
            store=r["store_name"],
            current_price=r["current_price"],
            original_price=r["original_price"],
            advertised_discount=r["advertised_discount"],
            real_discount=r["real_discount"] or 0.0,
            deception_gap=r["deception_gap"] or 0.0,
            price_max_90d=r["price_max_90d"],
            sample_count=r["sample_count"],
        )
        for r in rows
    ]


@app.get(
    "/trending",
    response_model=list[ProductSummary],
    summary="Productos que más aumentaron",
    description=(
        "Lista los productos con mayor incremento porcentual de precio "
        "en los últimos `days` días. Solo incluye productos con historial "
        "en ambos extremos del período."
    ),
)
@limiter.limit("20/minute")
def trending(
    request: Request,
    days: Annotated[int, Query(ge=1, le=90, description="Ventana de días a comparar")] = 7,
    limit: Annotated[int, Query(ge=1, le=200, description="Máximo de resultados")] = 50,
) -> list[ProductSummary]:
    rows = get_top_increases(days=days, limit=limit)
    return [
        ProductSummary(
            product_id=r["product_id"],
            sku=r["sku"],
            name=r["product_name"],
            url=r["url"],
            category=r["category"],
            image_url=r["image_url"],
            store=r["store_name"],
            price=r["price"],
            original_price=r["original_price"],
            discount_pct=r["discount_pct"],
            in_stock=bool(r["in_stock"]) if r["in_stock"] is not None else None,
            last_seen=r["scraped_at"],
            price_change_7d=_pct_change(r["price"], r["price_before"]) if days == 7 else None,
            price_change_30d=_pct_change(r["price"], r["price_before"]) if days == 30 else None,
        )
        for r in rows
    ]


@app.get(
    "/categories",
    response_model=list[str],
    summary="Listar categorías",
    description="Retorna todas las categorías únicas con al menos un producto registrado.",
)
def categories_list() -> list[str]:
    return get_categories()


@app.get(
    "/inflation",
    response_model=InflationIndex,
    summary="Índice de inflación",
    description=(
        "Calcula la variación promedio de precios comparando el precio actual de cada "
        "producto con su último precio registrado hace al menos `days` días. "
        "Incluye desglose por categoría y tendencia semanal de las últimas 12 semanas."
    ),
)
@limiter.limit("20/minute")
def inflation(
    request: Request,
    days: Annotated[int, Query(ge=7, le=365, description="Ventana de comparación en días")] = 30,
) -> InflationIndex:
    data = get_inflation_index(days=days)
    return InflationIndex(
        days=days,
        overall_change_pct=data["overall_change_pct"],
        product_count=data["product_count"],
        by_category=[
            CategoryInflation(
                category=c["category"],
                avg_change_pct=c["avg_change_pct"],
                product_count=c["product_count"],
            )
            for c in data["by_category"]
        ],
        weekly_trend=[
            WeeklyPoint(
                week=w["week"],
                avg_price=w["avg_price"],
                product_count=w["product_count"],
            )
            for w in data["weekly_trend"]
        ],
    )


@app.get(
    "/stores",
    response_model=list[StoreSummary],
    summary="Listar tiendas",
    description=(
        "Retorna todas las tiendas configuradas con el total de productos rastreados "
        "y la fecha del último scrape exitoso."
    ),
)
def stores() -> list[StoreSummary]:
    rows = get_stores_summary()
    return [
        StoreSummary(
            id=r["id"],
            name=r["name"],
            base_url=r["base_url"],
            scraper_type=r["scraper_type"],
            active=bool(r["active"]),
            total_products=r["total_products"] or 0,
            last_scraped_at=r["last_scraped_at"],
        )
        for r in rows
    ]


# ---------------------------------------------------------------------------
# SEO — robots.txt, sitemap.xml, SPA fallback
# ---------------------------------------------------------------------------

@app.get("/robots.txt", include_in_schema=False)
def robots_txt() -> PlainTextResponse:
    return PlainTextResponse(
        f"User-agent: *\n"
        f"Allow: /\n"
        f"Sitemap: {SITE_URL}/sitemap.xml\n"
    )


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml() -> Response:
    from db.database import get_db
    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.id, ph.scraped_at
               FROM products p
               LEFT JOIN price_history ph ON ph.id = (
                   SELECT id FROM price_history WHERE product_id = p.id
                   ORDER BY scraped_at DESC LIMIT 1
               )
               ORDER BY p.id"""
        ).fetchall()

    urls = [f"  <url><loc>{SITE_URL}/</loc><changefreq>daily</changefreq><priority>1.0</priority></url>"]
    for r in rows:
        lastmod = (r["scraped_at"] or "")[:10]
        lastmod_tag = f"<lastmod>{lastmod}</lastmod>" if lastmod else ""
        urls.append(
            f"  <url>"
            f"<loc>{SITE_URL}/producto/{r['id']}</loc>"
            f"{lastmod_tag}"
            f"<changefreq>daily</changefreq>"
            f"<priority>0.8</priority>"
            f"</url>"
        )

    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "\n".join(urls)
        + "\n</urlset>"
    )
    return Response(content=xml, media_type="application/xml")


@app.get("/sw.js", include_in_schema=False)
def service_worker():
    return FileResponse(FRONTEND_DIR / "static" / "js" / "sw.js",
                        media_type="application/javascript")


@app.get("/manifest.json", include_in_schema=False)
def manifest_json():
    return FileResponse(FRONTEND_DIR / "static" / "manifest.json",
                        media_type="application/manifest+json")


@app.get("/version", include_in_schema=False)
def static_version() -> dict:
    """Retorna un hash corto basado en el contenido de los archivos estáticos.

    El Service Worker lo usa como clave de caché: cuando se despliega una nueva
    versión los archivos cambian → el hash cambia → el SW invalida el caché viejo.
    """
    static_dir = FRONTEND_DIR / "static"
    h = hashlib.sha1(usedforsecurity=False)
    for f in sorted(static_dir.rglob("*")):
        if f.is_file():
            stat = f.stat()
            h.update(f.name.encode())
            h.update(stat.st_mtime_ns.to_bytes(8, "little"))
            h.update(stat.st_size.to_bytes(8, "little"))
    return {"version": h.hexdigest()[:12]}


# IMPORTANTE: este catch-all debe ir al final para no interferir con las rutas de la API.
@app.get("/{full_path:path}", include_in_schema=False)
def spa_fallback(full_path: str) -> FileResponse:
    """Sirve index.html para cualquier ruta no-API (SPA con History API routing)."""
    return FileResponse(FRONTEND_DIR / "index.html")
