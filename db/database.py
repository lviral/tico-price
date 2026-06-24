import logging
import os
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Generator

log = logging.getLogger(__name__)

DB_PATH = Path(os.getenv("DB_PATH", str(Path(__file__).parent / "prices.db")))
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
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA wal_autocheckpoint = 500")
        conn.executescript(sql)
        # Migraciones para BDs existentes (ALTER TABLE no soporta IF NOT EXISTS)
        for migration in [
            "ALTER TABLE stores ADD COLUMN status TEXT NOT NULL DEFAULT 'active' "
            "CHECK (status IN ('active', 'requires_attention'))",
            "ALTER TABLE products ADD COLUMN image_url TEXT",
            "ALTER TABLE products ADD COLUMN last_seen_at TEXT",
            "ALTER TABLE products ADD COLUMN status TEXT NOT NULL DEFAULT 'active' "
            "CHECK (status IN ('active', 'discontinued'))",
        ]:
            try:
                conn.execute(migration)
                conn.commit()
            except sqlite3.OperationalError:
                pass  # la columna ya existe

        # Backfill last_seen_at: poblar desde MAX(scraped_at) de price_history para
        # productos existentes donde todavía es NULL (primera vez que corre esta migración)
        try:
            conn.execute("""
                UPDATE products
                SET last_seen_at = (
                    SELECT MAX(scraped_at) FROM price_history
                    WHERE product_id = products.id
                )
                WHERE last_seen_at IS NULL
            """)
            conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migración FTS5: recrear índice standalone si existe como content table
        try:
            schema_row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE name = 'products_fts'"
            ).fetchone()
            is_content_table = (
                schema_row is not None and "content" in (schema_row["sql"] or "").lower()
            )
            if is_content_table:
                # Eliminar tabla y triggers del schema viejo
                for obj in ["products_fts_ai", "products_fts_au", "products_fts_ad"]:
                    conn.execute(f"DROP TRIGGER IF EXISTS {obj}")
                conn.execute("DROP TABLE IF EXISTS products_fts")
                conn.commit()

            # Crear tabla y triggers (CREATE ... IF NOT EXISTS en schema.sql ya los define;
            # aquí los creamos manualmente para la migración sobre BD existente)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
                    name,
                    tokenize = "unicode61 remove_diacritics 2"
                )
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS products_fts_ai AFTER INSERT ON products BEGIN
                    INSERT INTO products_fts(rowid, name) VALUES (new.id, new.name);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS products_fts_au AFTER UPDATE OF name ON products BEGIN
                    DELETE FROM products_fts WHERE rowid = old.id;
                    INSERT INTO products_fts(rowid, name) VALUES (new.id, new.name);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS products_fts_ad AFTER DELETE ON products BEGIN
                    DELETE FROM products_fts WHERE rowid = old.id;
                END
            """)
            conn.commit()

            # Poblar si está vacío
            fts_count = conn.execute("SELECT COUNT(*) FROM products_fts").fetchone()[0]
            if fts_count == 0:
                conn.execute(
                    "INSERT INTO products_fts(rowid, name) SELECT id, name FROM products"
                )
                conn.commit()
        except sqlite3.OperationalError:
            log.warning("FTS5 no disponible en esta versión de SQLite — búsqueda por texto desactivada", exc_info=True)

        # Migración: ampliar CHECK constraint de stores.scraper_type para incluir 'pricesmart'
        try:
            ps_row = conn.execute(
                "SELECT id FROM stores WHERE name = 'PriceSmart CR'"
            ).fetchone()
            if ps_row is None:
                # Intentar INSERT; si falla por CHECK constraint viejo, reconstruir tabla
                try:
                    conn.execute(
                        "INSERT INTO stores (name, base_url, scraper_type) "
                        "VALUES ('PriceSmart CR', 'https://www.pricesmart.com', 'pricesmart')"
                    )
                    conn.commit()
                except sqlite3.IntegrityError:
                    # CHECK constraint no incluye 'pricesmart' → reconstruir tabla sin constraint
                    conn.execute("PRAGMA foreign_keys = OFF")
                    conn.execute("""
                        CREATE TABLE stores_new (
                            id           INTEGER PRIMARY KEY AUTOINCREMENT,
                            name         TEXT    NOT NULL UNIQUE,
                            base_url     TEXT    NOT NULL,
                            scraper_type TEXT    NOT NULL,
                            active       INTEGER NOT NULL DEFAULT 1,
                            status       TEXT    NOT NULL DEFAULT 'active'
                                         CHECK (status IN ('active', 'requires_attention'))
                        )
                    """)
                    conn.execute("INSERT INTO stores_new SELECT * FROM stores")
                    conn.execute("DROP TABLE stores")
                    conn.execute("ALTER TABLE stores_new RENAME TO stores")
                    conn.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS idx_stores_name ON stores(name)"
                    )
                    conn.execute(
                        "INSERT OR IGNORE INTO stores (name, base_url, scraper_type) "
                        "VALUES ('PriceSmart CR', 'https://www.pricesmart.com', 'pricesmart')"
                    )
                    conn.execute("PRAGMA foreign_keys = ON")
                    conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migración: una lectura de precio por producto por día
        # Elimina duplicados (conserva MAX(id) por (product_id, date)) y crea
        # unique index para garantizar la invariante en el futuro.
        # El índice existente es el marcador de migración aplicada: evita el
        # DELETE full-scan en cada arranque.
        try:
            already = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_ph_product_day'"
            ).fetchone()
            if already is None:
                conn.execute("""
                    DELETE FROM price_history
                    WHERE id NOT IN (
                        SELECT MAX(id)
                        FROM price_history
                        GROUP BY product_id, date(scraped_at)
                    )
                """)
                conn.commit()
                conn.execute("""
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_ph_product_day
                    ON price_history(product_id, date(scraped_at))
                """)
                conn.commit()
        except sqlite3.OperationalError:
            pass

        # Migración: insertar tiendas nuevas (no necesita CHECK fix — ya se hizo arriba)
        for name, base_url, scraper_type in [
            ("RadioShack CR", "https://www.radioshack.cr", "magento"),
        ]:
            try:
                row = conn.execute(
                    "SELECT id FROM stores WHERE name = ?", (name,)
                ).fetchone()
                if row is None:
                    conn.execute(
                        "INSERT OR IGNORE INTO stores (name, base_url, scraper_type) "
                        "VALUES (?, ?, ?)",
                        (name, base_url, scraper_type),
                    )
                    conn.commit()
            except sqlite3.OperationalError:
                pass
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
    image_url: str | None = None,
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
            "UPDATE products SET name = ?, url = ?, category = ?, image_url = ?, "
            "last_seen_at = datetime('now'), status = 'active' WHERE id = ?",
            (name, url, category, image_url, existing["id"]),
        )
        return existing["id"], False

    cursor = conn.execute(
        "INSERT INTO products (store_id, sku, name, url, category, image_url) VALUES (?, ?, ?, ?, ?, ?)",
        (store_id, sku, name, url, category, image_url),
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
    """Inserta o actualiza el precio del día.

    Si ya existe un registro para (product_id, hoy), actualiza los campos de
    precio sin cambiar scraped_at. Garantiza una sola lectura por día.
    """
    existing = conn.execute(
        "SELECT id FROM price_history WHERE product_id = ? AND date(scraped_at) = date('now') LIMIT 1",
        (product_id,),
    ).fetchone()
    if existing:
        conn.execute(
            """UPDATE price_history
               SET price=?, original_price=?, discount_pct=?, in_stock=?
               WHERE id=?""",
            (price, original_price, discount_pct, int(in_stock), existing["id"]),
        )
    else:
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
            data.get("image_url"),
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

def checkpoint_wal() -> None:
    """Fuerza un WAL checkpoint TRUNCATE para mantener el archivo WAL pequeño.

    Llamar después de cada job de scraping. Sin checkpoint el WAL crece
    indefinidamente hasta que SQLite lo compacta internamente (>1000 páginas),
    lo que puede afectar tiempos de lectura en tablas grandes.
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        conn.close()
        log.debug("WAL checkpoint completado")
    except Exception:
        log.warning("WAL checkpoint falló", exc_info=True)


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


