# Prototipo MYPE · Pronóstico de demanda, alertas de quiebre y segmentación

Implementación ejecutable del piloto descrito en el APF3: pipeline de datos, modelos supervisados y no supervisados, plan de compra con A*, API con MFA y dashboard.

> **Declaración obligatoria:** todos los datos son **simulados**. INEI y SUNAT no publican ventas por SKU de un minimarket, así que no existe una fuente pública equivalente. El perfil activo (`data/generate_demo.py`) **calibra** el simulador para acercar las métricas a las del APF3; las cifras de `artifacts/` son el resultado de esa calibración, no mediciones de Minimarket La Esquina. La comparación objetivo vs. logrado está en `RESULTADOS.md`, y la API y el dashboard lo muestran como `demo_calibrada`.

## Arquitectura

| Servicio | Imagen / build | Puerto | Función |
|---|---|---|---|
| `frontend` | `frontend/` (Vite + Nginx) | 8080 | Dashboard React con login MFA |
| `api` | `api/` (FastAPI + Uvicorn) | 8000 | Endpoints REST, JWT, TOTP, RBAC |
| `worker` | `api/` | — | Sincroniza alertas cada 60 min |
| `db` | `postgres:16-alpine` | 5432 | Usuarios, alertas y auditoría |
| `redis` | `redis:7-alpine` | — | Caché de métricas |
| `mlflow` | `ghcr.io/mlflow/mlflow` | 5000 | Tracking de experimentos |
| `trainer` | `python:3.12-slim` (perfil `train`) | — | Genera datos y entrena |

## Requisitos

- Docker Desktop con Compose v2 (o Python 3.12 + Node 20 para el modo local)
- 4 GB de RAM libres; el entrenamiento usa ~1 GB

Probado en Windows 11 con Python 3.12.8, pandas 3.0.2, scikit-learn 1.9.1 y XGBoost 3.4.1. Las versiones exactas están en `requirements.txt` y `ml/requirements.txt`.

## 1. Levantar todo con Docker

Probado en WSL2 (Ubuntu 24.04) con Docker 29.6.1 y Compose v5.3.1, desde `/mnt/c/Users/Joshua/Proyectos/prototipo_mype`.

```powershell
Copy-Item .env.example .env
docker compose up -d --build
docker compose ps
```

Eso deja seis contenedores: `db`, `redis`, `mlflow`, `api`, `worker` y `frontend`. El frontend responde en <http://127.0.0.1:8080>, la API en <http://127.0.0.1:8000> y MLflow en <http://127.0.0.1:5000>. Usa la IP, no `localhost`: con red en modo espejo, `localhost` resuelve a `::1` y `Invoke-WebRequest` se cuelga (curl y el navegador sí caen a IPv4).


Generar el código TOTP del usuario sembrado y entrar en <http://localhost:8080>:

```powershell
docker compose exec api python -m app.totp
```

Credenciales por defecto: `propietario@mype.pe` / `Piloto2026!` / código de 6 dígitos. Cambiar `ADMIN_PASSWORD`, `ADMIN_TOTP_SECRET` y `JWT_SECRET` en `.env` antes de cualquier uso real.

Entrenar dentro de Docker (perfil `train`):

```powershell
docker compose --profile train run --rm trainer
```

Eso deja `artifacts/` en el host; la API lo monta en solo lectura y recarga al detectar un `metricas.json` nuevo. Tarda unos 3 minutos (instala dependencias y entrena) y pide ~2 GB de RAM: si Docker Desktop está limitado a menos, súbelo en Settings → Resources. El run queda registrado en MLflow vía su API REST, sin necesidad de instalar el paquete `mlflow`.

Apagar:

```powershell
docker compose down
docker compose down -v   # además borra volúmenes de Postgres/Redis/MLflow
```

### 1.1 Mantener el stack vivo en WSL

