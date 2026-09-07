# Media Ops — Onboarding para una nueva sesión de Claude

> Documento de arranque para que un Claude en **otro ordenador** entienda todo el
> proyecto sin contexto previo. Para detalle por áreas, ver la carpeta [`doc/`](doc/)
> (01-arquitectura, 02-modelo-de-datos, 03-pipeline-y-servicios, 04-api, 05-frontend,
> 06-fases, 07-asd-active-speaker). Este fichero es el índice + lo más reciente
> (Avatar Reel, reels de partido y Macetas/WAN) que aún no está en `doc/`.

---

## 1. Qué es

**Media Ops** (repo `myMoviPyTests`): plataforma web para producir vídeo corto vertical
(Shorts/Reels/TikTok) de forma semiautomática. Empezó como "clip farming" (clipear vídeos
largos para campañas tipo ClipFarm/Whop/Reach) y ha crecido con generación de contenido propio
con IA. Áreas principales:

1. **Clipping** — descargar un vídeo largo, transcribir, detectar los mejores momentos con IA,
   render vertical con subtítulos karaoke, SEO y subida a YouTube. Campañas por canal.
2. **Avatar Reel** — contenido propio: disparador → guion (OpenAI) → **voz clonada (XTTS)** →
   vídeo con karaoke + música, con b-roll IA (ComfyUI) o fondo simple. + miniatura + SEO + subida.
3. **Reels de partido** — a partir del enlace de YouTube de un resumen de fútbol: transcribe →
   momentos clave → guion explicativo → voz → **fragmentos de vídeo reales** recortados a vertical
   → karaoke + música. (⚠️ el metraje real da Content ID en YouTube; ver §11.)
4. **🪴 Macetas** — vídeos de crecimiento de plantas en time-lapse **100% IA** (WAN 2.2 TI2V-5B
   imagen→vídeo). Contenido sin copyright. **En desarrollo** (ver §10).

---

## 2. Cómo arrancar / operar

Todo corre en **Docker Compose** en el equipo Debian de desarrollo.

```bash
cd /home/guillem/myMoviPyTests
docker compose up -d                     # levanta backend + frontend
docker compose logs -f backend           # logs backend
```

- **Backend**: contenedor `intro_python_backend`, FastAPI + uvicorn `--reload`, puerto host
  **8800 → 8000**. El repo se monta en `/workspace` (`.:/workspace`), así que **editar un `.py`
  recarga el backend en caliente** (no hay que reconstruir). Dominio público: `mymovi.enguillem.es`.
- **Frontend**: contenedor `intro_python_frontend`, build **de producción con nginx**, puerto
  **5074 → 80**. **NO hay HMR**: tras tocar `frontend/src/**` hay que:
  ```bash
  cd frontend && npx tsc --noEmit        # typecheck (obligatorio antes de build)
  docker compose build frontend && docker compose up -d frontend
  ```
- **DB**: SQLite en `backend/runs/jobs.db` (stdlib `sqlite3`). Migraciones idempotentes con
  `ALTER TABLE ... ADD COLUMN` en `backend/app/db.py` (listas `*_MIGRATIONS`), se aplican en `init()`.
- **Auth**: header `Authorization` / token `MEDIA_OPS_TOKEN` (ver `.env`). Endpoints devuelven 401 sin él.

---

## 3. Sistema de JOBS (crítico entender esto)

Las operaciones largas o con GPU **NO** se hacen en el request; se lanzan como **jobs**:
`enqueue_job(script_name, args)` en `backend/app/main.py` ejecuta `backend/scripts/<script>.py`
como **subproceso detached** (`start_new_session=True`) y guarda el log en `backend/runs/<job_id>.log`.

**Por qué importa:** el backend corre con `--reload`. Si editas un fichero `.py` (o se crea un
`.pyc`) mientras hay un **request síncrono largo** en vuelo, uvicorn se reinicia y **mata** ese
request (se ve como "received signal 15 / código 255"). Los jobs detached **sobreviven** al reload.
→ Regla: cualquier cosa que tarde (ffmpeg, ComfyUI, TTS, descargas, transcripción) va como **job**,
no como request síncrono. (El `/api/reels/compose` es la excepción histórica síncrona; el resto son jobs.)

