# 01 — Arquitectura e infraestructura

## Servicios (docker-compose.yml)

Dos contenedores:

### backend
- Build desde `backend/Dockerfile`, `working_dir: /workspace/backend`.
- Monta todo el repo: `.:/workspace` (por eso el código se recarga en vivo).
- Puerto `8800:8000`.
- `env_file: .env`.
- Command (importante, instala dependencias volátiles en cada arranque):
  ```sh
  pip install --no-cache-dir --upgrade yt-dlp curl_cffi \
    && pip install --no-cache-dir openai google-auth-oauthlib google-api-python-client \
    && uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload --timeout-graceful-shutdown 5
  ```
  - `yt-dlp` se actualiza siempre (sus extractores se rompen cada pocas semanas).
  - `curl_cffi` para impersonation de navegador (sitios con 403/Cloudflare).
  - `--timeout-graceful-shutdown 5` evita que el reload se cuelgue esperando a
    cerrar conexiones SSE abiertas.

### frontend
- Build desde `frontend/Dockerfile` target `dev`.
- Puerto `5074:5173`, monta `./frontend:/app` + volumen `frontend_node_modules`.
- Command: `npm run dev -- --host 0.0.0.0` (Vite dev server con HMR).

> **HMR:** como el código va montado, cualquier cambio de fichero recarga la página
> del navegador. Cualquier estado en memoria del cliente se pierde en la recarga →
> por eso los procesos largos (render en cola) deben vivir en el **backend**, no en el cliente.

## Variables de entorno (`.env`)

| Variable | Uso |
|----------|-----|
| `MEDIA_OPS_TOKEN` | Token de acceso (auth). Si está vacío, la API es abierta. |
| `OPENAI_API_KEY`  | Detección de clips, SEO, extracción de brief. |
| `AAI_API_KEY`     | AssemblyAI, subtítulos karaoke por palabra. |

`.env` contiene secretos reales → **gitignored, nunca commitear**. Igual que
`youtube_creds/` y los ficheros `cookies*.txt`.

## Autenticación

Middleware de token en el backend. El token se acepta por:
- `Authorization: Bearer <token>`
- `X-API-Key: <token>`
- `?token=<token>` (query param — necesario para `EventSource`/SSE y para `<img>/<video>`
  que no pueden mandar cabeceras).

Frontend: guarda el token en `localStorage` (`mediaops_token`), pantalla de login si
la API responde `authRequired: true`. Todas las llamadas añaden la cabecera; para
recursos servidos por URL (ficheros, streams) usa `?token=`.

## Sistema de jobs

Los procesos pesados (descarga, transcripción, render, subida) corren como **jobs**:
un job = un script de `backend/scripts/` ejecutado como **subproceso**.

- `enqueue_job(script_name, args)`:
  - crea un `Job` (id de 12 hex), estado `queued`, `log_path = backend/runs/<id>.log`.
  - lo guarda en memoria (`jobs` dict + `jobs_lock`) y en SQLite (`db.save_job`).
  - lanza un `threading.Thread(target=run_job, daemon=True)`.
- `run_job(job_id)`:
  - marca `running`, abre el log, `subprocess.Popen(cmd, cwd=ROOT_DIR, stdout=PIPE, stderr=STDOUT)`.
  - vuelca stdout línea a línea al fichero de log.
  - al acabar marca `completed`/`failed` con `return_code`.
- Los scripts hijos que a su vez lanzan otros scripts (p.ej. `render_all.py` →
  `render_clip.py`) heredan el stdout, así todo el progreso cae en el mismo log.

Endpoints de jobs:
- `GET /api/jobs`, `GET /api/jobs/{id}`, `GET /api/jobs/{id}/log`.
- `GET /api/jobs/{id}/stream` → **SSE** en vivo (frontend hace `EventSource` con `?token=`).

Patrón clave para procesos largos que deben sobrevivir a recargas del navegador:
**encolarlos como un job de backend** y que el frontend derive el estado de la lista
de jobs (buscar un job con ese `script` en estado `running/queued`). Ejemplo:
`render_all.py` (ver [`03-pipeline-y-servicios.md`](03-pipeline-y-servicios.md)).

## Estructura de carpetas

```
backend/
  app/
    main.py            # FastAPI: endpoints, jobs, auth
    db.py              # capa SQLite (schema, migraciones, CRUD)
    catalog.py         # metadatos de scripts para la UI "Ejecutar Scripts"
    services/          # lógica de IA y utilidades
      clip_detector.py     # detección de clips (OpenAI, por partes)
      clip_seo.py          # SEO por clip (título/desc/tags + compliance)
      seo_engine.py        # wrapper OpenAI de generación SEO
      brief_extractor.py   # extrae reglas del brief (Google Docs) con IA
      youtube_service.py   # OAuth + upload + privacidad por canal
      transcription.py     # transcripción
      video_download.py    # yt-dlp + fallbacks
      content_pipeline.py  # pipeline URL→audio→transcripción
      comfyui.py           # (opcional, descartado en clipping)
  scripts/             # cada uno se ejecuta como job (subproceso)
    render_clip.py         # render vertical de UN clip (pipeline completo)
    render_all.py          # render EN COLA de todos los pendientes
    make_vertical_clip.py  # composición ffmpeg pantalla partida
    subtitle_engine.py     # transcripción por palabra → ASS karaoke → quemar
    upload_clip.py         # subida a YouTube con SEO + compliance
    privatize_pending.py   # privatiza vídeos antiguos sin tocar campañas
    download_*.py, kvs_fallback.py, wetransfer_dl.py, ...
  runs/                # jobs.db (SQLite) + logs de jobs
frontend/
  src/
    App.tsx            # toda la UI (secciones, clipping, canales)
    api.ts             # cliente HTTP tipado
    types.ts           # tipos compartidos
    styles.css         # estilos + tema oscuro
youtube_creds/         # credenciales OAuth por canal (gitignored)
  channel_XXXX/{client_secret.json, token.json}
output/                # vídeos descargados, transcripciones, clips renderizados (gitignored)
doc/                   # esta documentación
```
