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
        conn.executescript(sql)
        # Migraciones para BDs existentes (ALTER TABLE no soporta IF NOT EXISTS)
        for migration in [
            "ALTER TABLE stores ADD COLUMN status TEXT NOT NULL DEFAULT 'active' "
            "CHECK (status IN ('active', 'requires_attention'))",
        ]:
            try:
                conn.execute(migration)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # la columna ya existe
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

def record_scrape_run(
    store_id: int,
    started_at: str,
    finished_at: str,
    success: bool,
    new_products: int = 0,
    prices_added: int = 0,
    errors: int = 0,
) -> None:
    """Registra el resultado de un scrape de tienda en scrape_runs."""
    with get_db() as conn:
        conn.execute(
            """INSERT INTO scrape_runs
               (store_id, started_at, finished_at, success, new_products, prices_added, errors)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (store_id, started_at, finished_at, int(success),
             new_products, prices_added, errors),
        )


def get_consecutive_failures(store_id: int, n: int = 3) -> int:
    """Retorna cuántos de los últimos `n` runs terminaron en fallo (success=0)."""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT success FROM scrape_runs
               WHERE store_id = ?
               ORDER BY started_at DESC, id DESC
               LIMIT ?""",
            (store_id, n),
        ).fetchall()
    if len(rows) < n:
        return 0
    return sum(1 for r in rows if r["success"] == 0)


def mark_store_attention(store_id: int) -> None:
    """Marca una tienda como requires_attention."""
    with get_db() as conn:
        conn.execute(
            "UPDATE stores SET status = 'requires_attention' WHERE id = ?",
            (store_id,),
        )


def reset_store_status(store_id: int) -> None:
    """Restablece el status de una tienda a 'active' tras un scrape exitoso."""
    with get_db() as conn:
        conn.execute(
            "UPDATE stores SET status = 'active' WHERE id = ?",
            (store_id,),
        )


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


def search_products(
    query: str,
    category: str | None = None,
    store: str | None = None,
) -> list[sqlite3.Row]:
    """Busca productos con filtros opcionales.

    Columnas retornadas:
      product_id, sku, product_name, url, category,
      store_name, price, original_price, discount_pct, in_stock, scraped_at
    """
    conditions = ["p.name LIKE ?"]
    params: list = [f"%{query}%"]

    if category:
        conditions.append("p.category LIKE ?")
        params.append(f"%{category}%")
    if store:
        conditions.append("s.name LIKE ?")
        params.append(f"%{store}%")

    where = " AND ".join(conditions)
    sql = f"""
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
        WHERE {where}
        ORDER BY ph.price ASC
    """
    with get_db() as conn:
        return conn.execute(sql, params).fetchall()


def get_product_with_stats(product_id: int, days: int = 90) -> sqlite3.Row | None:
    """Retorna un producto con sus stats de precio de los últimos `days` días.

    Columnas: product_id, product_name, url, category, store_name,
              current_price, original_price, discount_pct, in_stock, scraped_at,
              price_min, price_max, price_avg, sample_count
    """
    sql = """
        SELECT
            p.id          AS product_id,
            p.name        AS product_name,
            p.url,
            p.category,
            s.name        AS store_name,
            latest.price         AS current_price,
            latest.original_price,
            latest.discount_pct,
            latest.in_stock,
            latest.scraped_at,
            stats.price_min,
            stats.price_max,
            stats.price_avg,
            stats.sample_count
        FROM products p
        JOIN stores s ON s.id = p.store_id
        JOIN (
            SELECT price, original_price, discount_pct, in_stock, scraped_at
            FROM price_history
            WHERE product_id = ?
            ORDER BY scraped_at DESC, id DESC
            LIMIT 1
        ) latest
        JOIN (
            SELECT
                MIN(price)   AS price_min,
                MAX(price)   AS price_max,
                AVG(price)   AS price_avg,
                COUNT(*)     AS sample_count
            FROM price_history
            WHERE product_id = ?
              AND scraped_at >= datetime('now', ? || ' days')
        ) stats
        WHERE p.id = ?
    """
    with get_db() as conn:
        return conn.execute(sql, (product_id, product_id, f"-{days}", product_id)).fetchone()


def get_deals(limit: int = 50) -> list[sqlite3.Row]:
    """Productos donde el descuento anunciado no coincide con la bajada real de precio.

    Calcula:
      - advertised_discount : discount_pct del último registro (vs original_price)
      - real_discount        : (max_price_90d - current_price) / max_price_90d * 100
      - deception_gap        : advertised_discount - real_discount
                               (positivo = el anuncio exagera el descuento)

    Solo incluye productos con descuento anunciado y ≥ 3 registros históricos.

    Columnas: product_id, product_name, url, category, store_name,
              current_price, original_price, advertised_discount,
              real_discount, deception_gap, price_max_90d, sample_count
    """
    sql = """
        SELECT
            p.id    AS product_id,
            p.name  AS product_name,
            p.url,
            p.category,
            s.name  AS store_name,
            latest.price              AS current_price,
            latest.original_price,
            latest.discount_pct       AS advertised_discount,
            ROUND(
                (stats.price_max - latest.price) * 100.0 / stats.price_max,
                1
            )                         AS real_discount,
            ROUND(
                latest.discount_pct
                - (stats.price_max - latest.price) * 100.0 / stats.price_max,
                1
            )                         AS deception_gap,
            stats.price_max           AS price_max_90d,
            stats.sample_count
        FROM products p
        JOIN stores s ON s.id = p.store_id
        JOIN (
            SELECT product_id, price, original_price, discount_pct
            FROM price_history
            WHERE id IN (
                SELECT MAX(id) FROM price_history GROUP BY product_id
            )
        ) latest ON latest.product_id = p.id
        JOIN (
            SELECT
                product_id,
                MAX(price)  AS price_max,
                COUNT(*)    AS sample_count
            FROM price_history
            WHERE scraped_at >= datetime('now', '-90 days')
            GROUP BY product_id
        ) stats ON stats.product_id = p.id
        WHERE latest.discount_pct IS NOT NULL
          AND latest.discount_pct > 0
          AND stats.sample_count >= 3
        ORDER BY deception_gap DESC
        LIMIT ?
    """
    with get_db() as conn:
        return conn.execute(sql, (limit,)).fetchall()


def get_stores_summary() -> list[sqlite3.Row]:
    """Lista todas las tiendas con total de productos y fecha del último scrape.

    Columnas: id, name, base_url, scraper_type, active,
              total_products, last_scraped_at
    """
    sql = """
        SELECT
            s.id,
            s.name,
            s.base_url,
            s.scraper_type,
            s.active,
            COUNT(DISTINCT p.id)  AS total_products,
            MAX(ph.scraped_at)    AS last_scraped_at
        FROM stores s
        LEFT JOIN products p     ON p.store_id  = s.id
        LEFT JOIN price_history ph ON ph.product_id = p.id
        GROUP BY s.id
        ORDER BY s.name
    """
    with get_db() as conn:
        return conn.execute(sql).fetchall()
