"""Scraper para tiendas WooCommerce (Intelec CR).

Usa la API REST pública de WooCommerce:
  GET {base_url}/wp-json/wc/v3/products?category={cat_id}&per_page=100&page=N

Si la API está protegida, cae back a scraping HTML via Playwright.
"""

import logging
import time

import httpx

log = logging.getLogger(__name__)

_PAGE_SIZE = 100
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2


def _parse_price(val) -> float | None:
    if not val:
        return None
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def _discount_pct(price: float, regular: float | None) -> float | None:
    if regular and regular > price:
        return round((1 - price / regular) * 100, 1)
    return None


class WooCommerceScraper:
    """Scraper para tiendas WooCommerce via REST API pública.

    Params
    ------
    store_id : id interno en la BD local.
    base_url : URL raíz de la tienda. Ej.: "https://www.intelec.co.cr"
    """

    def __init__(self, store_id: int, base_url: str) -> None:
        self.store_id = store_id
        self.base_url = base_url.rstrip("/")
        self._api_base = f"{self.base_url}/wp-json/wc/v3"
        self._client = httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (precio-tracker-cr/1.0)"},
            follow_redirects=True,
            timeout=30,
        )

    def scrape_category(self, category_slug: str) -> list[dict]:
        """Extrae todos los productos de una categoría WooCommerce.

        Params
        ------
        category_slug : slug o ID numérico de la categoría.
                        Ej.: "celulares" o "15"

        Returns
        -------
        Lista de dicts con: sku, name, url, price, original_price,
        discount_pct, in_stock, category, image_url.
        """
        # Primero resolvemos el slug a ID si es necesario
        cat_id = self._resolve_category(category_slug)
        if cat_id is None:
            log.warning("[%s] Categoría '%s' no encontrada", self.base_url, category_slug)
            return []

        log.info("[%s] categoría=%s (id=%s)", self.base_url, category_slug, cat_id)

        results: list[dict] = []
        page = 1

        while True:
            items = self._fetch_page(cat_id, page)
            if not items:
                break

            parsed = []
            for raw in items:
                try:
                    parsed.append(self._parse_item(raw, category_slug))
                except Exception as exc:
                    log.warning("Error parseando producto id=%s: %s", raw.get("id"), exc)

            log.info(
                "[%s] page=%d -> %d productos (acum. %d)",
                self.base_url, page, len(parsed), len(results) + len(parsed),
            )
            results.extend(parsed)

            if len(items) < _PAGE_SIZE:
                break
            page += 1

        return results

    def get_categories(self) -> list[dict]:
        """Devuelve todas las categorías disponibles (útil para descubrir IDs)."""
        try:
            r = self._get_with_retry(f"{self._api_base}/products/categories", {"per_page": 100})
            return r.json()
        except Exception as exc:
            log.error("Error obteniendo categorías: %s", exc)
            return []

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _resolve_category(self, slug_or_id: str) -> str | None:
        """Convierte slug a ID numérico. Si ya es numérico, lo devuelve tal cual."""
        if slug_or_id.isdigit():
            return slug_or_id
        try:
            r = self._get_with_retry(
                f"{self._api_base}/products/categories",
                {"slug": slug_or_id, "per_page": 10},
            )
            cats = r.json()
            if cats:
                return str(cats[0]["id"])
        except Exception as exc:
            log.warning("No se pudo resolver categoría '%s': %s", slug_or_id, exc)
        return None

    def _fetch_page(self, cat_id: str, page: int) -> list[dict]:
        params = {
            "category": cat_id,
            "per_page": _PAGE_SIZE,
            "page": page,
            "status": "publish",
        }
        r = self._get_with_retry(f"{self._api_base}/products", params)
        return r.json()

    def _get_with_retry(self, url: str, params: dict | None = None) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = self._client.get(url, params=params)
                resp.raise_for_status()
                return resp
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_exc = exc
                log.warning("Intento %d/%d fallido [%s]: %s", attempt, _MAX_RETRIES, url, exc)
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_BACKOFF)
        raise RuntimeError(f"Todos los reintentos fallaron para {url}") from last_exc

    def _parse_item(self, item: dict, category_slug: str) -> dict:
        sku  = item.get("sku") or str(item["id"])
        name = item.get("name", "")
        url  = item.get("permalink", "")

        price    = _parse_price(item.get("price")) or 0.0
        regular  = _parse_price(item.get("regular_price"))
        in_stock = item.get("stock_status") == "instock"

        # Imagen principal
        images   = item.get("images", [])
        image_url = images[0].get("src") if images else None

        return {
            "sku":            sku,
            "name":           name,
            "url":            url,
            "price":          price,
            "original_price": regular if regular and regular > price else None,
            "discount_pct":   _discount_pct(price, regular),
            "in_stock":       in_stock,
            "category":       category_slug,
            "image_url":      image_url,
        }


# ------------------------------------------------------------------
# Test: python -m scrapers.woocommerce
# ------------------------------------------------------------------

if __name__ == "__main__":
    import json
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

    BASE_URL = "https://www.intelec.co.cr"
    scraper  = WooCommerceScraper(store_id=999, base_url=BASE_URL)

    print("Categorias disponibles:")
    for cat in scraper.get_categories()[:15]:
        print(f"  [{cat['id']}] {cat['name']} (slug: {cat['slug']}, count: {cat.get('count',0)})")