def mark_products_discontinued(store_id: int, run_started_at: str) -> int:
    """Marca como 'discontinued' los productos de una tienda no vistos en el último scrape.

    Se llama después de un scrape exitoso: cualquier producto de esa tienda cuyo
    last_seen_at sea anterior a run_started_at no apareció en la corrida y se
    considera descatalogado. Si reaparece en un futuro scrape, upsert_product lo
    reactiva automáticamente (status='active').

    Returns el número de productos marcados.
    """
    with get_db() as conn:
        cur = conn.execute(
            """
            UPDATE products
               SET status = 'discontinued'
             WHERE store_id = ?
               AND status  = 'active'
               AND (last_seen_at IS NULL OR last_seen_at < ?)
            """,
            (store_id, run_started_at),
        )
        return cur.rowcount


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


def _fts_expr(raw: str) -> str | None:
    """Convierte texto libre a expresión FTS5 con prefix matching por token.

    Ejemplo: "samsung galaxy a55" → '"samsung"* "galaxy"* "a55"*'
    Retorna None si no quedan tokens después de limpiar.
    """
    clean = re.sub(r'["\(\)\^\-\*\+]', ' ', raw)
    tokens = [t for t in clean.split() if t and len(t) <= 50][:10]
    if not tokens:
        return None
    return " ".join(f'"{t}"*' for t in tokens)