WSL apaga la distro cuando no queda ninguna sesión conectada, y con ella se detiene `dockerd`. Todos los servicios tienen `restart: unless-stopped`, así que vuelven solos al reactivar la distro, pero si quieres que sigan arriba sin abrir una terminal:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\keepalive.ps1
```

Eso deja un `sleep` adjunto en la distro por 24 h. Para cortar todo: `wsl --shutdown`.

### 1.2 Perfil de datos

Hay dos generadores:

| Script | Perfil | Para qué |
|---|---|---|
| `data/generate_demo.py` | `demo` | calibrado a las cifras del informe (18.250 tickets, 127.750 líneas, 214 SKUs densos) |
| `data/generate.py` | `realista` | simulación libre, sin calibrar |

La demo fija los volúmenes exactos y ajusta el ruido de demanda, la política de pedidos y la separación de los segmentos. Los parámetros que se tocaron están listados en `RESULTADOS.md`, sección «Qué se ajustó para llegar ahí».

```powershell
python data/generate_demo.py --out data/demo
python ml/train.py --raw data/demo --art artifacts --fecha 2026-11-10T09:14:00
```

`--fecha` declara la fecha de entrenamiento que muestran la API y el panel (los archivos conservan `generado_real` con la hora efectiva). Sin el flag se usa la fecha actual.

## 2. Ejecutar sin Docker

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Generar datos y entrenar (~30 s y ~80 s respectivamente):

```powershell
python data/generate_demo.py --out data/demo
python ml/train.py --raw data/demo
```

Levantar la API:

```powershell
$env:DATABASE_URL = "sqlite:///./data/app.db"
$env:ARTIFACTS_DIR = (Resolve-Path artifacts).Path
$env:JWT_SECRET = "dev-secret"
$env:PYTHONPATH = (Resolve-Path api).Path
python -m uvicorn app.main:app --reload --port 8000
```

Levantar el front:

```powershell
cd frontend
npm install
npm run dev
```

El proxy de Vite manda `/api` a `http://localhost:8000`.

## 3. Cómo correr cada prueba

### 3.1 Pruebas del pipeline de datos y modelos

```powershell
python -m pytest ml/tests -q
```

Qué valida:

- `test_generador_es_determinista`: dos corridas con la misma semilla producen archivos byte a byte idénticos.
- `test_generador_cambia_con_semilla`: con otra semilla cambian los datos (no está hardcodeado).
- `test_features_sin_fuga_temporal`: `ma_4` y `lag_1` se recalculan a mano y deben coincidir, lo que prueba que las features solo miran hacia atrás.
- `test_volumenes_de_la_demo`: los tickets, líneas, clientes y anónimos cuadran con las cifras del informe.

### 3.2 Pruebas de la API

```powershell
python -m pytest api/tests -q
```

Cubre: `/health`, rechazo de password y de TOTP incorrectos, 401 sin token en todos los endpoints protegidos, dashboard, métricas, pronóstico (incluido 404), segmentos, plan de compra y el flujo completo de alertas (sync → listar → reconocer).

### 3.3 Build del frontend

```powershell
cd frontend
npm run build
```

Falla si hay imports rotos o JSX inválido; deja el bundle en `frontend/dist`.

### 3.4 Smoke test de la API en vivo

Con el stack en Docker hay un script que recorre todo a través del nginx del frontend (health, 401 sin token, login con TOTP, dashboard, pronóstico, plan y alertas en Postgres):

```powershell
wsl -d Ubuntu-24.04 bash -lc "cd /mnt/c/Users/Joshua/Proyectos/prototipo_mype && bash scripts/smoke.sh"
```

En Windows directo, contra la API en el puerto 8000:

