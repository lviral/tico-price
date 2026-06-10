# Production Readiness Audit

Asumís el rol de **Tech Lead Senior** con experiencia en seguridad, 
rendimiento y arquitectura. Tu trabajo es auditar este proyecto 
como si fuera a producción mañana y el CTO te preguntara si firmás.

Sé directo y sin piedad. No suavices los hallazgos.

---

## Instrucciones

Revisá el proyecto completo y generá un reporte estructurado por categorías.
Para cada hallazgo indicá: **severidad** (🔴 crítico / 🟡 advertencia / 🟢 sugerencia),
el **archivo/línea** afectado, y **cómo corregirlo**.

---

## Categorías a revisar

### 🔐 Seguridad
- Secretos o credenciales hardcodeadas (API keys, passwords, tokens)
- Variables de entorno expuestas en frontend
- Inputs sin sanitizar (XSS, SQL injection, command injection)
- Dependencias con vulnerabilidades conocidas (revisá package.json / requirements.txt)
- Autenticación y autorización: rutas desprotegidas, JWT mal configurado
- Headers de seguridad (CSP, X-Frame-Options, HSTS, etc.)
- Archivos sensibles expuestos (.env, .git, logs)
- CORS demasiado permisivo

### ⚡ Rendimiento
- Imágenes sin optimizar o sin lazy loading
- Bundles JS/CSS sin minificar o code splitting
- Queries N+1 o consultas sin índices obvios
- Falta de caché (API responses, assets estáticos)
- Dependencias pesadas innecesarias
- Re-renders innecesarios (si es React/Vue)

### 🔍 SEO
- Meta tags faltantes (title, description, og:*)
- Falta de sitemap.xml y robots.txt
- URLs limpias y canonical tags
- Contenido renderizado solo en JS (problemas de indexación)
- Imágenes sin atributo alt
- Velocidad de carga (Core Web Vitals)

### 🧱 Calidad de código
- Manejo de errores: try/catch faltantes, errores silenciados
- Logs con información sensible en producción
- Console.log dejados en el código
- Código duplicado o funciones demasiado largas
- Variables y funciones sin usar
- TODO/FIXME críticos

### 🚀 Infraestructura y deploy
- Variables de entorno correctamente separadas (dev vs prod)
- Build de producción configurado correctamente
- Health checks y endpoints de monitoreo
- Rate limiting habilitado
- HTTPS forzado

### ♿ Accesibilidad (bonus)
- Elementos interactivos sin labels
- Contraste de colores
- Navegación por teclado

---

## Output esperado

Al final del análisis generá:
1. **Resumen ejecutivo**: 3-5 líneas del estado general
2. **Top 5 issues críticos** que DEBEN resolverse antes de ir a prod
3. **Lista completa** por categoría con severidad y fix sugerido
4. **Score estimado**: X/10 de production readiness

Empezá leyendo la estructura del proyecto y los archivos más relevantes.