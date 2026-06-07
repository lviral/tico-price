"""Orquestador principal: lee tiendas de SQLite, instancia scrapers y persiste precios."""

import logging
import sys
import time
from dataclasses import dataclass

from db.database import get_active_stores, init_db, save_product
from scrapers.magento import MagentoScraper
from scrapers.vtex import VtexScraper

log = logging.getLogger("runner")

# ---------------------------------------------------------------------------
# Configuración de scrapers y categorías por tienda
# ---------------------------------------------------------------------------

SCRAPER_MAP = {
    "magento": MagentoScraper,
    "vtex": VtexScraper,
}

# Mapeo de slugs de categoría → nombre canónico en español.
# Asegura que tiendas distintas que usan nombres diferentes queden unificadas.
CATEGORY_NORMALIZE: dict[str, str] = {
    # Línea blanca
    "hogar-y-linea-blanca":       "linea-blanca",
    "hogar":                      "linea-blanca",
    "refrigeracion":              "linea-blanca",
    "refrigeradoras":             "linea-blanca",
    "lavadoras":                  "linea-blanca",
    "lavadoras-y-secadoras":      "linea-blanca",
    "cocinas":                    "linea-blanca",
    "cocina":                     "linea-blanca",
    "microondas":                 "linea-blanca",
    # Celulares
    "celulares-y-tablets":        "celulares",
    "celulares-y-telefonos":      "celulares",
    "telefonia":                  "celulares",
    "telefonos":                  "celulares",
    "smartphones":                "celulares",
    # Televisores
    "tv-y-video":                 "televisores",
    "pantallas":                  "televisores",
    # Computación
    "computacion":                "computacion",
    "computadoras":               "computacion",
    "laptops":                    "computacion",
    "laptop":                     "computacion",
    "computadoras-gaming":        "computacion",
    # Electrodomésticos
    "pequenos-electrodomesticos": "electrodomesticos",
    "small-appliances":           "electrodomesticos",
    # Audio / sonido
    "audio":                      "audio",
    "audio-video":                "audio",
    "audio-y-video":              "audio",
    # Videojuegos / gaming
    "gaming":                     "videojuegos",
    "gamer-lab":                  "videojuegos",
    "consolas":                   "videojuegos",
    # Ignorados (no en allowlist)
    "electronics":                "electronica",
    "tecnologia":                 "electronica",
    # Cuidado del cabello / electrobelleza
    "cuidado-personal":                        "cuidado-cabello",
    "cuidado-de-cabello":                      "cuidado-cabello",
    "cuidado-del-cabello":                     "cuidado-cabello",
    "electrobelleza":                          "cuidado-cabello",
    "alisadores-y-onduladores":                "cuidado-cabello",
    "secadores-de-pelo":                       "cuidado-cabello",
    "herramientas-para-estilizar-el-cabello":  "cuidado-cabello",
}

# Categorías por nombre de tienda. Ajustar aquí cuando se agreguen tiendas.
STORE_CATEGORIES: dict[str, list[str]] = {
    "Gollo": [
        "https://www.gollo.com/c/linea-blanca",
        "https://www.gollo.com/c/tv-y-video",
        "https://www.gollo.com/c/telefonia",
        "https://www.gollo.com/c/audio",
        "https://www.gollo.com/c/pequenos-electrodomesticos",
        "https://www.gollo.com/c/gaming",
        "https://www.gollo.com/c/computacion",
    ],
    "Monge": [
        "https://www.tiendamonge.com/productos/hogar",
        "https://www.tiendamonge.com/productos/celulares-y-tablets/celulares",
        "https://www.tiendamonge.com/productos/tv-y-video/pantallas",
        "https://www.tiendamonge.com/productos/audio",
        "https://www.tiendamonge.com/productos/electrodomesticos",
        "https://www.tiendamonge.com/productos/gamer-lab",
        "https://www.tiendamonge.com/productos/computadoras/laptops",
        "https://www.tiendamonge.com/productos/computadoras/desktop/computadoras-de-escritorio",
    ],
    "Verdugo": [
        "https://www.verdugotienda.com/productos/hogar",
        "https://www.verdugotienda.com/productos/celulares-y-tablets/celulares",
        "https://www.verdugotienda.com/productos/tv-y-video/pantallas",
        "https://www.verdugotienda.com/productos/audio",
        "https://www.verdugotienda.com/productos/electrodomesticos",
        "https://www.verdugotienda.com/gamer-lab",
        "https://www.verdugotienda.com/productos/computadoras",
    ],
    "Walmart CR": [
        "/electronica/linea-blanca",
        "/electronica/celulares",
        "/electronica/televisores",
        "/electronica/electrodomesticos",
        "/electronica/audio",
        "/electronica/videojuegos",
        "/electronica/computacion",
    ],
    "Siman CR": [
        "/linea-blanca",
        "/linea-blanca/refrigeradoras",
        "/linea-blanca/lavadoras",
        "/electrodomesticos",
        "/tecnologia/telefonos/celulares",
        "/tecnologia/televisores",
        "/tecnologia/audio-y-video",
        "/tecnologia/computadoras/laptops",
        "/belleza-e-higiene/electrobelleza",
    ],
    "Aliss CR": [
        "https://aliss.cr/pequenos-electrodomesticos",
    ],
    "EPA CR": [
        "https://cr.epaenlinea.com/electrodomesticos.html",
        "https://cr.epaenlinea.com/cocinas.html",
        "https://cr.epaenlinea.com/refrigeracion.html",
        "https://cr.epaenlinea.com/lavadoras.html",
        "https://cr.epaenlinea.com/televisores.html",
        "https://cr.epaenlinea.com/audio-y-video.html",
        "https://cr.epaenlinea.com/celulares.html",
        "https://cr.epaenlinea.com/laptops.html",
    ],
}

