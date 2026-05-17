import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "prices.db"
SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    sql = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as conn:
        conn.executescript(sql)


def upsert_product(store_id: int, sku: str, name: str, url: str, category: str | None = None) -> int:
    sql = """
        INSERT INTO products (store_id, sku, name, url, category)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT (store_id, sku) DO UPDATE SET
            name     = excluded.name,
            url      = excluded.url,
            category = excluded.category
        RETURNING id
    """
    with get_connection() as conn:
        row = conn.execute(sql, (store_id, sku, name, url, category)).fetchone()
        return row["id"]


def insert_price(
    product_id: int,
    price: float,
    original_price: float | None = None,
    discount_pct: float | None = None,
    in_stock: bool = True,
) -> None:
    sql = """
        INSERT INTO price_history (product_id, price, original_price, discount_pct, in_stock)
        VALUES (?, ?, ?, ?, ?)
    """
    with get_connection() as conn:
        conn.execute(sql, (product_id, price, original_price, discount_pct, int(in_stock)))


def get_active_stores(scraper_type: str | None = None) -> list[sqlite3.Row]:
    sql = "SELECT * FROM stores WHERE active = 1"
    params: tuple = ()
    if scraper_type:
        sql += " AND scraper_type = ?"
        params = (scraper_type,)
    with get_connection() as conn:
        return conn.execute(sql, params).fetchall()


def get_price_history(product_id: int, limit: int = 90) -> list[sqlite3.Row]:
    sql = """
        SELECT * FROM price_history
        WHERE product_id = ?
        ORDER BY scraped_at DESC
        LIMIT ?
    """
    with get_connection() as conn:
        return conn.execute(sql, (product_id, limit)).fetchall()