Frontend hace *polling* (`api.reelsList()`, `api.job(id)`, etc.) hasta que el registro tiene `video`/`youtubeUrl`.

---

## 4. Infraestructura externa (LAN 192.168.1.x)

| Servicio | Máquina / URL | Uso | Env |
|---|---|---|---|
| **ComfyUI** | Windows `192.168.1.46:8188` (nativo, GPU) | imágenes SDXL + vídeo WAN | `COMFY_URL` |
| **XTTS TTS** | Windows `192.168.1.46:8022` (docker, GPU) | voz clonada | `LOCAL_TTS_URL` |
| **person_worker** | `192.168.1.46:8901` | detección/tracking personas (blur) | `PERSON_WORKER_URL` |
| **asd_worker** | `192.168.1.46:8900` | active speaker detection | `ASD_WORKER_URL` |
| **AssemblyAI** | nube | transcripción (subtítulos, momentos) | `AAI_API_KEY` |
| **OpenAI** | nube | guiones, SEO, prompts, detección de clips | `OPENAI_API_KEY` |
| **YouTube** | nube (OAuth por canal) | subida | creds en `backend/../youtube_creds` |

- **GPU del Windows**: **NVIDIA RTX 4060 Ti, 16 GB VRAM**. Límite clave para WAN (ver §10).
- **SSH al Windows**: `ssh guillem@192.168.1.46` cae en **cmd.exe** (usar rutas Windows `dir`/`type`,
  o `for %F in (...) do @echo %~zF`). Para el venv de ComfyUI: `D:\AI\ComfyUI\venv\Scripts\python.exe`.
  ComfyUI vive en `D:\AI\ComfyUI` (modelos en `D:\AI\ComfyUI\models\{unet,diffusion_models,loras,vae,text_encoders,checkpoints}`).
- **scp trunca ficheros grandes** con el OpenSSH de Windows (los corta a ~200 KB). Para traer
  binarios grandes: **streaming base64 vía PowerShell** →
  `ssh guillem@192.168.1.46 "powershell -NoProfile -Command \"[Convert]::ToBase64String([IO.File]::ReadAllBytes('D:\\ruta\\fichero'))\"" | tr -d '\r\n' | base64 -d > destino`.
  Para descargar modelos de HuggingFace directos al box: usar el venv + `huggingface_hub.hf_hub_download`
  (script pasado por base64, ver historial de la sesión de Macetas).
- Hubo otra máquina ComfyUI `192.168.1.184` ("ComfyUI - copia", del proyecto de shorts) — **suele estar apagada**.

---

## 5. `.env` (claves — NO commitear, está gitignored)

Nombres presentes: `BACKEND_PORT`, `FRONTEND_PORT`, `BACKEND_CORS_ORIGINS`, `AAI_API_KEY`,
`COMFY_URL`, `COMFY_IS_WINDOWS`, `WIN_SSH_HOST/USER/PASS`, `WIN_COMFY_INPUT`,
`REMOTE_SSH_USER/HOST/PORT`, `REMOTE_BASE_PATH`, `LOCAL_TTS_URL`, `MEDIA_OPS_TOKEN`,
`OPENAI_API_KEY`, `ASD_WORKER_URL`, `PERSON_WORKER_URL`.

**Seguridad:** `.env` contiene secretos y `*.mp3`/modelos están gitignored. **Nunca** commitear
`.env` ni enviar su contenido a terceros. Email del usuario (identidad): enguillem@gmail.com.

---

## 6. Estructura del código

