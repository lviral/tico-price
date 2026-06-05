"""Scraper para tiendas con plataforma VTEX (Walmart CR, Siman CR).

Consume el endpoint público de búsqueda de catálogo:
  GET {base_url}/api/catalog_system/pub/products/search
      ?fq=C:/{numeric_category_path}/&_from=N&_to=N+49&O=OrderByReleaseDateDESC

VTEX requiere IDs numéricos en el filtro fq. El árbol de categorías se
obtiene de:
  GET {base_url}/api/catalog_system/pub/category/tree/{depth}

Ejemplo Walmart CR:
  Electrónica (12) → Línea Blanca (61) → fq=C:/12/61/
"""

import logging
import time

import httpx

log = logging.getLogger(__name__)

_SEARCH_PATH = "/api/catalog_system/pub/products/search"
_TREE_PATH = "/api/catalog_system/pub/category/tree"
_PAGE_SIZE = 50
_MAX_RETRIES = 3
_RETRY_BACKOFF = 2  # segundos


def _parse_price(value: int | float | None) -> float | None:
    return float(value) if value is not None else None


def _discount_pct(price: float, list_price: float | None) -> float | None:
    if list_price and list_price > price:
        return round((1 - price / list_price) * 100, 1)
    return None


class VtexScraper:
    """Scraper para plataforma VTEX.

    Params
    ------
    store_id : id interno de la tienda en la BD local.
    base_url : URL raíz de la tienda, sin trailing slash.
               Ej.: "https://www.walmart.co.cr"
    """

    def __init__(self, store_id: int, base_url: str) -> None:
        self.store_id = store_id
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={
                "User-Agent": "Mozilla/5.0 (precio-tracker-cr/1.0)",
                "Accept": "application/json",
            },
            follow_redirects=True,
            timeout=30,
        )
        # cache: nombre_segmento_lower → id numérico
        self._cat_id_cache: dict[str, str] = {}

    # ------------------------------------------------------------------
    # Interfaz pública
    # ------------------------------------------------------------------

    def scrape_category(self, category_path: str) -> list[dict]:
        """Pagina de 50 en 50 hasta agotar resultados.

        Params
        ------
        category_path : ruta semántica o numérica.
                        Semántica: "/electronica/linea-blanca"
                        Numérica:  "/12/61"   (más rápido, sin resolución)

        Returns
        -------
        Lista de dicts con: sku, name, url, price, original_price,
        discount_pct, in_stock, category.
        """
        numeric_path = self._resolve_category_path(category_path)
        log.info("[%s] categoria=%s -> path numerico=%s", self.base_url, category_path, numeric_path)

        results: list[dict] = []
        from_idx = 0

        while True:
            to_idx = from_idx + _PAGE_SIZE - 1
            page = self._fetch_page(numeric_path, from_idx, to_idx)

            if not page:
                log.info(
                    "[%s] _from=%d → 0 productos, fin de paginación (total=%d)",
                    self.base_url, from_idx, len(results),
                )
                break

            parsed = []
            for raw in page:
                try:
                    parsed.append(self._parse_item(raw, category_path))
                except Exception as exc:
                    log.warning("Error parseando producto %s: %s", raw.get("productId"), exc)

            log.info(
                "[%s] _from=%d _to=%d -> %d productos (acum. %d)",
                self.base_url, from_idx, to_idx, len(parsed), len(results) + len(parsed),
            )

            results.extend(parsed)

            if len(page) < _PAGE_SIZE:
                break

            from_idx += _PAGE_SIZE

        return results

    def get_category_tree(self, depth: int = 3) -> list[dict]:
        """Devuelve el árbol de categorías de la tienda (útil para descubrir IDs)."""
        url = f"{self.base_url}{_TREE_PATH}/{depth}"
        resp = self._get_with_retry(url)
        return resp.json()

    # ------------------------------------------------------------------
    # Resolución de rutas semánticas → numéricas
    # ------------------------------------------------------------------

    def _resolve_category_path(self, path: str) -> str:
        """Convierte '/electronica/linea-blanca' al path numérico '/12/61'.

        Si el path ya contiene solo números y barras, lo devuelve tal cual.
        """
        segments = [s for s in path.strip("/").split("/") if s]

        if all(s.isdigit() for s in segments):
            return "/" + "/".join(segments)

        # Necesitamos el árbol para resolver
        tree = self.get_category_tree(depth=len(segments) + 1)
        numeric_ids: list[str] = []
        nodes = tree

        for seg in segments:
            node = self._find_node(nodes, seg)
            if node is None:
                log.warning(
                    "Segmento '%s' no encontrado en el árbol de categorías de %s. "
                    "Usando path semántico directo.",
                    seg, self.base_url,
                )
                return "/" + "/".join(segments)
            numeric_ids.append(str(node["id"]))
            nodes = node.get("children", [])

        return "/" + "/".join(numeric_ids)

    @staticmethod
    def _find_node(nodes: list[dict], segment: str) -> dict | None:
        """Busca un nodo por nombre o por slug extraído de su URL."""
        seg_lower = segment.lower().replace("-", " ")
        for node in nodes:
            name_lower = node.get("name", "").lower()
            url_slug = node.get("url", "").rstrip("/").split("/")[-1].lower()
            if name_lower == seg_lower or url_slug == segment.lower():
                return node
        # Búsqueda difusa: contiene el segmento
        for node in nodes:
            if seg_lower in node.get("name", "").lower():
                return node
        return None

    # ------------------------------------------------------------------
    # HTTP y parsing
    # ------------------------------------------------------------------

    def _fetch_page(self, numeric_path: str, from_idx: int, to_idx: int) -> list[dict]:
        url = f"{self.base_url}{_SEARCH_PATH}"
        params = {
            "fq": f"C:{numeric_path}/",
            "_from": from_idx,
            "_to": to_idx,
            "O": "OrderByReleaseDateDESC",
        }
        resp = self._get_with_retry(url, params=params)
        return resp.json()

    def _get_with_retry(self, url: str, params: dict | None = None) -> httpx.Response:
        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                resp = self._client.get(url, params=params)
                resp.raise_for_status()
                return resp
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                last_exc = exc
                log.warning(
                    "Intento %d/%d fallido [%s]: %s",
                    attempt, _MAX_RETRIES, url, exc,
                )
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_BACKOFF)

        raise RuntimeError(f"Todos los reintentos fallaron para {url}") from last_exc

    def _parse_item(self, item: dict, category_path: str) -> dict:
        sku = str(item["productId"])
        name = item["productName"]
        link_text = item.get("linkText", "")
        url = f"{self.base_url}/{link_text}/p"

        items_list = item.get("items", [{}])
        first_item = items_list[0] if items_list else {}

        offer = (
            first_item
            .get("sellers", [{}])[0]
            .get("commertialOffer", {})
        )
        price = _parse_price(offer.get("Price")) or 0.0
        original_price = _parse_price(offer.get("ListPrice"))
        in_stock: bool = bool(offer.get("IsAvailable", False))

        category = category_path.strip("/").split("/")[-1]

        # Imagen: primera imagen del primer ítem
        images = first_item.get("images", [])
        image_url: str | None = images[0].get("imageUrl") if images else None

        return {
            "sku": sku,
            "name": name,
            "url": url,
            "price": price,
            "original_price": original_price,
            "discount_pct": _discount_pct(price, original_price),
            "in_stock": in_stock,
            "category": category,
            "image_url": image_url,
        }


# ------------------------------------------------------------------
# Test: python -m scrapers.vtex
# ------------------------------------------------------------------

if __name__ == "__main__":
    import json

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    BASE_URL = "https://www.walmart.co.cr"
    CATEGORY = "/electronica/linea-blanca"

    scraper = VtexScraper(store_id=4, base_url=BASE_URL)
    productos = scraper.scrape_category(CATEGORY)

    print(f"\nTotal encontrados: {len(productos)}")
    print("\n--- Primeros 5 resultados ---")
    for p in productos[:5]:
        print(json.dumps(p, ensure_ascii=False, indent=2))
