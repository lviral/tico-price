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

# Categorías por nombre de tienda. Ajustar aquí cuando se agreguen tiendas.
STORE_CATEGORIES: dict[str, list[str]] = {
    "Gollo":      ["https://www.gollo.com/c/linea-blanca"],
    "Monge":      ["https://www.tiendamonge.com/hogar-y-linea-blanca"],
    "Verdugo":    ["https://www.verdugotienda.com/hogar-y-linea-blanca"],
    "Walmart CR": ["/electronica/linea-blanca"],
    "Siman CR":   ["/linea-blanca"],
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

def _process_product(store_id: int, data: dict) -> bool:
    """Persiste un producto + precio. Retorna True si fue exitoso."""
    try:
        save_product(store_id, data)
        return True
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
    log.info("── %s (%s)  categorías=%d", store_name, scraper_type, len(categories))

    for cat_url in categories:
        log.info("  Scrapeando categoría: %s", cat_url)
        try:
            products = scraper.scrape_category(cat_url)
        except Exception as exc:
            log.error("  Error scrapeando categoría %s: %s", cat_url, exc)
            result.errors += 1
            continue

        for data in products:
            try:
                _, is_new = save_product(store_id, data)
                if is_new:
                    result.new_products += 1
                result.prices_recorded += 1
            except Exception as exc:
                log.error(
                    "  Error guardando sku=%s: %s", data.get("sku", "?"), exc
                )
                result.errors += 1

    result.elapsed_s = time.monotonic() - t0
    log.info(
        "  ✓ %s  nuevos=%d  precios=%d  errores=%d  (%.0fs)",
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

    log.info("═" * 55)
    log.info("Iniciando scrape: %d tienda(s)", len(stores))
    log.info("═" * 55)

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

    log.info("═" * 55)
    log.info("RESUMEN")
    log.info("  Tiendas procesadas : %d", len(results))
    log.info("  Productos nuevos   : %d", total_new)
    log.info("  Precios registrados: %d", total_prices)
    log.info("  Errores            : %d", total_errors)
    log.info("  Tiempo total       : %.0fs", elapsed_total)
    log.info("═" * 55)

    for r in results:
        status = "OK" if r.ok() else f"⚠ {r.errors} errores"
        log.info(
            "  %-14s  nuevos=%4d  precios=%4d  %s",
            r.store_name, r.new_products, r.prices_recorded, status,
        )
    log.info("═" * 55)
    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Ejecuta scraping de precios")
    parser.add_argument(
        "stores", nargs="*",
        help="Nombre(s) de tienda a procesar (ej: Gollo 'Walmart CR'). "
             "Sin argumentos procesa todas.",
    )
    args = parser.parse_args()
    run_all(store_names=args.stores or None)
