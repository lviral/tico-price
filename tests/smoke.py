"""
Smoke tests para TicoPrice — correr antes de cada deploy.

Uso:
  python tests/smoke.py              # contra localhost:8000 (server ya corriendo)
  python tests/smoke.py --start      # levanta el server automáticamente
  python tests/smoke.py --url https://ticoprice.app  # contra prod
"""

import argparse
import io
import subprocess
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from playwright.sync_api import sync_playwright

PROD_SSH = "root@87.99.130.13"
PROD_DB_PATH = "/opt/precio-tracker/db/prices.db"
LOCAL_DB_PATH = "db/prices.db"
SSH_KEY = r"D:\Users\lvidal\.ssh\id_ed25519"


def pull_db():
    print("📥 Bajando DB de producción...")
    result = subprocess.run(
        f'scp -i "{SSH_KEY}" {PROD_SSH}:{PROD_DB_PATH} {LOCAL_DB_PATH}',
        capture_output=True, text=True, shell=True
    )
    if result.returncode != 0:
        print(f"  ⚠️  No se pudo bajar la DB: {result.stderr.strip()}")
        print("  Continuando con la DB local existente.")
    else:
        print("  ✅ DB actualizada")


def start_server(port):
    print(f"🚀 Levantando servidor en puerto {port}...")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app",
         "--port", str(port), "--log-level", "error"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(2)
    if proc.poll() is not None:
        print("  ❌ El servidor no pudo arrancar")
        sys.exit(1)
    print("  ✅ Servidor corriendo")
    return proc


