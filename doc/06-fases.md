# 06 — Hoja de ruta por fases (reconstruir desde cero)

Orden recomendado para levantar el proyecto en un VS Code limpio hasta el estado
actual. Cada fase es **entregable y probable por sí sola** antes de pasar a la
siguiente. Al final de cada una: "Hecho cuando…".

> Consejo: crea el andamiaje (Fase 0-1) tú, y a partir de la Fase 2 puedes ir
> pidiéndole a un agente cada fase por separado, pegándole el `.md` correspondiente
> de estas specs como contexto.

---

## Fase 0 — Andamiaje e infraestructura

- Repo con `backend/` (FastAPI) y `frontend/` (Vite + React + TS).
- `docker-compose.yml` con los 2 servicios (ver [`01-arquitectura.md`](01-arquitectura.md)):
  backend `:8800→8000` montando el repo, frontend `:5074→5173`.
- `.env` con `MEDIA_OPS_TOKEN`, `OPENAI_API_KEY`, `AAI_API_KEY`. `.gitignore` con
  `.env`, `youtube_creds/`, `output/`, `cookies*.txt`, `backend/runs/`.
- Backend: FastAPI vacío con `GET /api/health` + middleware de token (Bearer/X-API-Key/`?token=`).
- Frontend: shell con pantalla de login por token (guardado en `localStorage`) y barra lateral.

**Hecho cuando:** `docker compose up` levanta ambos, `/api/health` responde y la UI
pide token y entra.

---

## Fase 1 — Persistencia y sistema de jobs

- `db.py`: SQLite con tabla `jobs` + patrón de migraciones idempotentes (ver
  [`02-modelo-de-datos.md`](02-modelo-de-datos.md)).
- `enqueue_job` + `run_job` (subproceso, log a fichero, estados). Endpoints
  `GET /api/jobs`, `/{id}`, `/{id}/log`, `/{id}/stream` (SSE).
- Frontend: sección "Historial" que lista jobs y muestra el log en vivo (EventSource con `?token=`).
- Un script de prueba en `backend/scripts/` (p.ej. un `echo` lento) para validar el flujo.

**Hecho cuando:** lanzas un job desde la UI y ves su log en tiempo real y su estado final.

---

## Fase 2 — Descarga + transcripción del vídeo fuente

- `video_download.py` con yt-dlp; añade `curl_cffi` (403/Cloudflare), `kvs_fallback.py`
  (sitios KVS) y `wetransfer_dl.py` (WeTransfer) según necesites.
- Transcripción del audio a fichero de subtítulos con tiempos (AssemblyAI o Whisper).
- Endpoint `POST /api/clips/source-from-url` y `GET /api/clips/sources`.
- Guarda todo en `output/<carpeta>/` (vídeo, `.txt`/`.vtt`, `source.json`/`source_url.txt`).

**Hecho cuando:** pegas una URL, se descarga y transcribe como job, y aparece como
fuente disponible.

---

## Fase 3 — Canales + vinculación YouTube (OAuth)

- Tabla `channels`. CRUD + endpoints `/api/channels`.
- `services/youtube_service.py`: OAuth por canal (credenciales en
  `youtube_creds/channel_{id:04d}/`), `get_auth_url`/`finish_oauth`/`unlink`,
  `get_channel_info`. Endpoints `/api/youtube/{id}/{status,secret,auth-url,unlink}` y
  `/api/youtube/finish`.
- Frontend: barra lateral de canales + pantalla "YouTube ⚙" (subir `client_secret.json`,
  vincular, desvincular). Manejo del retorno OAuth (`?code=&state=` en la raíz).

**Hecho cuando:** creas un canal y vinculas una cuenta de YouTube real.

---

## Fase 4 — Detección de clips con IA

- `services/clip_detector.py`: detección por partes (OpenAI). Tabla `clips` con los
  campos base + `focus/zoom/top_ratio/subtitles` con defaults.
- `replace_clips` que preserva los clips ya renderizados/subidos al re-detectar.
- Endpoints `POST /api/clips/detect` y `GET /api/clips/list` (+ `_annotate_clip`).
- Frontend: parámetros (partes/clips por parte/duración) + lista de tarjetas de clip
  con los ajustes (aún sin render).

**Hecho cuando:** de una transcripción salen N clips con título/score/tiempos,
persistidos y editables.

---

## Fase 5 — Render vertical (el corazón)

- `make_vertical_clip.py`: composición pantalla partida (arriba recorte enfocado con
  focus/zoom, abajo escena completa con letterbox). Lienzo 1080×1920.
- `subtitle_engine.py`: transcripción por palabra (AssemblyAI) → ASS karaoke (`\kf`) → quemar.
- `render_clip.py`: encadena composición → subtítulos → (overlay/endcard vienen luego).
- Endpoint `POST /api/clips/{id}/render` (job). Preview en la tarjeta con `renderNonce`
  para romper caché tras regenerar, y overlay "…regenerando…".

**Hecho cuando:** generas un short vertical con karaoke de un clip y lo ves en la UI.