def search_products(
    query: str,
    category: str | None = None,
    store: str | None = None,
    limit: int = 200,
    sort: str = "price-asc",
    offset: int = 0,
) -> list[sqlite3.Row]:
    """Busca productos con filtros opcionales.

    Usa FTS5 (prefix matching por token) cuando hay texto; devuelve todos los
    productos ordenados por precio cuando la búsqueda está vacía.

    `sort` controla la dirección del ORDER BY de precio ("price-asc" o
    "price-desc"). Importa porque el LIMIT corta el resultado: con asc un
    catálogo grande nunca muestra los productos caros.

    Columnas retornadas:
      product_id, sku, product_name, url, category, image_url,
      store_name, price, original_price, discount_pct, in_stock, scraped_at,
      price_7d_ago, price_30d_ago
    """
    # Subconsultas de precio histórico reutilizadas en ambas ramas
    _ph7 = """
        LEFT JOIN (
            SELECT ph1.product_id, ph1.price
            FROM price_history ph1
            INNER JOIN (
                SELECT product_id, MAX(id) AS max_id
                FROM price_history
                WHERE scraped_at <= datetime('now', '-7 days')
                GROUP BY product_id
            ) sub ON ph1.product_id = sub.product_id AND ph1.id = sub.max_id
        ) ph7 ON ph7.product_id = p.id
    """
    _ph30 = """
        LEFT JOIN (
            SELECT ph1.product_id, ph1.price
            FROM price_history ph1
            INNER JOIN (
                SELECT product_id, MAX(id) AS max_id
                FROM price_history
                WHERE scraped_at <= datetime('now', '-30 days')
                GROUP BY product_id
            ) sub ON ph1.product_id = sub.product_id AND ph1.id = sub.max_id
        ) ph30 ON ph30.product_id = p.id
    """
    _select = """
        SELECT
            p.id          AS product_id,
            p.sku,
            p.name        AS product_name,
            p.url,
            p.category,
            p.image_url,
            s.name        AS store_name,
            ph.price,
            ph.original_price,
            ph.discount_pct,
            ph.in_stock,
            ph.scraped_at,
            ph7.price     AS price_7d_ago,
            ph30.price    AS price_30d_ago
    """
    _price_join = """
        LEFT JOIN price_history ph ON ph.id = (
            SELECT id FROM price_history
            WHERE product_id = p.id
            ORDER BY scraped_at DESC, id DESC
            LIMIT 1
        )
    """

    price_dir = "DESC" if sort == "price-desc" else "ASC"

    extra_conds: list[str] = [
        "(p.last_seen_at IS NULL OR p.last_seen_at >= datetime('now', '-14 days'))",
        "p.status = 'active'",
    ]
    extra_params: list = []
    if category:
        extra_conds.append("p.category LIKE ? ESCAPE '\\'")
        extra_params.append("%" + category.replace("%", r"\%").replace("_", r"\_") + "%")
    if store:
        extra_conds.append("s.name LIKE ? ESCAPE '\\'")
        extra_params.append("%" + store.replace("%", r"\%").replace("_", r"\_") + "%")
    extra_where = (" AND " + " AND ".join(extra_conds)) if extra_conds else ""

    # ── Rama FTS5 (query no vacío) ──────────────────────────────────────────
    expr = _fts_expr(query) if query else None
    if expr:
        sql = f"""
            {_select}
            FROM (SELECT rowid AS fts_id, rank FROM products_fts
                  WHERE products_fts MATCH ?) ranked
            JOIN products p ON p.id = ranked.fts_id
            JOIN stores s ON s.id = p.store_id
            {_price_join}
            {_ph7}
            {_ph30}
            {"WHERE " + " AND ".join(extra_conds) if extra_conds else ""}
            ORDER BY
                ranked.rank,
                CASE WHEN ph.price IS NULL OR ph.price = 0 THEN 1 ELSE 0 END,
                ph.price {price_dir}
            LIMIT ? OFFSET ?
        """
        params = [expr] + extra_params + [limit, offset]
        try:
            with get_db() as conn:
                return conn.execute(sql, params).fetchall()
        except sqlite3.OperationalError:
            log.warning("FTS5 falló al ejecutar la búsqueda — usando fallback LIKE", exc_info=True)

        # Fallback LIKE si FTS5 falla
        extra_conds.insert(0, "p.name LIKE ?")
        extra_params.insert(0, f"%{query}%")
        extra_where = "AND " + " AND ".join(extra_conds)

    # ── Rama sin texto (o fallback LIKE) ────────────────────────────────────
    where = f"WHERE {' AND '.join(extra_conds)}" if extra_conds else ""
    sql = f"""
        {_select}
        FROM products p
        JOIN stores s ON s.id = p.store_id
        {_price_join}
        {_ph7}
        {_ph30}
        {where}
        ORDER BY
            CASE WHEN ph.price IS NULL OR ph.price = 0 THEN 1 ELSE 0 END,
            ph.price {price_dir}
        LIMIT ? OFFSET ?
    """
    params = extra_params + [limit, offset]
    with get_db() as conn:
        return conn.execute(sql, params).fetchall()


