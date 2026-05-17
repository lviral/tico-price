from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterator


@dataclass
class ProductData:
    sku: str
    name: str
    url: str
    price: float
    original_price: float | None
    discount_pct: float | None
    in_stock: bool
    category: str | None = None


class BaseScraper(ABC):
    def __init__(self, store_id: int, base_url: str) -> None:
        self.store_id = store_id
        self.base_url = base_url.rstrip("/")

    @abstractmethod
    def scrape_category(self, category_url: str) -> Iterator[ProductData]:
        """Yield ProductData for every product found at category_url."""

    @abstractmethod
    def scrape_product(self, product_url: str) -> ProductData:
        """Return ProductData for a single product page."""

    def _full_url(self, path: str) -> str:
        if path.startswith("http"):
            return path
        return f"{self.base_url}/{path.lstrip('/')}"
