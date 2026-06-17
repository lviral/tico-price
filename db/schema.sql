CREATE TABLE IF NOT EXISTS stores (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    name         TEXT    NOT NULL UNIQUE,
    base_url     TEXT    NOT NULL,
    scraper_type TEXT    NOT NULL CHECK (scraper_type IN ('magento', 'vtex', 'pricesmart')),
    active       INTEGER NOT NULL DEFAULT 1,
    status       TEXT    NOT NULL DEFAULT 'active'
                         CHECK (status IN ('active', 'requires_attention'))
);

-- Para BDs existentes que no tienen el constraint: idempotente
CREATE UNIQUE INDEX IF NOT EXISTS idx_stores_name ON stores(name);

CREATE TABLE IF NOT EXISTS scrape_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id     INTEGER NOT NULL REFERENCES stores(id),
    started_at   TEXT    NOT NULL,
    finished_at  TEXT    NOT NULL,
    success      INTEGER NOT NULL DEFAULT 0,
    new_products INTEGER NOT NULL DEFAULT 0,
    prices_added INTEGER NOT NULL DEFAULT 0,
    errors       INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_scrape_runs_store_id ON scrape_runs(store_id);
CREATE INDEX IF NOT EXISTS idx_scrape_runs_started  ON scrape_runs(started_at);

CREATE TABLE IF NOT EXISTS products (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    store_id     INTEGER NOT NULL REFERENCES stores(id),
    sku          TEXT    NOT NULL,
    name         TEXT    NOT NULL,
    url          TEXT    NOT NULL,
    category     TEXT,
    image_url    TEXT,
    created_at   TEXT    NOT NULL DEFAULT (datetime('now')),
    last_seen_at TEXT    NOT NULL DEFAULT (datetime('now')),
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
CREATE INDEX IF NOT EXISTS idx_ph_product_date ON price_history(product_id, scraped_at);
CREATE INDEX IF NOT EXISTS idx_products_store_id         ON products(store_id);

-- FTS5: búsqueda de texto completo en nombres de productos.
-- Standalone (no content=): almacena name directamente para búsqueda confiable.
CREATE VIRTUAL TABLE IF NOT EXISTS products_fts USING fts5(
    name,
    tokenize = "unicode61 remove_diacritics 2"
);

CREATE TRIGGER IF NOT EXISTS products_fts_ai AFTER INSERT ON products BEGIN
    INSERT INTO products_fts(rowid, name) VALUES (new.id, new.name);
END;

CREATE TRIGGER IF NOT EXISTS products_fts_au AFTER UPDATE OF name ON products BEGIN
    DELETE FROM products_fts WHERE rowid = old.id;
    INSERT INTO products_fts(rowid, name) VALUES (new.id, new.name);
END;

CREATE TRIGGER IF NOT EXISTS products_fts_ad AFTER DELETE ON products BEGIN
    DELETE FROM products_fts WHERE rowid = old.id;
END;

INSERT OR IGNORE INTO stores (name, base_url, scraper_type) VALUES
    ('Gollo',         'https://www.gollo.com',             'magento'),
    ('Monge',         'https://www.tiendamonge.com',       'magento'),
    ('Verdugo',       'https://www.verdugotienda.com',     'magento'),
    ('Walmart CR',    'https://www.walmart.co.cr',         'vtex'),
    ('Siman CR',      'https://cr.siman.com',              'vtex'),
    ('Aliss CR',      'https://aliss.cr',                  'magento'),
    ('EPA CR',        'https://cr.epaenlinea.com',         'magento'),
    ('PriceSmart CR', 'https://www.pricesmart.com',        'pricesmart'),
    ('RadioShack CR', 'https://www.radioshack.cr',         'magento');