def run_smoke(base_url, results):

    def ok(msg):
        print(f"  ✅ {msg}")
        results["passed"] += 1

    def fail(msg):
        print(f"  ❌ {msg}")
        results["errors"].append(msg)

    def warn(msg):
        print(f"  ⚠️  {msg}")

    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context()
        page = context.new_page()

        console_errors = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(f"JS exception: {e}"))

        # ── 1. Página principal carga ────────────────────────────────────
        print("\n[1] Página principal")
        try:
            page.goto(base_url, wait_until="networkidle", timeout=15000)
            # Esperar que el spinner de trending desaparezca
            page.wait_for_function(
                "!document.querySelector('#trending-grid .spinner')",
                timeout=10000
            )
            cards = page.query_selector_all(".product-card")
            if cards:
                ok(f"{len(cards)} productos cargados en trending")
            else:
                # Trending puede estar vacío si no hay variaciones recientes — buscar para verificar
                page.fill("#search-input", "samsung")
                # Esperar debounce (350ms) + que arranque y termine la búsqueda
                page.wait_for_timeout(500)
                page.wait_for_function(
                    "document.querySelector('#search-results-section:not(.hidden)') && "
                    "!document.querySelector('#products-grid .spinner')",
                    timeout=10000
                )
                cards = page.query_selector_all(".product-card")
                if cards:
                    ok(f"Trending vacío (normal sin datos 7d), búsqueda OK: {len(cards)} productos")
                    page.fill("#search-input", "")
                    page.wait_for_timeout(400)
                else:
                    fail("No se cargaron productos ni en trending ni en búsqueda")
        except Exception as e:
            fail(f"Página no cargó: {e}")
            browser.close()
            return

        # ── 2. Modal y gráfico ───────────────────────────────────────────
        print("\n[2] Modal + gráfico de historial")
        try:
            # Asegurar que haya cards visibles (buscar si trending está vacío)
            cards = page.query_selector_all(".product-card:visible")
            if not cards:
                page.fill("#search-input", "lg")
                page.wait_for_timeout(500)
                page.wait_for_function(
                    "document.querySelector('#search-results-section:not(.hidden)') && "
                    "!document.querySelector('#products-grid .spinner')",
                    timeout=10000
                )
                cards = page.query_selector_all(".product-card")

            # Buscar un producto que tenga historial (intentar varios)
            chart_found = False
            canvas = None
            for card in cards[:5]:
                card.click()
                page.wait_for_selector(".modal-overlay.open", timeout=5000)
                page.wait_for_function(
                    "document.getElementById('modal-body')?.querySelector('.stats-row, .empty, .spinner') && "
                    "!document.getElementById('modal-body')?.querySelector('.spinner')",
                    timeout=10000
                )
                # Esperar un frame para que el chart se inicialice
                page.wait_for_timeout(300)

                canvas = page.query_selector("#history-chart")
                if canvas:
                    w = canvas.evaluate("el => el.width")
                    h = canvas.evaluate("el => el.height")
                    if w > 0 and h > 0:
                        ok(f"Chart renderizado correctamente ({w}×{h}px)")
                        chart_found = True
                    else:
                        fail(f"Chart creado pero con dimensiones 0×0 — bug de canvas")
                    break
                else:
                    # Este producto no tiene suficiente historial, probar el siguiente
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(200)

            if not chart_found and canvas is None:
                warn("Ningún producto de los primeros 5 tiene historial suficiente para chart")

            # Verificar que el modal muestra stats (solo si sigue abierto)
            if page.query_selector(".modal-overlay.open"):
                stats = page.query_selector(".stats-row")
                if stats:
                    ok("Stats del producto visibles en modal")
                else:
                    fail("Stats del producto no aparecen en modal")
                page.keyboard.press("Escape")
                page.wait_for_timeout(300)
            else:
                ok("Modal abrió y cerró correctamente (sin historial suficiente para chart)")

        except Exception as e:
            fail(f"Error en modal/chart: {e}")

        # ── 3. Página Ofertas ────────────────────────────────────────────
        print("\n[3] Página Ofertas")
        try:
            page.click('button[data-view="view-deals"]')
            page.wait_for_function(
                "!document.querySelector('#deals-tbody .spinner')",
                timeout=10000
            )
            rows = page.query_selector_all("#deals-tbody tr")
            if rows:
                ok(f"{len(rows)} ofertas cargadas")
                cells = rows[0].query_selector_all("td")
                if len(cells) == 5:
                    ok("Columnas correctas (5: Producto, Precio, Máx 90d, Bajada, Registros)")
                else:
                    fail(f"Columnas incorrectas: esperaba 5, tiene {len(cells)}")

                # Verificar que real_discount tiene valor real (no 0%)
                import re
                discount_cell = cells[3].inner_text() if len(cells) > 3 else ""
                match = re.search(r"([\d.]+)%", discount_cell)
                if match and float(match.group(1)) > 0:
                    ok(f"Bajada real calculada: {discount_cell.strip()}")
                else:
                    fail(f"Bajada muestra 0% o sin valor: '{discount_cell.strip()}'")
            else:
                warn("No hay ofertas — puede ser normal si no hay suficiente historial")
        except Exception as e:
            fail(f"Error en página Ofertas: {e}")

        # ── 4. Página Tiendas ────────────────────────────────────────────
        print("\n[4] Página Tiendas")
        try:
            page.click('button[data-view="view-stores"]')
            page.wait_for_selector(".store-card", timeout=8000)
            stores = page.query_selector_all(".store-card")
            if stores:
                ok(f"{len(stores)} tiendas cargadas")
            else:
                fail("No se cargaron tiendas")
        except Exception as e:
            fail(f"Error en página Tiendas: {e}")

        # ── 5. API endpoints críticos ────────────────────────────────────
        print("\n[5] API endpoints")
        try:
            resp = page.request.get(f"{base_url}/products?limit=1")
            if resp.ok:
                ok(f"GET /products → {resp.status}")
            else:
                fail(f"GET /products → {resp.status}")

            resp = page.request.get(f"{base_url}/deals?limit=1")
            if resp.ok:
                data = resp.json()
                if data and "real_discount" in data[0]:
                    ok(f"GET /deals → campos correctos (real_discount presente)")
                elif data:
                    fail(f"GET /deals → campos inesperados: {list(data[0].keys())}")
                else:
                    ok("GET /deals → sin resultados (normal en DB vacía)")
            else:
                fail(f"GET /deals → {resp.status}")

            resp = page.request.get(f"{base_url}/version")
            if resp.ok:
                version = resp.json().get("version", "?")
                ok(f"GET /version → {version[:8]}…")
            else:
                fail(f"GET /version → {resp.status}")
        except Exception as e:
            fail(f"Error verificando API: {e}")

        # ── 6. Errores de consola ────────────────────────────────────────
        print("\n[6] Consola JS")
        ignorar = ["favicon", "robots.txt", "ResizeObserver"]
        errores_reales = [e for e in console_errors if not any(i in e for i in ignorar)]
        if errores_reales:
            for e in errores_reales:
                fail(f"Console error: {e}")
        else:
            ok("Sin errores en consola")

        browser.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", action="store_true", help="Levantar server local automáticamente")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--url", default=None, help="URL base (default: localhost)")
    parser.add_argument("--skip-db", action="store_true", help="No bajar DB de prod")
    args = parser.parse_args()

    base_url = args.url or f"http://localhost:{args.port}"
    server_proc = None

    print("=" * 55)
    print("  TicoPrice — Smoke Test Pre-Deploy")
    print(f"  Target: {base_url}")
    print("=" * 55)

    if not args.url and not args.skip_db:
        pull_db()

    if args.start and not args.url:
        server_proc = start_server(args.port)

    results = {"passed": 0, "errors": []}

    try:
        run_smoke(base_url, results)
    finally:
        if server_proc:
            server_proc.terminate()

    print("\n" + "=" * 55)
    if results["errors"]:
        print(f"  🔴 FALLÓ — {len(results['errors'])} problema(s) encontrado(s):")
        for e in results["errors"]:
            print(f"     • {e}")
        print("  ⛔ No hacer deploy hasta resolver estos fallos.")
        sys.exit(1)
    else:
        print(f"  🟢 PASÓ — {results['passed']} verificaciones OK")
        print("  ✈️  Listo para deploy.")
        sys.exit(0)


if __name__ == "__main__":
    main()
