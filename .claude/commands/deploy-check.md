# Deploy Check

Checklist pre-deploy de TicoPrice. Ejecutá cada chequeo y reportá un
semáforo final: ¿seguro hacer `git pull` + restart en el servidor?

---

## Chequeos

### 1. Estado del repo
- `git status --short` — working tree limpio (sin cambios a medio commitear)
- `git log origin/master..HEAD --oneline` — nada sin pushear
- El servidor hace `git pull` de origin/master: lo que no esté pusheado no se despliega

### 2. Sintaxis y arranque
- `bash -n deploy/setup.sh` — sintaxis válida
- Importes críticos con el venv del proyecto:
  `python -c "import api.main, scrapers.runner, scheduler.cron"`
- Verificar que `init_db()` corre sin error (incluye las migraciones idempotentes)

### 3. Suite de tests (obligatorio — bloqueante si falla)
```
.venv/Scripts/python.exe -m pytest tests/ -q
```
La suite de `tests/test_api.py` cubre: health, 404 fallback (rutas y
productos inexistentes), sitemap/robots, orden y paginación de /products,
validación 422, JSON-LD sin `price: null` y sin inyección HTML vía
`</script>` en nombres scrapeados, e invariante de una lectura de
precio por producto por día. Si pytest no está instalado:
`pip install -r requirements-dev.txt`.

Cualquier test en rojo es **bloqueante** — no hay deploy hasta que pase.

### 3b. Smoke test adicional (solo lo que los tests no cubren)
Levantá la API (`run.py --api`) si no está corriendo, y verificá:
- `GET /trending?limit=2` → 200 con datos reales

### 4. Configuración de producción
- `deploy/Caddyfile`: contiene `TU_DOMINIO` como placeholder (setup.sh lo
  reemplaza) — verificar que no quedó un dominio hardcodeado de pruebas
- `deploy/api.service`: `SITE_URL` presente, `--host 127.0.0.1` (no 0.0.0.0)
- `deploy/scraper.timer`: `OnCalendar` en UTC correcto (00:00 y 12:00 = 6pm/6am CR)
- `requirements.txt`: todo pinneado con `==`

### 5. Frontend
- `frontend/index.html` referencia archivos que existen en `frontend/static/`
- El SHELL del service worker (`sw.js`) solo lista archivos existentes
- Sin `console.log` de debug nuevos en `app.js`

---

## Output esperado

- ✅/❌ por chequeo, con detalle solo en los que fallen
- Veredicto final: **LISTO PARA DEPLOY** o lista de bloqueantes
- Si hay bloqueantes, ofrecé corregirlos pero no los corrijas sin confirmación
