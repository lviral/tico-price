import re
from typing import Iterator

import httpx

from .base import BaseScraper, ProductData

_VTEX_SEARCH_PATH = "/api/catalog_system/pub/products/search"
_PAGE_SIZE = 50


def _parse_price(value: int | float | None) -> float | None:
    return float(value) if value is not None else None


class VtexScraper(BaseScraper):
    """Scraper for VTEX storefronts (Walmart CR, Siman CR).

    Uses the VTEX Catalog Search API instead of HTML parsing.
    """

    def __init__(self, store_id: int, base_url: str) -> None:
        super().__init__(store_id, base_url)
        self._client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (precio-tracker-cr/1.0)",
                "Accept": "application/json",
            },
            follow_redirects=True,
            timeout=30,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def scrape_category(self, category_path: str) -> Iterator[ProductData]:
        """category_path: e.g. '/electrodomesticos' or a VTEX category ID."""
        from_idx = 0
        while True:
            items = self._search(category_path, from_idx, from_idx + _PAGE_SIZE - 1)
            if not items:
                break
            for item in items:
                try:
                    yield self._parse_item(item)
                except Exception:
                    continue
            from_idx += _PAGE_SIZE

    def scrape_product(self, product_url: str) -> ProductData:
        # Resolve the product slug to a VTEX product via the search API
        slug = product_url.rstrip("/").split("/")[-1]
        url = f"{self.base_url}{_VTEX_SEARCH_PATH}"
        params = {"fq": f"alternateIds_RefId:{slug}", "_from": 0, "_to": 0}
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        items = resp.json()
        if not items:
            raise ValueError(f"Product not found: {product_url}")
        return self._parse_item(items[0])

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _search(self, category_path: str, from_idx: int, to_idx: int) -> list[dict]:
        url = f"{self.base_url}{_VTEX_SEARCH_PATH}"
        # Strip leading slash for the fq filter
        cat = re.sub(r"^/", "", category_path)
        params = {
            "fq": f"C:/{cat}/",
            "_from": from_idx,
            "_to": to_idx,
            "O": "OrderByTopSaleDESC",
        }
        resp = self._client.get(url, params=params)
        resp.raise_for_status()
        return resp.json()

    def _parse_item(self, item: dict) -> ProductData:
        sku_id = str(item.get("productId", ""))
        name = item.get("productName", "")
        link = item.get("link", "")
        category = item.get("categories", [None])[0]
        if category:
            category = category.strip("/").split("/")[-1]

        # Pick the first available SKU for pricing
        skus: list[dict] = item.get("items", [{}])
        sku_data = skus[0] if skus else {}
        sellers: list[dict] = sku_data.get("sellers", [{}])
        offer = sellers[0].get("commertialOffer", {}) if sellers else {}

        price = _parse_price(offer.get("Price")) or 0.0
        list_price = _parse_price(offer.get("ListPrice"))
        discount_pct: float | None = None
        if list_price and list_price > price:
            discount_pct = round((1 - price / list_price) * 100, 1)

        in_stock = int(offer.get("AvailableQuantity", 0)) > 0

        return ProductData(
            sku=sku_id,
            name=name,
            url=self._full_url(link),
            price=price,
            original_price=list_price,
            discount_pct=discount_pct,
            in_stock=in_stock,
            category=category,
        )