```powershell
$otp = python -m app.totp
$body = @{ email="propietario@mype.pe"; password="Piloto2026!"; otp=$otp } | ConvertTo-Json
$login = Invoke-RestMethod "http://127.0.0.1:8000/api/v1/auth/login" -Method Post -Body $body -ContentType "application/json"
$h = @{ Authorization = "Bearer $($login.access_token)" }
Invoke-RestMethod "http://127.0.0.1:8000/health"
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/dashboard" -Headers $h
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/forecast?limit=5" -Headers $h
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/segments" -Headers $h
Invoke-RestMethod "http://127.0.0.1:8000/api/v1/purchase-plan?top=5" -Headers $h
```

### 3.5 Verificar que el reentrenamiento es reproducible

```powershell
python ml/train.py --raw data/demo
Get-FileHash artifacts/metricas.json
python ml/train.py --raw data/demo
Get-FileHash artifacts/metricas.json
```

El hash de `metricas.json` no cambia (solo el campo `generado`); las métricas son estables con la semilla `20261116`.

### 3.6 Comprobar las métricas contra el informe

```powershell
Get-Content artifacts/metricas.json
```

`RESULTADOS.md` trae la comparación tabla por tabla con lo que decía el APF3.

### 3.7 Demo guiada en terminal

Para explicar el procedimiento en vivo (dataset, split 9/2/1, entrenamiento de XGBoost, clustering y decisiones) hay una secuencia de seis scripts con salida visual:

```powershell
powershell -ExecutionPolicy Bypass -File demo\run_all.ps1
```

Cada paso espera `Enter`. El guion de qué decir en cada uno está en `demo/GUION.md`. Los scripts trabajan en `demo_work/` y el último (`06_publicar.py`) reentrena el pipeline completo y deja los artefactos que consume el panel.

### 3.8 Agregar datos y ver el efecto

El panel **general** trae un bloque “Llegada de datos nuevos — reentrenamiento” que compara tres reentrenamientos reales sobre la misma ventana de prueba, con una deriva simulada de +35 % de demanda desde el 1 de noviembre:

| Historial usado | MAPE | RMSE | F1 |
|---|---|---|---|
| Sin datos nuevos | 27,10 % | 17,31 | 0,936 |
| +1 semana | 27,99 % | 17,76 | 0,931 |
| +2 semanas | 14,32 % | 7,73 | 0,949 |

Se regenera desde la terminal (~4 min, tres entrenamientos):

```powershell
python ml/escenarios.py
```

Escribe `artifacts/escenarios/resumen.json`, que es lo que lee `GET /api/v1/scenarios`. El generador acepta `--dias`, `--deriva-inicio` y `--deriva-factor`, y `train.py` acepta `--split deriva --hasta YYYY-MM-DD` para reproducir cada fila.

### 3.9 Simular el paso de la semana

En *Panel general* hay un bloque **Simulación semana a semana** con las últimas 6 semanas del piloto. Cada una es un snapshot real del modelo (pronóstico, probabilidad y stock tal como se veían al cerrar esa semana):

- Botones `‹` y `›` para retroceder o avanzar una semana.
- Barras clicables con el número de alertas de cada semana.
- Se actualizan las alertas, el riesgo máximo, el MAPE de esa semana y las 4 urgencias con su acción.

Los snapshots se regeneran con:

```powershell
python ml/semanas.py
```

Escribe `artifacts/semanas.json` (224 KB), que alimenta `GET /api/v1/weeks` y `GET /api/v1/weeks/{i}`.

## 4. Endpoints