def get_top_increases(days: int = 7, limit: int = 50) -> list[sqlite3.Row]:
    """Productos que más aumentaron de precio en los últimos `days` días.

    Solo incluye productos con precio anterior y actual ambos > 0.

    Columnas retornadas:
      product_id, sku, product_name, url, category, image_url, store_name,
      price, original_price, discount_pct, in_stock, scraped_at,
      price_before, change_pct
    """
    sql = """
        SELECT
            p.id          AS product_id,
            p.sku,
            p.name        AS product_name,
            p.url,
            p.category,
            p.image_url,
            s.name        AS store_name,
            latest.price          AS price,
            latest.original_price,
            latest.discount_pct,
            latest.in_stock,
            latest.scraped_at,
            old_ph.price          AS price_before,
            ROUND(
                (latest.price - old_ph.price) * 100.0 / old_ph.price,
                1
            )                     AS change_pct
        FROM products p
        JOIN stores s ON s.id = p.store_id
        JOIN (
            SELECT ph1.product_id, ph1.price, ph1.original_price,
                   ph1.discount_pct, ph1.in_stock, ph1.scraped_at
            FROM price_history ph1
            INNER JOIN (
                SELECT product_id, MAX(id) AS max_id
                FROM price_history
                GROUP BY product_id
            ) sub ON ph1.product_id = sub.product_id AND ph1.id = sub.max_id
        ) latest ON latest.product_id = p.id
        JOIN (
            SELECT ph1.product_id, ph1.price
            FROM price_history ph1
            INNER JOIN (
                SELECT product_id, MAX(id) AS max_id
                FROM price_history
                WHERE scraped_at <= datetime('now', ? || ' days')
                GROUP BY product_id
            ) sub ON ph1.product_id = sub.product_id AND ph1.id = sub.max_id
        ) old_ph ON old_ph.product_id = p.id
        WHERE latest.price > 0
          AND old_ph.price > 0
          AND latest.price > old_ph.price
          AND p.status = 'active'
        ORDER BY change_pct DESC
        LIMIT ?
    """
    with get_db() as conn:
        return conn.execute(sql, (f"-{days}", limit)).fetchall()


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
    """Productos con bajadas reales de precio detectadas en el historial.

    Un producto aparece si:
      - El precio actual es ≤ 1 % por encima de su mínimo histórico (en los 90d disponibles)
      - El máximo histórico supera al mínimo (hubo variación real de precio)
      - La bajada respecto al máximo es ≥ 5 %
      - Tiene ≥ 3 registros históricos

    Columnas: product_id, product_name, url, category, store_name,
              current_price, price_max_90d, price_avg_90d, real_discount, sample_count
    """
    sql = """
        SELECT
            p.id    AS product_id,
            p.name  AS product_name,
            p.url,
            p.category,
            p.image_url,
            s.name  AS store_name,
            latest.price                                   AS current_price,
            stats.price_max                                AS price_max_90d,
            ROUND(stats.price_avg, 0)                      AS price_avg_90d,
            ROUND(
                (stats.price_max - latest.price) * 100.0 / stats.price_max,
                1
            )                                              AS real_discount,
            stats.sample_count
        FROM products p
        JOIN stores s ON s.id = p.store_id
        JOIN (
            SELECT product_id, price
            FROM price_history
            WHERE id IN (
                SELECT MAX(id) FROM price_history GROUP BY product_id
            )
        ) latest ON latest.product_id = p.id
        JOIN (
            SELECT
                product_id,
                MAX(price)  AS price_max,
                MIN(price)  AS price_min,
                AVG(price)  AS price_avg,
                COUNT(*)    AS sample_count
            FROM price_history
            WHERE scraped_at >= datetime('now', '-90 days')
            GROUP BY product_id
        ) stats ON stats.product_id = p.id
        WHERE latest.price <= stats.price_min * 1.01
          AND stats.price_max > stats.price_min
          AND ROUND((stats.price_max - latest.price) * 100.0 / stats.price_max, 1) >= 5.0
          AND stats.sample_count >= 3
          AND latest.price >= stats.price_avg * 0.4
          AND p.last_seen_at >= datetime('now', '-14 days')
          AND p.status = 'active'
        ORDER BY real_discount DESC
        LIMIT ?
    """
    with get_db() as conn:
        return conn.execute(sql, (limit,)).fetchall()