```
backend/
  app/
    main.py            # FastAPI: todos los endpoints + enqueue_job + helpers
    db.py              # SQLite: esquema, migraciones, CRUD (clips, channels, campaigns, reels, plant_videos)
    services/
      clip_detector.py   # detect_clips(subs) -> momentos "virales" (OpenAI)
      clip_seo.py        # generate_clip_seo(clip, channel) -> {title, description, tags}
      seo_engine.py      # SEOEngine: generate_video_title / generate_description / tags
      reel_engine.py     # guiones: generate_script, hook_text, thumbnail_prompt, match_script,
                         #          content_text (transcribe si no hay guion), broll_prompts_for
      tts_client.py      # XTTS: synthesize(text, voice, out, lang); _split_text; detect_language
      transcription.py   # AssemblyAiTranscriptionService.transcribe(mp3, lang, subtitle_format)
      comfy_client.py    # ComfyUI texto→imagen (SDXL, reel_broll.json); generate_image(prompt,out,negative=...)
      wan_client.py      # ComfyUI WAN i2v (wan_ti2v.json): upload_image + generate_video (inyecta por class_type)
      plant_engine.py    # motor Macetas: plant_ideas, plant_plan(planta,aspect)->{locked_scene,image_prompt,clips[3]}
      youtube_service.py # YouTubeService(channel_id).upload_video(...)
      person_client.py / asd_client.py  # workers de blur / active-speaker
  scripts/             # JOBS y utilidades (se ejecutan como subprocesos)
    reel_broll.py        # b-roll IA: transcribe audio -> imágenes SDXL sincronizadas -> compose
    reel_compose.py      # compone reel vertical: --images | --bg-video | fondo; karaoke; música
    reel_match.py        # reel de partido: descarga+transcribe+momentos+guion+voz+fragmentos+compose (+ --render-only)
    reel_thumbnail.py    # miniatura (PIL, fuente Anton): --mode preview|append
    reel_upload.py       # sube reel a YouTube con SEO (respeta title/seo_description guardados)
    plant_video.py       # JOB Macetas: plan -> 1ª imagen (maceta vacía) -> 3 clips WAN encadenados -> montaje
    subtitle_engine.py   # SubtitleEngine: transcribe_words (AssemblyAI) + karaoke .ass + burn
    download_video.py / download_and_transcribe_video.py  # yt-dlp (+deno) + AssemblyAI
    render_clip.py / make_vertical_clip.py / render_all.py  # render de clips de campaña
  workflows/
    reel_broll.json      # SDXL vertical (RealVisXL) para b-roll/imágenes
    wan_ti2v.json        # WAN 2.2 TI2V-5B i2v (ACTIVO en Macetas): UNETLoader fp16 + Turbo LoRA 6 pasos
    wan_i2v.json         # WAN 2.2 A14B i2v (referencia; NO usar: no cabe en 16GB)
  assets/
    fonts/Anton-Regular.ttf   # fuente miniaturas (estilo videos_automaticos)
    music/*.mp3               # banco de música de fondo (Suno, gitignored) — ver assets/music/README.md
frontend/src/
  App.tsx              # toda la UI (secciones: dashboard, content, clipping, reels, plants, channel, execute, jobs, files)
  api.ts               # cliente HTTP (todas las llamadas)
  types.ts             # tipos (ClipCandidate, ReelItem, PlantItem, Campaign, ...)
  styles.css           # estilos + responsive móvil
output/                # salidas (clips, reels, plants/, uploads) — gitignored
```

---

## 7. Avatar Reel (contenido propio con IA) — funcionando

Flujo en la sección **🎬 Avatar Reel**:
1. **Disparador** (tema/noticia) → **Generar guion** (`reel_engine.generate_script`, OpenAI).
2. **Generar voz** (`tts_client.synthesize`, XTTS clonada) → persiste el reel (`reels` en DB).
3. **Componer**: `🎬 Fondo simple` (negro+karaoke) o `🎨 Con imágenes IA` (`reel_broll.py`: transcribe
   el audio, genera 1 imagen SDXL por tramo hablado anclada a lo que se dice, slideshow sincronizado).
4. **🔎 SEO**: `✨ Generar título` / `✨ Generar descripción` (`SEOEngine`, en el idioma del contenido;
   descripción sin título dentro y con enlace del vídeo original al final si el disparador es una URL).
   Se guardan y `reel_upload.py` los respeta.
