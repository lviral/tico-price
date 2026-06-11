"""Smoke tests de la API contra la BD local (db/prices.db).

Correr:  .venv/Scripts/python.exe -m pytest tests/ -q
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from api.main import app
from db.database import DB_PATH


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def product_id():
    """Un product_id real con historial, o skip si la BD está vacía."""
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT product_id FROM price_history LIMIT 1").fetchone()
    conn.close()
    if row is None:
        pytest.skip("BD sin datos de precios")
    return row[0]


# ── Salud y rutas básicas ────────────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "db": "ok"}


def test_home_sirve_html(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "<!DOCTYPE html>" in r.text


def test_ruta_desconocida_es_404(client):
    r = client.get("/ruta-que-no-existe")
    assert r.status_code == 404
    assert "<!DOCTYPE html>" in r.text  # sirve el SPA igual


def test_producto_inexistente_es_404(client):
    assert client.get("/producto/99999999").status_code == 404


def test_sitemap_y_robots(client):
    assert client.get("/robots.txt").status_code == 200
    r = client.get("/sitemap.xml")
    assert r.status_code == 200
    assert "<urlset" in r.text


# ── /products: orden y paginación ────────────────────────────────────────────

def test_products_sort_desc_trae_caros_primero(client, product_id):
    asc = client.get("/products?sort=price-asc&limit=5").json()
    desc = client.get("/products?sort=price-desc&limit=5").json()
    assert asc and desc
    assert desc[0]["price"] >= asc[0]["price"]
    prices = [p["price"] for p in desc if p["price"]]
    assert prices == sorted(prices, reverse=True)


def test_products_paginacion_sin_solapamiento(client, product_id):
    p1 = client.get("/products?sort=price-desc&limit=10&offset=0").json()
    p2 = client.get("/products?sort=price-desc&limit=10&offset=10").json()
    ids1 = {p["product_id"] for p in p1}
    ids2 = {p["product_id"] for p in p2}
    assert not ids1 & ids2


def test_products_sort_invalido_es_422(client):
    assert client.get("/products?sort=evil'--").status_code == 422
    assert client.get("/products?offset=-1").status_code == 422
    assert client.get("/products?limit=0").status_code == 422


# ── SSR /producto/{id} ───────────────────────────────────────────────────────

def test_ssr_producto_tiene_og_y_jsonld_valido(client, product_id):
    r = client.get(f"/producto/{product_id}")
    assert r.status_code == 200
    assert 'property="og:title"' in r.text
    assert '"price": null' not in r.text  # offer sin precio debe omitirse
    assert 'rel="canonical"' in r.text


def test_ssr_nombre_malicioso_no_inyecta_html(client):
    """Un nombre scrapeado con </script> no debe romper el bloque JSON-LD."""
    evil = 'Lavadora </script><h1 id="pwned">x</h1>'
    conn = sqlite3.connect(DB_PATH)
    try:
        store_id = conn.execute("SELECT id FROM stores LIMIT 1").fetchone()[0]
        cur = conn.execute(
            "INSERT INTO products (store_id, sku, name, url) VALUES (?, ?, ?, ?)",
            (store_id, "test-xss-jsonld", evil, "https://example.com/x"),
        )
        pid = cur.lastrowid
        conn.execute(
            "INSERT INTO price_history (product_id, price) VALUES (?, 100000)",
            (pid,),
        )
        conn.commit()  # visible para la conexión de la API

        r = client.get(f"/producto/{pid}")
        assert r.status_code == 200
        assert '<h1 id="pwned">' not in r.text   # no se inyectó HTML crudo
        assert "<\\/script>" in r.text            # quedó escapado en el JSON-LD
    finally:
        conn.execute("DELETE FROM price_history WHERE product_id = ?", (pid,))
        conn.execute("DELETE FROM products WHERE id = ?", (pid,))
        conn.commit()
        conn.close()


# ── Invariante de BD ─────────────────────────────────────────────────────────

def test_una_lectura_por_producto_por_dia(product_id):
    conn = sqlite3.connect(DB_PATH)
    dupes = conn.execute("""
        SELECT COUNT(*) FROM (
            SELECT product_id, date(scraped_at)
            FROM price_history
            GROUP BY product_id, date(scraped_at)
            HAVING COUNT(*) > 1
        )
    """).fetchone()[0]
    idx = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='index' AND name='idx_ph_product_day'"
    ).fetchone()
    conn.close()
    assert dupes == 0
    assert idx is not None
