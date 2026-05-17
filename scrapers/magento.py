import re
from typing import Iterator

import httpx
from bs4 import BeautifulSoup

from .base import BaseScraper, ProductData

_PRICE_RE = re.compile(r"[\d,]+\.?\d*")


def _parse_price(text: str) -> float | None:
    text = text.replace("\xa0", "").replace(",", "")
    match = _PRICE_RE.search(text)
    return float(match.group()) if match else None


class MagentoScraper(BaseScraper):
    """Scraper for Magento 2 storefronts (Gollo, Monge, Verdugo)."""

    def __init__(self, store_id: int, base_url: str) -> None:
        super().__init__(store_id, base_url)
        self._client = httpx.Client(
            headers={"User-Agent": "Mozilla/5.0 (precio-tracker-cr/1.0)"},
            follow_redirects=True,
            timeout=30,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def scrape_category(self, category_url: str) -> Iterator[ProductData]:
        url = self._full_url(category_url)
        while url:
            soup, next_url = self._fetch_page(url)
            yield from self._parse_listing(soup)
            url = next_url

    def scrape_product(self, product_url: str) -> ProductData:
        url = self._full_url(product_url)
        resp = self._client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        return self._parse_detail(soup, url)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _fetch_page(self, url: str) -> tuple[BeautifulSoup, str | None]:
        resp = self._client.get(url)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        next_tag = soup.select_one("a.action.next")
        next_url = next_tag["href"] if next_tag else None
        return soup, next_url

    def _parse_listing(self, soup: BeautifulSoup) -> Iterator[ProductData]:
        for item in soup.select("li.product-item"):
            try:
                yield self._extract_card(item)
            except Exception:
                continue

    def _extract_card(self, item: BeautifulSoup) -> ProductData:
        name_tag = item.select_one(".product-item-name a")
        name = name_tag.get_text(strip=True)
        url = name_tag["href"]

        sku_tag = item.select_one("[data-product-id]")
        sku = sku_tag["data-product-id"] if sku_tag else url.split("/")[-1]

        price_tag = item.select_one(".price-box .price")
        price = _parse_price(price_tag.get_text()) if price_tag else 0.0

        old_tag = item.select_one(".price-box .old-price .price")
        original_price = _parse_price(old_tag.get_text()) if old_tag else None
        discount_pct = _calc_discount(price, original_price)

        in_stock = item.select_one(".stock.unavailable") is None

        category_tag = item.select_one("[data-category]")
        category = category_tag["data-category"] if category_tag else None

        return ProductData(
            sku=str(sku),
            name=name,
            url=url,
            price=price,
            original_price=original_price,
            discount_pct=discount_pct,
            in_stock=in_stock,
            category=category,
        )

    def _parse_detail(self, soup: BeautifulSoup, url: str) -> ProductData:
        name = soup.select_one(".page-title span").get_text(strip=True)

        sku_tag = soup.select_one('[itemprop="sku"]')
        sku = sku_tag.get_text(strip=True) if sku_tag else url.split("/")[-1]

        price_tag = soup.select_one(".price-box .price")
        price = _parse_price(price_tag.get_text()) if price_tag else 0.0

        old_tag = soup.select_one(".price-box .old-price .price")
        original_price = _parse_price(old_tag.get_text()) if old_tag else None
        discount_pct = _calc_discount(price, original_price)

        in_stock = soup.select_one(".stock.unavailable") is None

        breadcrumb = soup.select(".breadcrumbs .item")
        category = breadcrumb[-2].get_text(strip=True) if len(breadcrumb) >= 2 else None

        return ProductData(
            sku=str(sku),
            name=name,
            url=url,
            price=price,
            original_price=original_price,
            discount_pct=discount_pct,
            in_stock=in_stock,
            category=category,
        )


def _calc_discount(price: float, original: float | None) -> float | None:
    if original and original > price:
        return round((1 - price / original) * 100, 1)
    return None
