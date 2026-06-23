#!/usr/bin/env bash
# =============================================================================
# PrecioTracker CR — Script de instalación en servidor Ubuntu 24.04
# Ejecutar como root: bash setup.sh tudominio.com
# =============================================================================
set -euo pipefail

DOMAIN="${1:?Uso: bash setup.sh tudominio.com}"
APP_DIR="/opt/precio-tracker"
APP_USER="preciotracker"

echo ""
echo "=========================================="
echo "  PrecioTracker CR — Setup en $DOMAIN"
echo "=========================================="
echo ""

# ── 1. Paquetes del sistema ─────────────────────────────────────────────────
# Las librerías de Chromium NO se listan aquí: cambian de nombre entre
# versiones de Ubuntu (ej. libasound2 → libasound2t64 en 24.04).
# `playwright install-deps` (paso 5) instala las correctas para el SO.
echo "[1/7] Instalando dependencias del sistema..."
apt-get update -qq
apt-get install -y -qq \
    python3.12 python3.12-venv python3-pip \
    git curl wget unzip sqlite3

# Caddy (reverse proxy con HTTPS automático)
if ! command -v caddy &>/dev/null; then
    apt-get install -y -qq debian-keyring debian-archive-keyring apt-transport-https
    curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/gpg.key | \
        gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -fsSL https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt | \
        tee /etc/apt/sources.list.d/caddy-stable.list
    apt-get update -qq && apt-get install -y caddy
fi

# ── 2. Usuario del sistema ──────────────────────────────────────────────────
echo "[2/7] Creando usuario $APP_USER..."
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --shell /bin/bash --home "$APP_DIR" "$APP_USER"
fi

# ── 3. Clonar repositorio ───────────────────────────────────────────────────
echo "[3/7] Clonando repositorio..."
if [ -d "$APP_DIR/.git" ]; then
    echo "  Repo ya existe, haciendo pull..."
    cd "$APP_DIR" && sudo -u "$APP_USER" git pull
else
    git clone https://github.com/lviral/tico-price "$APP_DIR"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"
fi

cd "$APP_DIR"

# ── 4. Entorno virtual Python ───────────────────────────────────────────────
echo "[4/7] Configurando entorno Python..."
sudo -u "$APP_USER" python3.12 -m venv .venv
sudo -u "$APP_USER" .venv/bin/pip install --quiet --upgrade pip
sudo -u "$APP_USER" .venv/bin/pip install --quiet -r requirements.txt

# ── 5. Playwright (navegador para Magento) ──────────────────────────────────
echo "[5/7] Instalando Playwright Chromium..."
sudo -u "$APP_USER" .venv/bin/python -m playwright install chromium
sudo -u "$APP_USER" .venv/bin/python -m playwright install-deps chromium

# ── 6. Base de datos inicial ────────────────────────────────────────────────
echo "[6/7] Inicializando base de datos..."
sudo -u "$APP_USER" .venv/bin/python -c "from db.database import init_db; init_db()"

# ── 7. Servicios systemd ────────────────────────────────────────────────────
echo "[7/7] Instalando servicios systemd..."

# Reemplazar dominio en los archivos de servicio
sed "s|TU_DOMINIO|$DOMAIN|g" deploy/api.service     > /etc/systemd/system/precio-tracker-api.service
sed "s|TU_DOMINIO|$DOMAIN|g" deploy/Caddyfile        > /etc/caddy/Caddyfile
cp deploy/scraper.service /etc/systemd/system/precio-tracker-scraper.service
cp deploy/scraper.timer   /etc/systemd/system/precio-tracker-scraper.timer
cp deploy/backup.service  /etc/systemd/system/precio-tracker-backup.service
cp deploy/backup.timer    /etc/systemd/system/precio-tracker-backup.timer

# Directorio de backups con permisos del usuario de la app
mkdir -p "$APP_DIR/backups"
chown "$APP_USER:$APP_USER" "$APP_DIR/backups"

systemctl daemon-reload
systemctl enable --now precio-tracker-api
systemctl enable --now precio-tracker-scraper.timer
systemctl enable --now precio-tracker-backup.timer
systemctl enable --now caddy

echo ""
echo "=========================================="
echo "  Instalacion completa!"
echo ""
echo "  API:     http://localhost:8000"
echo "  Web:     https://$DOMAIN"
echo ""
echo "  Logs API:    journalctl -u precio-tracker-api -f"
echo "  Logs Cron:   journalctl -u precio-tracker-scraper -f"
echo "  Logs Backup: journalctl -u precio-tracker-backup -f"
echo "  Backups:     $APP_DIR/backups/"
echo ""
echo "  Primer scrape (puede tardar ~10 min):"
echo "  sudo -u $APP_USER $APP_DIR/.venv/bin/python $APP_DIR/run.py --once"
echo "=========================================="