def get_price_check(limit: int = 300) -> list[sqlite3.Row]:
    """Productos con descuento anunciado por la tienda comparado contra historial real.

    Veredicto (doble criterio):
      1. El original_price anunciado debe ser plausible vs el máximo histórico (price_max_90d).
         Si original_price > price_max * 1.2, el "precio original" nunca fue real → fake.
      2. El descuento real (precio actual vs promedio 90d) debe ser proporcional al anunciado.

      real    — original plausible (≤ max*1.2)  Y  descuento real >= 80 % del anunciado
      partial — original no demasiado inflado (≤ max*1.5)  Y  descuento real >= 30 %
      fake    — original inflado o descuento real < 30 % del anunciado

    Columnas: product_id, name, url, category, image_url, store,
              current_price, original_price, price_max_90d,
              announced_discount, real_discount, sample_count, verdict
    """
    sql = """
        SELECT
            p.id        AS product_id,
            p.name,
            p.url,
            p.category,
            p.image_url,
            s.name      AS store,
            latest.price                                                    AS current_price,
            latest.original_price,
            stats.price_max                                                 AS price_max_90d,
            ROUND(
                (latest.original_price - latest.price) * 100.0 / latest.original_price,
                1
            )                                                               AS announced_discount,
            ROUND(
                (stats.price_avg - latest.price) * 100.0 / NULLIF(stats.price_avg, 0),
                1
            )                                                               AS real_discount,
            stats.sample_count,
            CASE
                WHEN latest.original_price <= stats.price_max * 1.2
                     AND (stats.price_avg - latest.price) / NULLIF(stats.price_avg, 0)
                         >= 0.8 * (latest.original_price - latest.price) / latest.original_price
                THEN 'real'
                WHEN latest.original_price <= stats.price_max * 1.5
                     AND (stats.price_avg - latest.price) / NULLIF(stats.price_avg, 0)
                         >= 0.3 * (latest.original_price - latest.price) / latest.original_price
                THEN 'partial'
                ELSE 'fake'
            END                                                             AS verdict
        FROM products p
        JOIN stores s ON s.id = p.store_id
        JOIN (
            SELECT product_id, price, original_price
            FROM price_history
            WHERE id IN (SELECT MAX(id) FROM price_history GROUP BY product_id)
        ) latest ON latest.product_id = p.id
        JOIN (
            SELECT
                product_id,
                AVG(price)  AS price_avg,
                MAX(price)  AS price_max,
                COUNT(*)    AS sample_count
            FROM price_history
            WHERE scraped_at >= datetime('now', '-90 days')
            GROUP BY product_id
        ) stats ON stats.product_id = p.id
        WHERE latest.original_price IS NOT NULL
          AND latest.original_price > latest.price
          AND latest.price > 0
          AND (latest.original_price - latest.price) * 100.0 / latest.original_price >= 3.0
          AND stats.sample_count >= 3
          AND p.last_seen_at >= datetime('now', '-7 days')
          AND p.status = 'active'
        ORDER BY announced_discount DESC
        LIMIT ?
    """
    with get_db() as conn:
        return conn.execute(sql, (limit,)).fetchall()


