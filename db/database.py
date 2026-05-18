import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

DB_PATH = Path(__file__).parent / "prices.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


@contextmanager
def get_db() -> Generator[sqlite3.Connection, None, None]:
    """Context manager que entrega una conexión con transacción automática.

    Hace commit al salir sin error, rollback si hay excepción.
    Úsalo así:
        with get_db() as conn:
            upsert_product(conn, ...)
            insert_price(conn, ...)
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.executescript(sql)  # executescript hace commit implícito
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Escritura — reciben una conexión abierta para compartir la transacción
# ---------------------------------------------------------------------------

def upsert_product(
    conn: sqlite3.Connection,
    store_id: int,
    sku: str,
    name: str,
    url: str,
    category: str | None = None,
) -> tuple[int, bool]:
    """Inserta o actualiza un producto.

    Returns
    -------
    (product_id, is_new)  —  is_new=True si se insertó por primera vez.
    """
    existing = conn.execute(
        "SELECT id FROM products WHERE store_id = ? AND sku = ?",
        (store_id, sku),
    ).fetchone()

    if existing:
        conn.execute(
            "UPDATE products SET name = ?, url = ?, category = ? WHERE id = ?",
            (name, url, category, existing["id"]),
        )
        return existing["id"], False

    cursor = conn.execute(
        "INSERT INTO products (store_id, sku, name, url, category) VALUES (?, ?, ?, ?, ?)",
        (store_id, sku, name, url, category),
    )
    return cursor.lastrowid, True


def insert_price(
    conn: sqlite3.Connection,
    product_id: int,
    price: float,
    original_price: float | None = None,
    discount_pct: float | None = None,
    in_stock: bool = True,
) -> None:
    conn.execute(
        """INSERT INTO price_history (product_id, price, original_price, discount_pct, in_stock)
           VALUES (?, ?, ?, ?, ?)""",
        (product_id, price, original_price, discount_pct, int(in_stock)),
    )


def save_product(store_id: int, data: dict) -> tuple[int, bool]:
    """Atomically upsert product + insert price in a single transaction.

    Returns
    -------
    (product_id, is_new)
    """
    with get_db() as conn:
        product_id, is_new = upsert_product(
            conn,
            store_id,
            data["sku"],
            data["name"],
            data["url"],
            data.get("category"),
        )
        insert_price(
            conn,
            product_id,
            price=data["price"],
            original_price=data.get("original_price"),
            discount_pct=data.get("discount_pct"),
            in_stock=data.get("in_stock", True),
        )
    return product_id, is_new


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def get_active_stores(scraper_type: str | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM stores WHERE active = 1"
    params: tuple = ()
    if scraper_type:
        sql += " AND scraper_type = ?"
        params = (scraper_type,)
    with get_db() as conn:
        return conn.execute(sql, params).fetchall()


def get_price_history(product_id: int, days: int = 30) -> list[sqlite3.Row]:
    """Retorna el historial de precios de los últimos `days` días."""
    sql = """
        SELECT ph.id, ph.price, ph.original_price, ph.discount_pct,
               ph.in_stock, ph.scraped_at
        FROM price_history ph
        WHERE ph.product_id = ?
          AND ph.scraped_at >= datetime('now', ? || ' days')
        ORDER BY ph.scraped_at DESC
    """
    with get_db() as conn:
        return conn.execute(sql, (product_id, f"-{days}")).fetchall()


def search_products(query: str) -> list[sqlite3.Row]:
    """Busca productos por nombre (LIKE) y devuelve cada uno con su último precio.

    Returns rows con columnas:
      product_id, sku, product_name, url, category,
      store_name, price, original_price, discount_pct, in_stock, scraped_at
    """
    sql = """
        SELECT
            p.id          AS product_id,
            p.sku,
            p.name        AS product_name,
            p.url,
            p.category,
            s.name        AS store_name,
            ph.price,
            ph.original_price,
            ph.discount_pct,
            ph.in_stock,
            ph.scraped_at
        FROM products p
        JOIN stores s ON s.id = p.store_id
        LEFT JOIN price_history ph ON ph.id = (
            SELECT id FROM price_history
            WHERE product_id = p.id
            ORDER BY scraped_at DESC, id DESC
            LIMIT 1
        )
        WHERE p.name LIKE ?
        ORDER BY ph.price ASC
    """
    with get_db() as conn:
        return conn.execute(sql, (f"%{query}%",)).fetchall()
