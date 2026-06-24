"""Scraper para PriceSmart CR via Bloomreach Discovery API.

El sitio es Vue Storefront 2 / Nuxt.js; los productos se cargan desde:
  POST https://www.pricesmart.com/api/br_discovery/getProductsByKeyword

No se necesita Playwright — la API devuelve JSON directamente.
El precio viene en price_CR con fractionDigits=2 (dividir por 100 para obtener CRC).
"""

import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import json

log = logging.getLogger(__name__)

_API_URL = "https://www.pricesmart.com/api/br_discovery/getProductsByKeyword"
_PRODUCT_URL_BASE = "https://www.pricesmart.com/es-cr/producto"
_ROWS_PER_PAGE = 24
_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36 TicoPrice/1.0 (+https://ticoprice.app)"
)
# Bloomreach credentials — set via env vars; defaults are the values embedded in frontend JS
_ACCOUNT_ID = os.getenv("BLOOMREACH_ACCOUNT_ID", "7024")
_AUTH_KEY = os.getenv("BLOOMREACH_AUTH_KEY", "ev7libhybjg5h1d1")
_DOMAIN_KEY = os.getenv("BLOOMREACH_DOMAIN_KEY", "pricesmart_bloomreach_io_es")
_VIEW_ID = os.getenv("BLOOMREACH_VIEW_ID", "CR")
_FL = (
    "pid,title,price_CR,thumb_image,brand,slug,"
    "master_sku,availability_CR,fractionDigits,currency"
)


def _cat_code_from_url(url: str) -> str:
    """Extrae el código de categoría del último segmento de la URL.

    https://www.pricesmart.com/es-cr/categoria/Electronicos-E10D24/E10D24
    → 'E10D24'
    """
    return url.rstrip("/").rsplit("/", 1)[-1]


def _cat_slug_from_url(url: str) -> str:
    """Extrae el slug de categoría del penúltimo segmento y lo pasa a minúsculas.

    https://www.pricesmart.com/es-cr/categoria/Electronicos-E10D24/E10D24
    → 'electronicos-e10d24'
    """
    parts = url.rstrip("/").split("/")
    return parts[-2].lower() if len(parts) >= 2 else "desconocido"


class PriceSmartScraper:
    """Scraper HTTP para PriceSmart CR usando Bloomreach Discovery API."""

    def __init__(self, store_id: int, base_url: str) -> None:
        self.store_id = store_id
        self.base_url = base_url

    def _post(self, payload: list) -> dict:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            _API_URL,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json, text/plain, */*",
                "User-Agent": _UA,
                "Referer": self.base_url,
                "Accept-Language": "es-CR,es;q=0.9",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def scrape_category(self, cat_url: str) -> list[dict]:
        cat_code = _cat_code_from_url(cat_url)
        cat_slug = _cat_slug_from_url(cat_url)
        products: list[dict] = []
        start = 0

        while True:
            payload = [{
                "url": cat_url,
                "start": start,
                "q": cat_code,
                "fq": [],
                "search_type": "category",
                "rows": _ROWS_PER_PAGE,
                "account_id": _ACCOUNT_ID,
                "auth_key": _AUTH_KEY,
                "request_id": int(time.time() * 1000),
                "domain_key": _DOMAIN_KEY,
                "fl": _FL,
                "view_id": _VIEW_ID,
            }]

            try:
                resp = self._post(payload)
            except urllib.error.HTTPError as exc:
                log.error("PriceSmart API HTTP %s para %s", exc.code, cat_url)
                break
            except Exception as exc:
                log.error("PriceSmart API error para %s: %s", cat_url, exc)
                break

            result = resp.get("response", {})
            num_found = result.get("numFound", 0)
            docs = result.get("docs", [])

            if not docs:
                break

            for doc in docs:
                price_raw = doc.get("price_CR") or doc.get("price") or 0
                fraction = doc.get("fractionDigits", 2)
                price = price_raw / (10 ** fraction) if price_raw else 0

                slug = doc.get("slug", "")
                pid = doc.get("pid", "") or doc.get("master_sku", "")
                url = f"{_PRODUCT_URL_BASE}/{slug}" if slug else f"{_PRODUCT_URL_BASE}/{pid}"

                products.append({
                    "sku": str(pid),
                    "name": (doc.get("title") or "").strip(),
                    "price": price,
                    "original_price": None,
                    "discount_pct": None,
                    "url": url,
                    "image_url": doc.get("thumb_image"),
                    "category": cat_slug,
                    "in_stock": doc.get("availability_CR", "true") == "true",
                })

            start += len(docs)
            log.debug("  PriceSmart %s: %d/%d", cat_code, start, num_found)

            if start >= num_found:
                break

            time.sleep(0.3)

        log.info("  PriceSmart %s: %d productos", cat_code, len(products))
        return products