| Método | Ruta | Auth | Descripción |
|---|---|---|---|
| GET | `/health` | no | Estado y disponibilidad de artefactos |
| GET | `/api/v1/auth/demo-code` | no | Solo con `DEMO_MODE=1`: TOTP vigente del usuario demo |
| POST | `/api/v1/auth/login` | no | Email + password + TOTP → JWT (15 min) |
| GET | `/api/v1/models` | sí | Modelos entrenados: tipo, variables, árboles, clusters, umbral |
| GET | `/api/v1/scenarios` | sí | Reentrenamientos con 0, 1 y 2 semanas de datos nuevos |
| GET | `/api/v1/weeks` | sí | índice de las últimas 6 semanas (alertas, riesgo, MAPE) |
| GET | `/api/v1/weeks/{i}` | sí | snapshot completo de una semana |
| GET | `/api/v1/dashboard` | sí | KPIs agregados del piloto |
| GET | `/api/v1/metrics` | sí | `metricas.json` completo (cacheado en Redis) |
| GET | `/api/v1/forecast?limit=&q=` | sí | Pronóstico por SKU, ordenado por demanda |
| GET | `/api/v1/forecast/{sku_id}` | sí | Pronóstico de un SKU |
| GET | `/api/v1/segments` | sí | Segmentos, silueta y ARI |
| GET | `/api/v1/purchase-plan?top=` | sí | Plan A* con costo por SKU |
| GET | `/api/v1/alerts?estado=` | sí | Alertas guardadas en Postgres |
| POST | `/api/v1/alerts/sync` | sí | Recalcula alertas desde el pronóstico |
| POST | `/api/v1/alerts/{id}/ack` | sí | Marca alerta como atendida y audita |

## 5. Estructura

```
prototipo_mype/
├─ data/generate_demo.py      # simulador calibrado (perfil activo)
├─ data/generate.py           # simulador libre, sin calibrar
├─ ml/features.py             # agregación semanal y features sin fuga
├─ ml/train.py                # modelos, métricas y artefactos
├─ ml/planning.py             # A* con haz para el plan de compra
├─ ml/tests/                  # pruebas del pipeline
├─ api/app/                   # FastAPI: seguridad, DB, worker
├─ api/tests/                 # pruebas de contrato de la API
├─ frontend/                  # React + Vite (+ vercel.json)
├─ deploy/Dockerfile          # imagen única para la nube (API + artefactos)
├─ deploy/huggingface/        # cabecera para un Space de Docker
├─ render.yaml                # blueprint gratis de Render
├─ artifacts/                 # modelos, métricas y pronósticos generados
├─ scripts/smoke.sh           # prueba end-to-end contra el stack local
├─ scripts/deploy_smoke.sh    # prueba de la imagen de despliegue
├─ scripts/warmup.ps1         # despierta el servicio gratis antes de la demo
├─ demo/                     # 6 scripts de demostración + guion
├─ docker-compose.yml
└─ requirements.txt
```

## 6. Variables de entorno

| Variable | Default | Uso |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./data/app.db` | Postgres en Docker, SQLite en local |
| `ARTIFACTS_DIR` | `./artifacts` | Ruta de modelos y métricas |
| `JWT_SECRET` | `cambiar-en-produccion` | Firma HS256 |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | `propietario@mype.pe` / `Piloto2026!` | Usuario sembrado |
| `ADMIN_TOTP_SECRET` | `JBSWY3DPEHPK3PXP` | Secreto base32 del MFA |
| `ALERT_THRESHOLD` | `0.5` | Probabilidad mínima para alertar |
| `REDIS_URL` | vacío | Si existe, cachea `/metrics` 60 s |
| `MLFLOW_TRACKING_URI` | vacío | Si existe, registra el run por la API REST de MLflow |
| `DEMO_MODE` | vacío | `1` habilita `/api/v1/auth/demo-code` para entrar sin calculadora TOTP |

## 7. Desplegar gratis en internet

Objetivo: demostrar desde cualquier PC sin llevar nada instalado. El front es estático (Vercel) y la API es un contenedor Docker (Render).

```
Navegador  ->  Vercel (React estático)  ->  Render (FastAPI + XGBoost + K-Means, SQLite)
```

### Por qué el backend no va en Vercel

Vercel sirve funciones serverless con un límite de ~250 MB sin comprimir y sin binarios nativos pesados. `xgboost`, `scikit-learn` y `pandas` suman más de 300 MB y el arranque en frío de una función no carga un proceso persistente; la imagen real pesa 1,34 GB. Para este stack hace falta un contenedor.

### Opciones gratis (noviembre 2026)

| Opción | Qué da | Duerme | Encaja aquí |
|---|---|---|---|
| **Render (free web service)** | 512 MB RAM, 0,1 CPU, Docker, 750 h/mes | 15 min inactivo, ~1 min al despertar | **Recomendada**: la imagen usa 146 MB y hay blueprint listo |
| **Hugging Face Spaces (Docker)** | 2 vCPU, 16 GB RAM, URL pública | tras 48 h inactivo | Mejor si Render se queda corto de RAM |
| **Google Cloud Run** | 2 M req/mes, escala a cero | a cero, ~10 s | Requiere cuenta con tarjeta (aunque no cobre) |
| **Koyeb** | 1 servicio 512 MB | sí | Similar a Render, menos cuota |
| Railway / Fly.io | créditos iniciales o pago por uso | — | Ya no son gratis de verdad |
| Render cron / worker | **no incluido** en free | — | El `worker` del compose no corre en la nube |

### Paso 1: backend en Render

1. Sube el repo a GitHub.
2. Render → **New → Blueprint** → elige el repo. Toma `render.yaml` y crea `prototipo-mype-api` desde `deploy/Dockerfile`.
3. En el servicio, define los secretos que pide el blueprint: `ADMIN_PASSWORD` y `ADMIN_TOTP_SECRET` (por ejemplo `JBSWY3DPEHPK3PXP`).
4. Espera el build (~5 min, instala pandas/sklearn/xgboost) y comprueba `https://TU-SERVICIO.onrender.com/health`.

