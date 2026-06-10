"""Scheduler de scraping: ejecuta runner.run_all() dos veces al día.

El registro en scrape_runs, la alerta por fallos consecutivos y el WAL
checkpoint viven en runner.run_all() — el mismo camino que usa el timer
systemd (run.py --once), para que dev y prod compartan la misma lógica.
"""

import logging
import sys
import time
from datetime import date, datetime
from pathlib import Path

import schedule

from db.database import init_db
from scrapers.runner import run_all

ROOT = Path(__file__).resolve().parent.parent
LOGS_DIR = ROOT / "logs"

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

def scrape_job() -> None:
    """Job que ejecuta el scrape completo de todas las tiendas activas."""
    _rotate_log_if_needed()
    log.info("═" * 55)
    log.info("Job de scraping iniciado  %s", datetime.now().strftime("%Y-%m-%d %H:%M"))
    log.info("═" * 55)

    run_all()

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
