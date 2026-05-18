CREATE TABLE IF NOT EXISTS stores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT    NOT NULL UNIQUE,
    base_url    TEXT    NOT NULL,
    scraper_type TEXT   NOT NULL CHECK (scraper_type IN ('magento', 'vtex')),
    active      INTEGER NOT NULL DEFAULT 1
);

-- Para BDs existentes que no tienen el constraint: idempotente
CREATE UNIQUE INDEX IF NOT EXISTS idx_stores_name ON stores(name);

CREATE TABLE IF NOT EXISTS products (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id    INTEGER NOT NULL REFERENCES stores(id),
    sku         TEXT    NOT NULL,
    name        TEXT    NOT NULL,
    url         TEXT    NOT NULL,
    category    TEXT,
    created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
    UNIQUE (store_id, sku)
);

CREATE TABLE IF NOT EXISTS price_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_id     INTEGER NOT NULL REFERENCES products(id),
    price          REAL    NOT NULL,
    original_price REAL,
    discount_pct   REAL,
    in_stock       INTEGER NOT NULL DEFAULT 1,
    scraped_at     TEXT    NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_price_history_product_id ON price_history(product_id);
CREATE INDEX IF NOT EXISTS idx_price_history_scraped_at  ON price_history(scraped_at);
CREATE INDEX IF NOT EXISTS idx_products_store_id         ON products(store_id);

INSERT OR IGNORE INTO stores (name, base_url, scraper_type) VALUES
    ('Gollo',      'https://www.gollo.com',          'magento'),
    ('Monge',      'https://www.tiendamonge.com',    'magento'),
    ('Verdugo',    'https://www.verdugotienda.com',  'magento'),
    ('Walmart CR', 'https://www.walmart.co.cr',      'vtex'),
    ('Siman CR',   'https://cr.siman.com',            'vtex');