`render.yaml` ya activa `DEMO_MODE=1`, así que el login puede pedir el código en pantalla sin calculadora.

### Paso 2: frontend en Vercel

1. Vercel → **Add New → Project** → importa el repo.
2. **Root Directory**: `frontend`. Framework: Vite (lo detecta).
3. Environment Variable: `VITE_API_BASE = https://TU-SERVICIO.onrender.com` (sin barra final).
4. Deploy. La URL queda tipo `https://prototipo-mype.vercel.app`.

Vite incrusta `VITE_API_BASE` en el build: si cambias la URL del backend, hay que volver a desplegar el front.

### Opción de un solo servicio (sin static site ni permisos de app)

`deploy/Dockerfile.all` construye el front y lo sirve desde FastAPI en la misma URL. Así solo hay un servicio que crear, sin `VITE_API_BASE` ni CORS:

- Render → **New → Web Service → Public Git repository**
- URL: `https://github.com/joshuaxpro19/prototipo-MYPE-s`
- Dockerfile Path: `deploy/Dockerfile.all` · Docker Context: `.`
- Plan **Free** · Health Check Path `/health`
- Variables: `DEMO_MODE=1`, `JWT_SECRET` (generate), `ADMIN_EMAIL=propietario@mype.pe`, `ADMIN_PASSWORD`, `ADMIN_TOTP_SECRET`, `ALERT_THRESHOLD=0.5`

El contenedor quedó probado en local con `scripts/deploy_all_smoke.sh`: la raíz devuelve el HTML del panel, `/health` responde 200 y el login MFA funciona.

### Cómo entrar cuando está en la nube

No hay terminal en Render, así que el código MFA sale de dos formas:

1. **Botón del login**: “Obtener código de acceso”. Llama a `GET /api/v1/auth/demo-code`, que devuelve el TOTP vigente y el correo. Requiere `DEMO_MODE=1` (ya viene activo en `render.yaml` y en `docker-compose.yml`).
2. **App autenticadora** (Google Authenticator, Authy, 1Password): agrega una entrada manual con el secreto base32 que pusiste en `ADMIN_TOTP_SECRET`, 6 dígitos, 30 s, SHA-1. Sirve aunque `DEMO_MODE=0`.

Si cambias `ADMIN_PASSWORD` en Render, el formulario no lo va a precargar: escribe la nueva.

### Paso 3: antes de la demo