---

## Fase 6 — Caption fijo + cierre con miniatura

- `burn_overlay` en `render_clip.py`: caption persistente en barra semitransparente
  (dibujo ASS) + texto amarillo negrita, a `0.63*H` (por encima del karaoke). Campo
  `overlay_text` + textarea en la tarjeta.
- `add_fade_and_endcard`: sin fundido a negro; corta al fotograma final (extraído
  LIMPIO antes de subtítulos) mientras el audio hace fade out; el fotograma se queda
  unos segundos con el caption en grande (miniatura). Campo `endcard_percent`
  (default 50). Endpoint `/api/clips/{id}/frames` (3 fotogramas 25/50/75%) + UI de elección.

**Hecho cuando:** el short sale con caption fijo y cierre con fotograma elegible como
miniatura, sin tapar el karaoke.

---

## Fase 7 — SEO + subida a YouTube

- `services/seo_engine.py` + `clip_seo.py`: título/descripción/tags con OpenAI según
  idioma y reglas del canal; `strip_markdown`, `strip_wrapping_quotes`.
- `upload_clip.py` + `youtube_service.upload_video` (con **saneo de tags** contando
  comillas, límite 480) y `set_video_privacy`. Campos `seo_*`, `youtube_url`,
  `youtube_privacy`, `uploaded_at`.
- Endpoints `/api/clips/{id}/{seo,upload,visibility}`. UI: previsualizar SEO, elegir
  privacidad (default Público), subir, cambiar visibilidad, copiar textos.

**Hecho cuando:** subes un short a YouTube con su SEO y puedes cambiar su visibilidad.

---

## Fase 8 — Campañas + compliance del brief

- Tabla `campaigns` (nexo con clips por `transcript_path`). CRUD + `/api/campaigns`.
- `services/brief_extractor.py`: extrae reglas del Google Doc con IA
  (`caption obligatorio`, handles, hashtags, watermark, fuente). `rules_json`.
- Endpoints `/api/campaigns/{id}/{brief,apply-rules}`. En `clip_seo` se añaden caption
  + hashtags de la campaña y el título/link del original (salvo WeTransfer).
- Frontend: "Mis campañas", sección de brief, auto-aplicar reglas.

**Hecho cuando:** una campaña extrae las reglas del brief y los shorts salen ya
cumpliendo el caption/handles/hashtags.

---

## Fase 9 — Productividad y control de envío

- **Render en cola en el backend** (`render_all.py` + `POST /api/clips/render-all`):
  un job que renderiza todos los pendientes secuencialmente aplicando el encuadre
  global; el frontend deriva el estado de la lista de jobs (sobrevive a recargas).
- **Encuadre global** en la barra de render.
- **Endcard 50% por defecto** para que el primer render ya sea un short con cierre.
- **Botón "Submiteado a Whop"** (`submitted`) + **cuenta atrás de 30 min** (`uploaded_at`),
  por la regla de la campaña (los vídeos con > 30 min desde la subida se rechazan).
- **Indicadores de progreso de campaña:**
  - En la campaña abierta: banner "N/total subidos · N/total submiteados" que pasa a
    verde "✅ Campaña totalmente subida y submiteada" cuando todo está subido y submiteado.
  - En el listado "Mis campañas": cada campaña muestra "N/total renderizados · subidos ·
    submiteados" (o "✅ Completada"). El API adjunta `clipStats` (agregado por
    `transcript_path`) a cada campaña — ver [`04-api.md`](04-api.md).
- `privatize_pending.py` para privatizar contenido antiguo sin tocar campañas.
- Persistencia de navegación en `localStorage`.

**Hecho cuando:** le das a "Generar todos los verticales", te vas, y al volver están
todos renderizados; subes y marcas submiteado con la cuenta atrás visible.

---

## Fase 10 — Encuadre "Seguir al hablante" (ASD, en progreso)

Recorte dinámico al hablante activo (estilo Opus Clip) para planos fijos de 2+
personas. Worker de GPU (TalkNet-ASD) en el Windows (WSL2 + Docker `--gpus`),
desacoplado del Docker de la app. Ver [`07-asd-active-speaker.md`](07-asd-active-speaker.md).

- [x] `asd_worker/` (FastAPI + TalkNet) + contrato `asd.json`.
- [x] `asd_client.py` (sube vídeo, cachea, fallback si no hay GPU) + `ASD_WORKER_URL`.
- [x] Modo de encuadre "Seguir al hablante" en el render (recorte dinámico que sigue
  al hablante activo). Validado con el podcast WATO. Ver [`07-asd-active-speaker.md`](07-asd-active-speaker.md).

## Ideas futuras (no implementadas)

- Subida a **TikTok e Instagram** (cada plataforma con su enlace y su botón de submiteado).
- Caption listo por plataforma (handle correcto + copiar).
- Encuadre que preserve automáticamente la marca de agua.
- Ampliación de cuota de YouTube / varios proyectos Google Cloud para escalar subidas.
- ComfyUI para generar la mitad inferior (evaluado y descartado por ahora).
