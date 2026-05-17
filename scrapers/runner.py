"""Entry point for running scrapers against all active stores."""

import logging
from typing import Sequence

from db.database import get_active_stores, init_db, insert_price, upsert_product
from scrapers.base import BaseScraper, ProductData
from scrapers.magento import MagentoScraper
from scrapers.vtex import VtexScraper

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("runner")

# Map each store's scraper_type to its class
_SCRAPER_MAP: dict[str, type[BaseScraper]] = {
    "magento": MagentoScraper,
    "vtex": VtexScraper,
}

# Default category paths to scrape per scraper type (override as needed)
_DEFAULT_CATEGORIES: dict[str, list[str]] = {
    "magento": ["/electrodomesticos", "/linea-blanca", "/tecnologia"],
    "vtex": ["/electrodomesticos", "/linea-blanca", "/tecnologia"],
}


def _save_product(store_id: int, data: ProductData) -> None:
    product_id = upsert_product(store_id, data.sku, data.name, data.url, data.category)
    insert_price(
        product_id,
        price=data.price,
        original_price=data.original_price,
        discount_pct=data.discount_pct,
        in_stock=data.in_stock,
    )


def run_store(store_id: int, scraper_type: str, base_url: str, categories: Sequence[str]) -> None:
    scraper_cls = _SCRAPER_MAP.get(scraper_type)
    if scraper_cls is None:
        log.warning("Unknown scraper type '%s' for store %d — skipped", scraper_type, store_id)
        return

    scraper = scraper_cls(store_id, base_url)
    total = 0
    for cat in categories:
        log.info("Scraping store_id=%d category=%s", store_id, cat)
        try:
            for product in scraper.scrape_category(cat):
                _save_product(store_id, product)
                total += 1
        except Exception as exc:
            log.error("Error scraping category %s: %s", cat, exc)

    log.info("store_id=%d done — %d products saved", store_id, total)


def run_all(categories: dict[str, list[str]] | None = None) -> None:
    """Scrape every active store.

    categories: optional override mapping scraper_type -> list of category paths.
    """
    init_db()
    effective_cats = categories or _DEFAULT_CATEGORIES
    stores = get_active_stores()
    log.info("Starting run for %d active stores", len(stores))

    for store in stores:
        cats = effective_cats.get(store["scraper_type"], [])
        run_store(store["id"], store["scraper_type"], store["base_url"], cats)

    log.info("All stores done")


if __name__ == "__main__":
    run_all()
