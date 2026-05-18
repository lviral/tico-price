"""API REST para consultar precios históricos de electrodomésticos en CR.

Iniciar:
    uvicorn api.main:app --reload
"""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from db.database import (
    get_deals,
    get_price_history,
    get_product_with_stats,
    get_stores_summary,
    search_products,
)

# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Precio Tracker CR",
    description="Historial de precios de electrodomésticos en tiendas de Costa Rica.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Modelos de respuesta
# ---------------------------------------------------------------------------

class ProductSummary(BaseModel):
    product_id: int
    sku: str
    name: str
    url: str
    category: str | None
    store: str
    price: float | None
    original_price: float | None
    discount_pct: float | None
    in_stock: bool | None
    last_seen: str | None


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
def list_products(
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
            store=r["store_name"],
            price=r["price"],
            original_price=r["original_price"],
            discount_pct=r["discount_pct"],
            in_stock=bool(r["in_stock"]) if r["in_stock"] is not None else None,
            last_seen=r["scraped_at"],
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
def product_history(product_id: int) -> ProductHistory:
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
def deals(
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