# Solo se persisten productos cuya categoría normalizada esté en este set.
CATEGORY_ALLOWLIST: set[str] = {
    "audio",
    "linea-blanca",
    "electrodomesticos",
    "celulares",
    "televisores",
    "cuidado-cabello",
    "videojuegos",
    "computacion",
}


# ---------------------------------------------------------------------------
# Resultado por tienda
# ---------------------------------------------------------------------------

@dataclass
class StoreResult:
    store_name: str
    new_products: int = 0
    prices_recorded: int = 0
    errors: int = 0
    elapsed_s: float = 0.0

    def ok(self) -> bool:
        return self.errors == 0


# ---------------------------------------------------------------------------
# Lógica de scraping por tienda
# ---------------------------------------------------------------------------

MIN_PRICE = 20_000  # Filtrar accesorios y productos baratos


def _process_product(store_id: int, data: dict) -> tuple[bool, bool]:
    """Filtra, normaliza y persiste un producto + precio.

    Returns (saved, is_new). saved=False significa filtrado o error.
    """
    data = dict(data)
    cat = data.get("category") or ""
    normalized = CATEGORY_NORMALIZE.get(cat, cat)
    data["category"] = normalized
    if normalized not in CATEGORY_ALLOWLIST:
        return False, False
    price = data.get("price") or 0
    if price < MIN_PRICE:
        return False, False
    try:
        _, is_new = save_product(store_id, data)
        return True, is_new
    except Exception as exc:
        log.error(
            "Error guardando producto sku=%s store_id=%d: %s",
            data.get("sku", "?"), store_id, exc,
        )
        return False


def run_store(store_id: int, store_name: str, scraper_type: str, base_url: str) -> StoreResult:
    result = StoreResult(store_name=store_name)
    t0 = time.monotonic()

    scraper_cls = SCRAPER_MAP.get(scraper_type)
    if scraper_cls is None:
        log.error("Tipo de scraper desconocido '%s' para tienda '%s'", scraper_type, store_name)
        result.errors += 1
        return result

    categories = STORE_CATEGORIES.get(store_name, [])
    if not categories:
        log.warning("Sin categorías configuradas para '%s' — se omite", store_name)
        return result

    scraper = scraper_cls(store_id, base_url)
    log.info("-- %s (%s)  categorias=%d", store_name, scraper_type, len(categories))

    for cat_url in categories:
        log.info("  Scrapeando categoría: %s", cat_url)
        try:
            products = scraper.scrape_category(cat_url)
        except Exception as exc:
            log.error("  Error scrapeando categoría %s: %s", cat_url, exc)
            result.errors += 1
            continue

        for data in products:
            saved, is_new = _process_product(store_id, data)
            if saved:
                if is_new:
                    result.new_products += 1
                result.prices_recorded += 1

    result.elapsed_s = time.monotonic() - t0
    log.info(
        "  OK %s  nuevos=%d  precios=%d  errores=%d  (%.0fs)",
        store_name, result.new_products, result.prices_recorded,
        result.errors, result.elapsed_s,
    )
    return result


# ---------------------------------------------------------------------------
# Punto de entrada
# ---------------------------------------------------------------------------

def run_all(store_names: list[str] | None = None) -> list[StoreResult]:
    """Ejecuta el scrape de todas las tiendas activas (o del subconjunto indicado).

    Params
    ------
    store_names : si se especifica, solo procesa las tiendas con esos nombres.
    """
    init_db()
    stores = get_active_stores()

    if store_names:
        stores = [s for s in stores if s["name"] in store_names]

    if not stores:
        log.warning("No hay tiendas activas que procesar")
        return

    log.info("=" * 55)
    log.info("Iniciando scrape: %d tienda(s)", len(stores))
    log.info("=" * 55)

    t_global = time.monotonic()
    results: list[StoreResult] = []

    for store in stores:
        res = run_store(
            store_id=store["id"],
            store_name=store["name"],
            scraper_type=store["scraper_type"],
            base_url=store["base_url"],
        )
        results.append(res)

    # -----------------------------------------------------------------------
    # Resumen final
    # -----------------------------------------------------------------------
    elapsed_total = time.monotonic() - t_global
    total_new   = sum(r.new_products    for r in results)
    total_prices= sum(r.prices_recorded for r in results)
    total_errors= sum(r.errors          for r in results)

    log.info("=" * 55)
    log.info("RESUMEN")
    log.info("  Tiendas procesadas : %d", len(results))
    log.info("  Productos nuevos   : %d", total_new)
    log.info("  Precios registrados: %d", total_prices)
    log.info("  Errores            : %d", total_errors)
    log.info("  Tiempo total       : %.0fs", elapsed_total)
    log.info("=" * 55)

    for r in results:
        status = "OK" if r.ok() else f"⚠ {r.errors} errores"
        log.info(
            "  %-14s  nuevos=%4d  precios=%4d  %s",
            r.store_name, r.new_products, r.prices_recorded, status,
        )
    log.info("=" * 55)
    return results


if __name__ == "__main__":
    import argparse
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )

    parser = argparse.ArgumentParser(description="Ejecuta scraping de precios")
    parser.add_argument(
        "stores", nargs="*",
        help="Nombre(s) de tienda a procesar (ej: Gollo 'Walmart CR'). "
             "Sin argumentos procesa todas.",
    )
    args = parser.parse_args()
    run_all(store_names=args.stores or None)
