---
description: Verificar que todo funciona localmente antes de hacer deploy a producción
---

# Pre-deploy

Corrés este skill antes de hacer `git push` + deploy al servidor.

## Lo que hace

1. Baja la DB de producción (`scp` desde el servidor)
2. Levanta el servidor FastAPI local en puerto 8000
3. Corre `tests/smoke.py` con Playwright — verifica:
   - Productos cargan en la home
   - Modal abre y el chart renderiza con dimensiones > 0
   - Página Ofertas muestra columnas correctas y `real_discount` con valor real
   - Página Tiendas carga
   - API endpoints `/products`, `/deals`, `/version` responden OK
   - Sin errores en consola JS
4. Reporta qué pasó y qué falló

## Cómo ejecutarlo

Corré este comando en el directorio del proyecto:

```bash
python tests/smoke.py --start
```

- `--start` → levanta el server local automáticamente (necesita el .venv activo)
- Sin `--start` → asume que el server ya está corriendo en localhost:8000
- `--url https://ticoprice.app` → corre directamente contra producción (sin bajar DB)
- `--skip-db` → no baja la DB de prod (usa la local existente)

## Activar el entorno virtual primero

```bash
.venv\Scripts\activate   # Windows
source .venv/bin/activate  # Linux/Mac
python tests/smoke.py --start
```

## Instrucciones para Claude

Cuando el usuario invoca `/pre-deploy`:

1. Verificá que el entorno virtual existe (`.venv/`). Si no existe, informá al usuario que debe crearlo primero con `python -m venv .venv && pip install -r requirements.txt playwright install chromium`.

2. Corré el smoke test:
   ```
   .venv\Scripts\python tests/smoke.py --start
   ```
   (o `python tests/smoke.py --start` si el venv ya está activo)

3. Mostrá el output completo al usuario.

4. Si hay fallos (exit code 1):
   - Identificá cuál de los checks falló
   - Leé el código relevante para entender la causa
   - Proponé un fix antes de hacer deploy

5. Si todo pasa (exit code 0):
   - Confirmá que es seguro hacer push y deploy
   - Recordale al usuario el comando de deploy:
     ```
     git push origin master && ssh root@87.99.130.13 "cd /opt/precio-tracker && git pull && systemctl restart precio-tracker-api"
     ```
