# Despliegue en producción

## Servidor recomendado

**Hetzner CX22** — €3.79/mes  
- 2 vCPU, 4 GB RAM, 40 GB SSD  
- Ubuntu 24.04 LTS  
- Suficiente para Playwright + FastAPI + SQLite  

Alternativa: DigitalOcean Droplet Basic ($6/mes)

---

## Pasos

### 1. Crear el servidor

1. Crear cuenta en [hetzner.com](https://hetzner.com)
2. Nuevo servidor: Ubuntu 24.04, CX22
3. Agregar tu clave SSH
4. Anotar la IP pública

### 2. Apuntar el dominio

En tu registrador de dominios, crear un registro **A**:
```
@ → IP_DEL_SERVIDOR
www → IP_DEL_SERVIDOR
```
Esperar 5-10 minutos para que propague.

### 3. Subir el repositorio a GitHub

```bash
# En tu máquina local
git remote add origin https://github.com/TU_USUARIO/precio-tracker-cr.git
git push -u origin master
```

> ⚠️ Asegurarse de que `db/prices.db` está en `.gitignore`  
> (la BD se genera en el servidor con el primer scrape)

### 4. Correr el script de instalación

```bash
# Conectarse al servidor
ssh root@IP_DEL_SERVIDOR

# Descargar y correr setup
curl -sL https://raw.githubusercontent.com/TU_USUARIO/precio-tracker-cr/master/deploy/setup.sh | \
    bash -s tudominio.com
```

O manualmente:
```bash
git clone https://github.com/TU_USUARIO/precio-tracker-cr /opt/precio-tracker
cd /opt/precio-tracker
bash deploy/setup.sh tudominio.com
```

### 5. Primer scrape

```bash
sudo -u preciotracker /opt/precio-tracker/.venv/bin/python \
    /opt/precio-tracker/run.py --once
```
Tarda ~15 minutos la primera vez.

---

## Comandos útiles post-despliegue

```bash
# Ver logs de la API en vivo
journalctl -u precio-tracker-api -f

# Ver logs del último scrape
journalctl -u precio-tracker-scraper

# Ver timers activos
systemctl list-timers | grep precio

# Reiniciar la API
systemctl restart precio-tracker-api

# Correr scrape manualmente
systemctl start precio-tracker-scraper

# Actualizar la app
cd /opt/precio-tracker
sudo -u preciotracker git pull
sudo -u preciotracker .venv/bin/pip install -r requirements.txt
systemctl restart precio-tracker-api
```

---

## Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `SITE_URL` | URL pública del sitio (para sitemap) | `https://preciotrackercr.com` |

Configuradas en `deploy/api.service`.

---

## Estructura de servicios

```
precio-tracker-api.service    → API FastAPI (siempre activa)
precio-tracker-scraper.service → Scrape (oneshot, lo lanza el timer)
precio-tracker-scraper.timer  → 6am y 6pm hora CR (12:00 y 00:00 UTC)
Caddy                         → Reverse proxy + HTTPS automático
```
