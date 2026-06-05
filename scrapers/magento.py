"""Scraper para tiendas Magento 2 con Playwright headless (Gollo, Monge, Verdugo).

Estrategia de precios:
  - data-price-amount en .price-wrapper[data-price-type='finalPrice'] → precio actual
  - data-price-amount en .price-wrapper[data-price-type='oldPrice']   → precio original
  Usar el atributo numérico evita parsear el símbolo ₡ y los separadores de miles.

Paginación:
  - Sigue a.action.next mientras exista.
  - Monge y Verdugo caben en una sola página (no hay next link → termina naturalmente).
"""

import logging
import math
import random
import time

from bs4 import BeautifulSoup
from playwright.sync_api import Page, TimeoutError as PWTimeout, sync_playwright

log = logging.getLogger(__name__)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
_WAIT_SELECTOR = "li.product-item"
_WAIT_TIMEOUT_MS = 15_000
_NAV_TIMEOUT_MS = 30_000


def _price_from_attr(value: str | None) -> float | None:
    """Convierte el atributo data-price-amount a float redondeado al entero."""
    if not value:
        return None
    try:
        return float(math.ceil(float(value)))
    except ValueError:
        return None


def _discount_pct(price: float, original: float | None) -> float | None:
    if original and original > price:
        return round((1 - price / original) * 100, 1)
    return None


class MagentoScraper:
    """Scraper Playwright para tiendas Magento 2.

    Params
    ------
    store_id : id interno en la BD local.
    base_url : URL raíz de la tienda. Ej.: "https://www.gollo.com"
    """

    def __init__(self, store_id: int, base_url: str) -> None:
        self.store_id = store_id
        self.base_url = base_url.rstrip("/")

    # ------------------------------------------------------------------
    # Interfaz pública
    # ------------------------------------------------------------------

    def scrape_category(self, category_url: str) -> list[dict]:
        """Extrae todos los productos de una URL de categoría, paginando automáticamente.

        Returns
        -------
        Lista de dicts con: sku, name, url, price, original_price,
        discount_pct, in_stock, category.
        """
        url = category_url if category_url.startswith("http") else f"{self.base_url}{category_url}"
        category = url.rstrip("/").split("/")[-1].split("?")[0]
        results: list[dict] = []

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(user_agent=_UA)
            page = context.new_page()

            page_num = 1
            current_url: str | None = url

            while current_url:
                products, next_url = self._scrape_page(page, current_url, category, page_num)
                results.extend(products)
                log.info(
                    "[%s] pág=%d  url=%s  productos=%d (acum. %d)",
                    self.base_url, page_num, current_url, len(products), len(results),
                )

                if next_url:
                    delay = random.uniform(1, 3)
                    log.debug("Esperando %.1fs antes de siguiente página", delay)
                    time.sleep(delay)

                current_url = next_url
                page_num += 1

            browser.close()

        return results

    # ------------------------------------------------------------------
    # Internos
    # ------------------------------------------------------------------

    def _scrape_page(
        self, page: Page, url: str, category: str, page_num: int
    ) -> tuple[list[dict], str | None]:
        """Carga una página, extrae productos y devuelve el URL de la siguiente."""
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=_NAV_TIMEOUT_MS)
            page.wait_for_selector(_WAIT_SELECTOR, timeout=_WAIT_TIMEOUT_MS)
        except PWTimeout:
            log.warning("Timeout cargando página %d (%s) — se omite", page_num, url)
            return [], None
        except Exception as exc:
            log.error("Error cargando página %d (%s): %s — se omite", page_num, url, exc)
            return [], None

        html = page.content()
        soup = BeautifulSoup(html, "html.parser")

        products = []
        for card in soup.select("li.product-item"):
            try:
                products.append(self._parse_card(card, category))
            except Exception as exc:
                log.debug("Error parseando card: %s", exc)

        next_tag = soup.select_one("a.action.next")
        next_url = next_tag["href"] if next_tag else None

        return products, next_url

    def _parse_card(self, card: BeautifulSoup, category: str) -> dict:
        # Nombre y URL del producto
        link = card.select_one("a.product-item-link")
        name = link.get_text(strip=True)
        product_url = link["href"]
        if not product_url.startswith("http"):
            product_url = f"{self.base_url}/{product_url.lstrip('/')}"

        # SKU desde el price-box (más confiable que data-product-id en el li)
        price_box = card.select_one(".price-box[data-product-id]")
        sku = price_box["data-product-id"] if price_box else product_url.split("/")[-1]

        # Precios via data-price-amount (evita parsear ₡ y puntos de miles)
        final_pw = card.select_one(".price-wrapper[data-price-type='finalPrice']")
        old_pw = card.select_one(".price-wrapper[data-price-type='oldPrice']")

        price = _price_from_attr(final_pw.get("data-price-amount") if final_pw else None) or 0.0
        original_price = _price_from_attr(old_pw.get("data-price-amount") if old_pw else None)

        # Stock: Magento oculta out-of-stock por defecto; verificar indicador explícito
        unavailable = card.select_one("[class*='unavailable'], [class*='out-of-stock']")
        in_stock = unavailable is None

        # Imagen del producto (data-src para lazy-load, src como fallback)
        img_tag = card.select_one("img.product-image-photo")
        image_url: str | None = None
        if img_tag:
            image_url = img_tag.get("data-src") or img_tag.get("src")
            # Descartar placeholders pequeños (base64 o "placeholder")
            if image_url and ("placeholder" in image_url or image_url.startswith("data:")):
                image_url = None

        return {
            "sku": str(sku),
            "name": name,
            "url": product_url,
            "price": price,
            "original_price": original_price,
            "discount_pct": _discount_pct(price, original_price),
            "in_stock": in_stock,
            "category": category,
            "image_url": image_url,
        }


# ------------------------------------------------------------------
# Test: python -m scrapers.magento
# ------------------------------------------------------------------

if __name__ == "__main__":
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    BASE_URL = "https://www.gollo.com"
    CATEGORY = "/c/linea-blanca"

    scraper = MagentoScraper(store_id=1, base_url=BASE_URL)
    productos = scraper.scrape_category(CATEGORY)

    print(f"\nTotal encontrados: {len(productos)}")
    print("\n--- Primeros 5 resultados ---")
    for p in productos[:5]:
        print(json.dumps(p, ensure_ascii=False, indent=2))