def get_inflation_index(days: int = 30) -> dict:
    """Calcula la variación promedio de precios en los últimos `days` días.

    Compara el precio actual de cada producto con el último precio registrado
    hace al menos `days` días. Solo incluye productos con datos en ambos extremos.

    Retorna un dict con:
      overall_change_pct : float | None  — variación promedio general
      product_count      : int           — productos con datos comparables
      by_category        : list[dict]    — [{category, avg_change_pct, product_count}]
      weekly_trend       : list[dict]    — [{week, avg_price, product_count}] últimas 12 sem.
    """
    # ── Variación general y por categoría ──────────────────────────────────
    cat_sql = """
        SELECT
            p.category,
            ROUND(AVG((latest.price - old_ph.price) * 100.0 / old_ph.price), 2)
                AS avg_change_pct,
            COUNT(*) AS product_count
        FROM products p
        JOIN (
            SELECT ph1.product_id, ph1.price
            FROM price_history ph1
            INNER JOIN (
                SELECT product_id, MAX(id) AS max_id
                FROM price_history
                GROUP BY product_id
            ) sub ON ph1.product_id = sub.product_id AND ph1.id = sub.max_id
        ) latest ON latest.product_id = p.id
        JOIN (
            SELECT ph1.product_id, ph1.price
            FROM price_history ph1
            INNER JOIN (
                SELECT product_id, MAX(id) AS max_id
                FROM price_history
                WHERE scraped_at <= datetime('now', ? || ' days')
                GROUP BY product_id
            ) sub ON ph1.product_id = sub.product_id AND ph1.id = sub.max_id
        ) old_ph ON old_ph.product_id = p.id
        WHERE latest.price > 0 AND old_ph.price > 0
        GROUP BY p.category
        ORDER BY avg_change_pct DESC
    """

    overall_sql = """
        SELECT
            ROUND(AVG((latest.price - old_ph.price) * 100.0 / old_ph.price), 2)
                AS avg_change_pct,
            COUNT(*) AS product_count
        FROM products p
        JOIN (
            SELECT ph1.product_id, ph1.price
            FROM price_history ph1
            INNER JOIN (
                SELECT product_id, MAX(id) AS max_id
                FROM price_history
                GROUP BY product_id
            ) sub ON ph1.product_id = sub.product_id AND ph1.id = sub.max_id
        ) latest ON latest.product_id = p.id
        JOIN (
            SELECT ph1.product_id, ph1.price
            FROM price_history ph1
            INNER JOIN (
                SELECT product_id, MAX(id) AS max_id
                FROM price_history
                WHERE scraped_at <= datetime('now', ? || ' days')
                GROUP BY product_id
            ) sub ON ph1.product_id = sub.product_id AND ph1.id = sub.max_id
        ) old_ph ON old_ph.product_id = p.id
        WHERE latest.price > 0 AND old_ph.price > 0
    """

    # ── Tendencia semanal (últimas 12 semanas) ──────────────────────────────
    trend_sql = """
        SELECT
            strftime('%Y-W%W', scraped_at)  AS week,
            ROUND(AVG(price), 2)            AS avg_price,
            COUNT(DISTINCT product_id)      AS product_count
        FROM price_history
        WHERE scraped_at >= datetime('now', '-84 days')
          AND price > 0
        GROUP BY week
        ORDER BY week
    """

    param = (f"-{days}",)
    with get_db() as conn:
        overall_row  = conn.execute(overall_sql, param).fetchone()
        cat_rows     = conn.execute(cat_sql, param).fetchall()
        trend_rows   = conn.execute(trend_sql).fetchall()

    return {
        "overall_change_pct": overall_row["avg_change_pct"] if overall_row else None,
        "product_count":      overall_row["product_count"]  if overall_row else 0,
        "by_category": [
            {
                "category":       r["category"],
                "avg_change_pct": r["avg_change_pct"],
                "product_count":  r["product_count"],
            }
            for r in cat_rows
        ],
        "weekly_trend": [
            {
                "week":          r["week"],
                "avg_price":     r["avg_price"],
                "product_count": r["product_count"],
            }
            for r in trend_rows
        ],
    }


def get_categories() -> list[str]:
    """Lista de categorías únicas con al menos un producto activo."""
    sql = """
        SELECT DISTINCT category
        FROM products
        WHERE category IS NOT NULL AND TRIM(category) != ''
          AND status = 'active'
        ORDER BY category
    """
    with get_db() as conn:
        rows = conn.execute(sql).fetchall()
    return [r["category"] for r in rows]


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
            COUNT(DISTINCT CASE WHEN p.status = 'active' THEN p.id END) AS total_products,
            MAX(ph.scraped_at)    AS last_scraped_at
        FROM stores s
        LEFT JOIN products p     ON p.store_id  = s.id
        LEFT JOIN price_history ph ON ph.product_id = p.id
        GROUP BY s.id
        ORDER BY s.name
    """
    with get_db() as conn:
        return conn.execute(sql).fetchall()
