"""Scheduler de scraping: ejecuta runner.run_store() dos veces al día.

Lógica de alerta:
  Después de cada run se registra el resultado en scrape_runs.
  Si las últimas 3 corridas de una tienda fueron todas fallidas,
  la tienda se marca como 'requires_attention' y se emite un log de CRITICAL.
  Un run exitoso la restaura a 'active'.

Un run se considera exitoso cuando prices_added > 0 y errors == 0.
"""

import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

import schedule

from db.database import (
    checkpoint_wal,
    get_active_stores,
    get_consecutive_failures,
    init_db,
    mark_store_attention,
    record_scrape_run,
    reset_store_status,
)
from scrapers.runner import SCRAPER_MAP, STORE_CATEGORIES, run_store

ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "logs"
CONSECUTIVE_FAILURE_THRESHOLD = 3

log = logging.getLogger("scheduler")

# Referencia al FileHandler actual para rotación por fecha
_file_handler: logging.FileHandler | None = None
_log_date: date | None = None


# ---------------------------------------------------------------------------
# Logging con rotación diaria
# ---------------------------------------------------------------------------

def _build_formatter() -> logging.Formatter:
    return logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s")


def _rotate_log_if_needed() -> None:
    """Añade o rota el FileHandler diario en el logger raíz."""
    global _file_handler, _log_date

    today = date.today()
    if _log_date == today and _file_handler is not None:
        return

    LOGS_DIR.mkdir(exist_ok=True)
    root = logging.getLogger()

    # Cerrar handler del día anterior
    if _file_handler is not None:
        root.removeHandler(_file_handler)
        _file_handler.close()

    log_path = LOGS_DIR / f"scraper_{today:%Y-%m-%d}.log"
    _file_handler = logging.FileHandler(log_path, encoding="utf-8")
    _file_handler.setFormatter(_build_formatter())
    root.addHandler(_file_handler)
    _log_date = today
    log.info("Log del día iniciado: %s", log_path)


def setup_logging() -> None:
    """Configura logging a stdout + archivo diario. Llamar una vez al iniciar."""
    root = logging.getLogger()
    root.setLevel(logging.INFO)

    if not any(isinstance(h, logging.StreamHandler) and h.stream is sys.stdout
               for h in root.handlers):
        stdout_handler = logging.StreamHandler(sys.stdout)
        stdout_handler.setFormatter(_build_formatter())
        root.addHandler(stdout_handler)

    _rotate_log_if_needed()


# ---------------------------------------------------------------------------
# Job de scraping
# ---------------------------------------------------------------------------

def _run_one_store(store: object) -> None:
    """Scrapea una tienda, registra el resultado y verifica fallos consecutivos."""
    store_id: int = store["id"]
    store_name: str = store["name"]

    started_at = datetime.now().isoformat(timespec="seconds")
    try:
        result = run_store(
            store_id=store_id,
            store_name=store_name,
            scraper_type=store["scraper_type"],
            base_url=store["base_url"],
        )
        success = result.prices_recorded > 0 and result.errors == 0
        new_p = result.new_products
        prices = result.prices_recorded
        errors = result.errors
    except Exception as exc:
        log.exception("Error inesperado scrapeando '%s': %s", store_name, exc)
        success, new_p, prices, errors = False, 0, 0, 1

    finished_at = datetime.now().isoformat(timespec="seconds")
    record_scrape_run(store_id, started_at, finished_at, success, new_p, prices, errors)

    if success:
        reset_store_status(store_id)
    else:
        consecutive = get_consecutive_failures(store_id, n=CONSECUTIVE_FAILURE_THRESHOLD)
        if consecutive >= CONSECUTIVE_FAILURE_THRESHOLD:
            mark_store_attention(store_id)
            log.critical(
                "ALERTA: '%s' ha fallado %d veces consecutivas → "
                "marcada como requires_attention. Revisar manualmente.",
                store_name,
                CONSECUTIVE_FAILURE_THRESHOLD,
            )


def scrape_job() -> None:
    """Job que ejecuta el scrape completo de todas las tiendas activas."""
    _rotate_log_if_needed()
    log.info("═" * 55)
    log.info("Job de scraping iniciado  %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    log.info("═" * 55)

    stores = get_active_stores()

    if not stores:
        log.warning("No hay tiendas activas — job finalizado sin acción")
        return

    for store in stores:
        _run_one_store(store)

    checkpoint_wal()
    log.info("Job de scraping completado  %s", datetime.now().strftime("%Y-%m-%d %H:%M"))


# ---------------------------------------------------------------------------
# Arranque del scheduler
# ---------------------------------------------------------------------------

def start() -> None:
    """Registra los jobs y entra al loop principal. Bloquea hasta Ctrl+C."""
    setup_logging()
    init_db()

    schedule.every().day.at("06:00").do(scrape_job)
    schedule.every().day.at("18:00").do(scrape_job)

    next_run = schedule.next_run()
    log.info("Scheduler iniciado. Jobs: 06:00 y 18:00 diarios.")
    log.info("Próxima ejecución: %s", next_run.strftime("%Y-%m-%d %H:%M") if next_run else "—")

    try:
        while True:
            schedule.run_pending()
            time.sleep(30)
    except KeyboardInterrupt:
        log.info("Scheduler detenido por el usuario.")
