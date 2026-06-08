"""Punto de entrada único del proyecto.

Uso:
    python run.py --once              # scrape inmediato y sale
    python run.py --once Gollo Monge  # scrape solo esas tiendas
    python run.py --schedule          # scheduler continuo (6am / 6pm)
    python run.py --api               # API REST en :8000
    python run.py --api --port 9000   # API en puerto personalizado
"""

import argparse
import logging
import sys


def _setup_console_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stdout,
    )


def cmd_once(store_names: list[str]) -> None:
    _setup_console_logging()
    from db.database import init_db
    from scrapers.runner import run_all

    init_db()
    results = run_all(store_names=store_names or None) or []
    errors = sum(r.errors for r in results)
    sys.exit(1 if errors else 0)


def cmd_schedule() -> None:
    from scheduler.cron import start
    start()


def cmd_api(host: str, port: int, reload: bool) -> None:
    _setup_console_logging()
    import uvicorn
    uvicorn.run("api.main:app", host=host, port=port, reload=reload)


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python run.py",
        description="Precio Tracker CR — scraping de electrodomésticos en tiendas CR",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos:
  python run.py --once                     Scrapea todas las tiendas ahora
  python run.py --once Gollo "Walmart CR"  Solo esas tiendas
  python run.py --schedule                 Inicia el scheduler (6am / 6pm)
  python run.py --api                      API en http://localhost:8000
  python run.py --api --port 9000          API en puerto 9000
  python run.py --api --reload             API con hot-reload (desarrollo)
        """,
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--once",
        nargs="*",
        metavar="STORE",
        help="Ejecuta el scrape inmediatamente y sale. "
             "Opcionalmente acepta nombres de tiendas (ej: Gollo 'Walmart CR').",
    )
    mode.add_argument(
        "--schedule",
        action="store_true",
        help="Inicia el scheduler: scrape diario a las 6:00 y 18:00. "
             "Logs en logs/scraper_YYYY-MM-DD.log.",
    )
    mode.add_argument(
        "--api",
        action="store_true",
        help="Levanta la API FastAPI con uvicorn.",
    )

    parser.add_argument("--host", default="0.0.0.0", help="Host de la API (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Puerto de la API (default: 8000)")
    parser.add_argument(
        "--reload", action="store_true",
        help="Hot-reload para la API (solo desarrollo).",
    )

    args = parser.parse_args()

    if args.once is not None:
        cmd_once(args.once)
    elif args.schedule:
        cmd_schedule()
    elif args.api:
        cmd_api(args.host, args.port, args.reload)


if __name__ == "__main__":
    main()