El plan gratis duerme el backend. Despiértalo un minuto antes:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\warmup.ps1 -Url https://TU-SERVICIO.onrender.com
```

Y entra con **Usar código demo** en la pantalla de login.

### Alternativa: Hugging Face Spaces

Si prefieres 16 GB de RAM y que no se duerma tan rápido: crea un Space con SDK **Docker**, sube el repo y usa `deploy/Dockerfile` (el Space escucha en el puerto 8000). `deploy/huggingface/README.md` trae la cabecera que pide HF. Los Spaces gratuitos son públicos, así que el repo y los secretos van como variables del Space.

### Qué cambia en la nube

- **Disponibilidad**: la URL es tuya todo el mes, pero el servicio se duerme a los 15 min sin tráfico y tarda **cerca de un minuto** en despertar. El primer clic después de un rato muestra una pantalla de carga de Render.
- **Cuota**: 750 horas-instancia por *workspace* al mes. Un mes de 31 días tiene 744 h, así que mantenerlo despierto 24/7 consume casi toda la cuota. No lo dejes con un ping automático.
- **Disco efímero**: cualquier archivo que escriba la app (incluido `app.db`) se pierde al dormir, reiniciar o redeployar. El usuario demo se vuelve a sembrar en cada arranque, así que el login siempre funciona; las alertas y los "ack" se reinician.
- **Sin Redis ni MLflow**: `REDIS_URL` vacío desactiva la caché y el entrenamiento no se ejecuta ahí; los artefactos van dentro de la imagen.
- **Cambia los secretos**: `JWT_SECRET`, `ADMIN_PASSWORD` y `ADMIN_TOTP_SECRET` por defecto son de demo.
- **No subas datos reales**: todo sigue siendo la demo calibrada.

### Persistencia: qué se pierde y cómo evitarlo

| Qué | En Render free |
|---|---|
| Modelos, métricas, pronósticos | **Persisten**: van dentro de la imagen |
| Usuario demo | Se recrea en cada arranque |
| Alertas y auditoría (SQLite) | **Se pierden** en cada spin-down |
| `Render Postgres` free | Persiste, pero **caduca a los 30 días** (14 de gracia y luego se borra) |

Si necesitas que las alertas sobrevivan más de una sesión, usa un Postgres gratis externo que no expire. Con **Neon** (0,5 GB, sin caducidad):

1. Crea el proyecto en neon.tech y copia la cadena de conexión.
2. Cámbiala al dialecto de SQLAlchemy (`postgresql+psycopg://usuario:clave@host/db?sslmode=require`).
3. En Render → Environment → `DATABASE_URL` = esa cadena.
4. Redeploy. `init_db` crea las tablas solo.

Supabase funciona igual (`postgresql+psycopg://...` con el puerto 5432 del pooler). Con eso, alertas y usuarios sobreviven a los reinicios del servicio.

### Probar la imagen de despliegue antes de subirla

```powershell
docker build -f deploy/Dockerfile -t mype-demo:latest .
wsl -d Ubuntu-24.04 -e bash -lc "cd /mnt/c/Users/Joshua/Proyectos/prototipo_mype && bash scripts/deploy_smoke.sh"
```

El script levanta el contenedor en el puerto 8090, pide un código demo, hace login, consulta dashboard y modelos, y muestra el consumo de RAM (146 MB medidos).

## 8. Limitaciones conocidas

- No se midió latencia bajo carga ni disponibilidad del VPS: el informe cita 180 ms p95 y 99.5 % de uptime, y eso requiere ejecutar Locust sobre el despliegue real.
- El plan de compra usa `h(n) = 0` (admisible pero débil) y poda por haz; el óptimo no está garantizado.
- El sobre-stock no es un KPI del simulador; solo se miden quiebres y demanda.
- Las figuras del APF3 no se regeneran aquí: se calculan desde `artifacts/metricas.json` y `artifacts/clientes_pca.csv`.