5. **🖼 Miniatura**: preview (`reel_thumbnail.py --mode preview`) con estilo de `videos_automaticos`
   (fuente Anton, 2 líneas, degradado amarillo→dorado + naranja, scrim) → `✅ Añadir al final`
   (`--mode append`, la deja como **último fotograma** para elegirla de portada en el móvil).
6. **📤 Subir a YouTube** al canal elegido.

Música de fondo: `reel_compose` añade un `.mp3` aleatorio de `backend/assets/music/` bajo la voz
(volumen 0.10, fade-out), salvo `--no-music`.

Detalle importante: **regenerar la voz borra el `video_path`** del reel (el vídeo viejo ya no vale).

---

## 8. Reels de partido — funcionando (con caveat de copyright)

Sección Avatar Reel, bloque **⚽ "Reel desde un resumen de partido"**. Job `reel_match.py`:
descarga (`download_video`, yt-dlp; **pasar `ffmpeg_path=None`** para que use el ffmpeg del PATH y
pueda fusionar formatos) → transcribe (AssemblyAI) → `clip_detector.detect_clips` (momentos clave) →
`reel_engine.match_script` (guion explicativo) → voz XTTS → **fragmentos de vídeo reales** del partido
recortados a vertical con fondo desenfocado (`_vertical_clip` + `_build_bgvideo`) → `reel_compose --bg-video`
(karaoke + música). Guarda `source_video` para el botón **🎬 Renderizar** (`--render-only`: re-monta
reusando guion+voz sin rehacer todo). ⚠️ Ver §11 (Content ID).

---

## 9. Clipping / Campañas (base histórica)

Ver `doc/03-pipeline-y-servicios.md` y `doc/07-asd-active-speaker.md`. Resumen: campañas por canal,
descarga+transcripción del vídeo fuente, `detect_clips` propone candidatos, edición (enfoque
left/center/right/follow/**facecam**, zoom, blur de personas semi-auto), render vertical con
subtítulos, SEO por clip y subida. Duración por defecto de campaña nueva: 40s.

---

## 10. 🪴 Macetas (WAN time-lapse) — EN DESARROLLO

Objetivo (inspirado en `plant_growth.pdf` en la raíz): vídeos satisfactorios de una planta creciendo
en una maceta, en time-lapse, 100% IA (sin copyright). Pipeline `plant_video.py`:
**plan (LLM)** → **primera imagen** (maceta VACÍA, SDXL) → **3 clips WAN i2v encadenados por el último
fotograma** → **montaje vertical** (ffmpeg concat).

### Estado y decisiones tomadas
- Modelo: **WAN 2.2 TI2V-5B fp16** (`wan2.2_ti2v_5B_fp16.safetensors`, ~10 GB) + **Turbo LoRA**
  (`Wan22_TI2V_5B_Turbo_rank64.safetensors`, 6 pasos) + VAE `wan2.2_vae.safetensors` + encoder
  `umt5-xxl-encoder-Q8_0.gguf`. Workflow: `backend/workflows/wan_ti2v.json`. Todo ya descargado en el box.
- **A14B NO** (30 GB, no cabe en 16 GB → swap → 20+ min/clip). El GGUF Q8 de 5B tampoco (offload por
  capas, VRAM ~2.5 GB, lento). **fp16 residente** es lo correcto (VRAM ~12 GB, ~6 min/clip en caliente).
- **Calidad de crecimiento: excelente y realista** (validado con clips de limón).
- **WAN NO sabe** coreografiar "una mano planta la semilla" ni la cosecha (eso es Veo/Google Flow).
  Decisión del usuario: **solo crecimiento** (tierra pelada → brote emerge → planta → flor/fruto,
  sin manos). Motor `plant_engine.py` ya reenfocado a eso.
- **Maceta vacía**: RealVisXL insistía en meter una planta; se fuerza con **negatives ponderados**
  (`(plant:1.6),(leaves:1.6),(succulent:1.5)...`) vía `comfy_client.generate_image(..., negative=...)`.

### Pendiente (retomar aquí)
1. Arrancar ComfyUI en el Windows (`start.bat`) — **la GPU/ComfyUI estaban apagados al cerrar**.
2. Lanzar un vídeo completo de limón con el enfoque "solo crecimiento" y validar que el clip 1
   arranca de tierra y el brote **emerge** (antes salía ya brotado en el frame 1 — vigilar).
3. Si convence: montar una **cola/batch** (pegar varias plantas, generarlas secuencialmente de
   noche — encaja con ~20-25 min/vídeo). El usuario generará "el arboretum por las noches".
4. Ajuste fácil de velocidad si hace falta: bajar resolución (pedir 288×512 → sale ~576×1024).

Nota WAN: la salida sale al **doble** de la resolución pedida (VAE 2.2). Vídeos **mudos** (ASMR
diegético, sin música — el PDF lo pide así). El polling a `/history` debe tener timeout amplio y
reintentos (ComfyUI satura la GPU y tarda en responder). Tras un OOM, ComfyUI queda "colgado en CPU"
(VRAM libre con job corriendo) → **hay que reiniciar ComfyUI**.

---

## 11. Gotchas / lecciones (no tropezar otra vez)

- **Editar `.py` durante un request síncrono largo → lo mata** (reload). Usar jobs. (§3)
- **ffmpeg `-loop 1` + `-shortest` → exit 255** en slideshows. Usar **concat demuxer** (ffconcat).
- **Caché de subtítulos por reel**: `subtitle_engine` usa nombres fijos → colisiona entre reels de la
  misma carpeta. Cada reel usa `cache_dir = out.parent/.sub_<stem>`.
- **YouTube/yt-dlp**: requiere **deno** (reto JS); formato `bestvideo[vcodec^=avc1][height<=1080]+bestaudio...`
  + `extractor_args player_client=[default]` para evitar 403/DRM. `download_video(url, ffmpeg_path=None, ...)`.
- **Content ID (§8)**: el metraje real de partidos LALIGA recibe reclamo automático → vídeo bloqueado
  en territorios. No se puede (ni se debe) "esquivar" la detección. Para fútbol legal: b-roll IA o
  material con licencia. El usuario sube reels de partido a una **cuenta secundaria** para aislar la principal.
- **scp trunca**; usar base64 vía PowerShell (§4).
- **VRAM 16 GB** manda en la elección de modelos WAN (§10).
- Frontend es **build de producción**: recordar `docker compose build frontend` tras cambios.

---

## 12. Convenciones

- **Commits** terminan con: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.
  **PRs** terminan con: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`.
- **Mantener `doc/` al día** con cada cambio relevante (hay memoria del usuario sobre esto).
- Reusar piezas del proyecto hermano **`videos_automaticos`** (host Windows `D:\videos_automaticos`,
  repo `github.com:guillemweb25-cell/videos_automaticos`) — de ahí salieron: patrón `comfy_service`,
  chunking de TTS, fuente Anton para miniaturas, banco de música Suno, workflow WAN i2v. Ver
  `videos_automaticos.md` en la raíz.
- Otro proyecto hermano con pipeline WAN de shorts: `ssh 5622enguillem` →
  `/home/guillem/code/myAutoYTB2/project_youtube_shorts` (de ahí salió `wan2.2_i2v-1-workflow.json`
  y `src/ytVideo/routers/comfy_video.py` con la orquestación WAN de referencia).

---

## 13. Verificación rápida al empezar una sesión

```bash
docker compose ps                                  # ¿backend y frontend up?
curl -s -o /dev/null -w "%{http_code}" localhost:8800/api/reels   # 401 = backend vivo (auth)
docker exec intro_python_backend python3 -c "import requests;print(requests.get('http://192.168.1.46:8188/system_stats',timeout=8).ok)"  # ¿ComfyUI/GPU?
docker exec intro_python_backend python3 -c "import requests;print(requests.get('http://192.168.1.46:8022',timeout=5).status_code)"       # ¿XTTS?
```

Si vas a generar con WAN/ComfyUI: confirma que el **Windows está encendido** y ComfyUI arrancado.
