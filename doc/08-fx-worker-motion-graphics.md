# 08 — FX Worker (motion graphics en clips y reels)

Capa de efectos animados para los vídeos verticales: subtítulos animados, zooms de
punch, título gancho cinético, barra de progreso, endcard animado, emojis y efectos de
sonido (estilo Opus Clip / Submagic). **Opcional y desacoplada**: si el worker no
está, se usa el camino actual (ffmpeg + ASS).

Consumidores previstos:

1. **Clipping / campañas** (`render_clip.py`, `render_all.py`).
2. **Avatar Reel y reels de partido** (`reel_compose.py`), que hoy también queman
   karaoke y música con ffmpeg.
3. (Opcional) **Macetas / Huevos / Mariposas**: solo título gancho y endcard.

> Origen de la idea: un tráiler de motion graphics hecho por Claude con escenas
> HTML/JS en función del tiempo, capturadas con Chrome headless y montadas con
> ffmpeg. Es render **determinista por código**, no IA de vídeo. Aquí se aplica la
> misma técnica usando **Remotion** como motor, en vez de reinventarlo.

---

## Decisiones

| Decisión | Motivo |
|----------|--------|
| **No migrar** el backend a Fastify + MariaDB | FastAPI + SQLite funciona. Un usuario y jobs secuenciales no necesitan MariaDB. Reescribir cuesta semanas sin ganancia. |
| Worker **separado** en Node + TypeScript + Remotion | Remotion ya resuelve timeline, render frame a frame con Chromium, audio y ffmpeg. Imagen Docker oficial. |
| Mismo patrón que `asd_worker` y `person_worker` | HTTP + cliente con **fallback**. Si el worker cae, el vídeo sale con el render ASS de siempre. |
| ffmpeg sigue haciendo la composición | Composición vertical, ASD, enfoque por tramo, facecam y blur de personas no cambian. Remotion solo pinta encima. |
| Tiempos por palabra de AssemblyAI | Ya se pagan en `subtitle_engine.py`. Se exportan como JSON en vez de convertirse a ASS. |
| Reutilizar assets existentes | Fuente `backend/assets/fonts/Anton-Regular.ttf` (la de videos_automaticos) y banco `backend/assets/music/`. |
| **La compliance falla en voz alta**, igual que blur y watermark | Si el FX no puede garantizar watermark u overlay, error o fallback; **nunca** un clip no conforme. |

---

## Arquitectura

### Clipping (`render_clip.py`)

```
 1. apply_person_blur (YOLO + regiones manuales)          ← sin cambios (falla si se pidió y no se aplica)
 2. make_vertical_clip (centro / follow / plan por tramo / facecam)  ← sin cambios
 3. ¿FX activo? (FX_WORKER_URL definido y fx_preset != "none")
    ├─ sí → NO se aplica add_watermark con ffmpeg (ver "Watermark y zooms")
    │       fotograma limpio del vertical SIN watermark
    │       transcribe_words (AssemblyAI)
    │       fx_client.render(vertical, payload, watermark.png, endcard_frame)
    │         ├─ OK    → final.mp4 (watermark como capa fija dentro de Remotion)
    │         └─ falla → seguir por el camino ASS (paso 4), aviso en el log
    └─ no  → paso 4
 4. Camino actual: add_watermark (ffmpeg) → fotograma limpio → karaoke ASS
                   → burn_overlay → add_fade_and_endcard
```

### Reels (`reel_compose.py`)

```
fondo / b-roll / fragmentos del partido (ffmpeg)
  → ¿FX activo? sí → fx_client.render(base, payload con palabras + hook + música)
                no → karaoke ASS + add_background_music (actual)
```

### Despliegue

```
Docker app (Debian)                         FX Worker (Node + Remotion, CPU)
  fx_client.py  ──POST multipart──────►     POST /render
    vertical.mp4 + payload.json               Remotion renderMedia()
    + watermark.png + endcard.png             composición "Short" según preset
                ◄──── final.mp4 ────
```

- **Dónde corre:** en el **compose del Debian**, junto a backend y frontend. Remotion
  es CPU; la máquina Windows ya está cargada con la GPU (WAN, ASD, YOLO) y meter ahí
  otro worker solo añade los problemas de despliegue conocidos (scp que trunca,
  watcher sobre bind-mount). Solo se movería si la CPU del Debian se queda corta.

  > **Revisado el 2026-10-17 (aparcado, no decidido).** Medido: el Debian va al
  > tope de RAM (11,7 de 12 GB) y en el Proxmox las VMs suman 32,4 GB asignados
  > sobre 30 GB físicos, así que no se le puede dar más. El Windows tiene 32 GB
  > con ~12 libres. Si el FX acaba siendo el cuello de botella, **mover solo el
  > worker** (no la app): corre nativo en Windows sin Docker (`npm ci` +
  > `node src/index.ts`), así que no aplican los problemas de despliegue de
  > arriba, que eran por los modelos grandes y el `--reload` de los workers de
  > GPU. Bastaría con `FX_WORKER_URL=http://192.168.1.46:8910`. Migrar la app
  > entera se descartó: 50 contenedores Linux, nginx, certificados y dominio
  > público, y en WSL2 los bind mounts con vídeo van lentos.
- **Sin `--reload`** en el worker (lección del `person_worker`). Deploy = rebuild + `up -d`.
- **Cliente:** `backend/app/services/fx_client.py`. Sube los ficheros, descarga el MP4,
  devuelve `None` ante timeout o error y **reintenta 1 vez**, como `person_client.blur`.
- **Config:** `FX_WORKER_URL` en `.env` (p.ej. `http://fx_worker:3000`). Vacía = desactivado.

---

## Watermark y zooms (importante)

Hoy `add_watermark` quema el PNG de campaña en el vertical **antes** del fotograma
de cierre (para que salga en la miniatura). Si el FX recibe ese vídeo ya marcado,
los **punch zooms escalarían también el watermark**: se movería, crecería y podría
recortarse. Eso es no conforme.

Por eso, en el camino FX:

- `render_clip` **no** llama a `add_watermark`. Manda el PNG al worker aparte.
- Remotion lo pinta como **capa fija superior** (42 % del ancho, margen superior 3 %,
  mismos valores que `add_watermark`), fuera de la capa que se escala.
- El endcard también lleva la capa de watermark (la miniatura sigue cumpliendo).
- Si el payload pide watermark y el PNG no llega o no se puede cargar, el worker
  responde **error** y no genera nada. `render_clip` cae entonces al camino ASS,
  que aplica el watermark con ffmpeg y, si también falla, aborta como hoy.

El **blur** (personas y regiones manuales) se aplica antes de componer, así que los
zooms no le afectan: lo difuminado sigue difuminado.

---

## Contrato `POST /render`

Multipart: `video` (MP4 vertical 1080×1920), `watermark` (PNG, opcional),
`endcard_frame` (PNG, opcional), `payload` (JSON):

```json
{
  "fps": 30,
  "duration": 28.4,
  "preset": "hormozi",
  "layout": { "mode": "split", "top_ratio": 0.50 },
  "words": [
    { "text": "nadie", "start": 0.12, "end": 0.38 },
    { "text": "se",    "start": 0.38, "end": 0.47 }
  ],
  "emphasis": [
    { "word_index": 14, "effect": "punch_zoom" },
    { "word_index": 31, "effect": "emoji", "emoji": "🔥" }
  ],
  "hook": { "text": "Nadie se esperaba esto", "duration": 2.0 },
  "overlay": { "text": "Link en @canal", "center_y": 0.63 },
  "watermark": { "required": true, "width_frac": 0.42, "top_frac": 0.03 },
  "safe_zones": [
    { "name": "watermark", "y0": 0.00, "y1": 0.14 },
    { "name": "overlay",   "y0": 0.58, "y1": 0.68 },
    { "name": "yt_ui",     "y0": 0.85, "y1": 1.00 }
  ],
  "endcard": { "caption": "Texto obligatorio", "fade_secs": 1.5, "hold_secs": 2.0 },
  "progress_bar": "split_line",
  "sfx": true,
  "music": { "file": null, "volume": 0.10, "duck": true },
  "brand": { "font": "Anton", "primary": "#FFD400", "stroke": "#000000" }
}
```

- `layout.mode`: `split` (arriba recorte, abajo escena completa), `facecam`
  (arriba webcam, abajo pantalla con zoom) o `full` (reels). Sirve para colocar
  subtítulos y emojis respetando la línea de corte y para decidir **qué** se escala
  en un punch zoom: en `facecam` solo la cara, nunca la pantalla, que debe leerse.
- `watermark` y la zona `watermark` se envían solo si la campaña tiene `watermarkPath`.
- `progress_bar`: `top`, `split_line` u `off`. **Con watermark, nunca `top`.**
- `music.file`: `null` = una aleatoria del banco `backend/assets/music/` (montado
  en el worker).

Respuesta: `200 video/mp4` con el vídeo final, o `4xx/5xx` con `{error}`.
`GET /health` → `{ok: true, presets: [...]}` (el backend lo usa para el selector de la UI).

---

## Composición Remotion

Composición `Short` (1080×1920), capas en función del frame, de abajo arriba:

| Capa | Contenido |
|------|-----------|
| `BaseVideo` | `<OffthreadVideo>` del vertical. Punch zooms (easing 0.25 s in / 0.4 s out) según `layout.mode`. |
| `Hook` | Título gancho con tipografía cinética los primeros `hook.duration` s. Fuera de la zona del watermark. |
| `Captions` | Subtítulos por palabra en frases de 2–4 palabras, palabra activa resaltada (color, escala, pop). |
| `Emojis` | Pop-in sobre la palabra marcada, respetando `safe_zones`. |
| `Overlay` | Caption fijo del brief. **No lo tapa ninguna capa.** |
| `ProgressBar` | Según `progress_bar`. |
| `Watermark` | PNG de campaña fijo, **nunca escalado**. |
| `Endcard` | Fotograma limpio + caption obligatorio + watermark, con entrada animada; audio con fade out como ahora. |
| `Audio` | Audio original + SFX (whoosh en cortes, pop en emojis) + música con ducking bajo la voz. Solo SFX libres en `fx_worker/assets/sfx/`. |

**Presets** (`fx_worker/src/presets/*.ts`): fuente, colores, tamaño, posición y tipo
de animación. Iniciales: `hormozi` (Anton, mayúsculas, amarillo, pop fuerte),
`minimal` (blanco, fade suave) y `none` (no se llama al worker).

---

## Cambios en el repo

### Backend

- `services/fx_client.py`: `render_fx(base_path, payload, watermark=None, endcard_frame=None) -> Path | None`,
  con timeout amplio (≈ 1–3 min por clip) y 1 reintento.
- `scripts/render_clip.py`:
  - Nuevo argumento `--fx-preset` (default `none`).
  - Rama FX según el diagrama: sin `add_watermark` en ffmpeg, payload con `layout`
    (`split`/`facecam` según `--facecam`), palabras, hook, overlay, watermark y endcard.
  - Si `render_fx` devuelve `None` → camino ASS completo y aviso en el log.
- `scripts/render_all.py`: propagar `--fx-preset` global, igual que `--focus` (y
  re-renderizar los ya hechos si el preset cambia, como ya se hace con el encuadre).
- `scripts/reel_compose.py`: `--fx-preset`; si hay FX, el worker hace karaoke y
  música; si no, lo actual (`add_background_music` incluido).
- `services/clip_detector.py`: pedir por clip `hook` (≤ 6 palabras) y `emphasis_words`
  (2–4 palabras con más fuerza de la transcripción).
- `db.py`: migraciones idempotentes en `clips` (`fx_preset TEXT DEFAULT 'none'`,
  `hook TEXT`, `emphasis_json TEXT`) y en `campaigns` (`fx_preset_default TEXT DEFAULT 'none'`,
  para campañas que no admiten edición pesada).
- `main.py`: `GET /api/fx/presets` (proxy a `/health`; lista vacía sin worker) y
  aceptar `fx_preset` y `hook` en el update del clip.

### Frontend

- Selector de preset en la tarjeta del clip, uno global junto a "Renderizar todo",
  otro en la campaña (default) y otro en Avatar Reel.
- Campo editable `hook`.
- Si `/api/fx/presets` viene vacío, ocultar los selectores.
- **Recordatorio:** el frontend es build de producción con nginx (sin HMR). Tras
  tocar `frontend/src/**`: `npx tsc --noEmit` y luego
  `docker compose build frontend && docker compose up -d frontend`.

### docker-compose.yml

```yaml
  fx_worker:
    build: ./fx_worker
    container_name: intro_python_fx
    ports:
      - "8910:3000"
    volumes:
      - ./fx_worker/assets:/app/assets:ro
      - ./backend/assets/fonts:/app/fonts:ro
      - ./backend/assets/music:/app/music:ro
    shm_size: "1gb"   # Chromium headless lo necesita
```

---

## Compliance (campañas Whop / ClipFarm / Reach)

- `overlay` (`onScreenText`) y caption del endcard salen de `rules_json`, como ahora.
- Watermark de campaña: capa fija sin escalar, también en el endcard. Si falta → error.
- `safe_zones`: subtítulos, emojis y hook **no tapan** watermark, overlay ni la UI de
  Shorts (abajo ~15 %).
- Los zooms solo escalan el vídeo base, que ya va difuminado.
- Los tramos prohibidos (`notes` del brief) ya se excluyen en la detección; el worker
  no cambia tiempos.
- `campaigns.fx_preset_default`: `minimal` o `none` en campañas estrictas.
- **Reels de partido:** el FX no cambia nada respecto a Content ID. El metraje real
  sigue reclamándose; los efectos no lo "esquivan" ni deben usarse para eso.

---

## Rendimiento

- ffmpeg + ASS: segundos por clip. Remotion: ~1–3 min por clip de 30 s en CPU.
- Con `render_all.py` en cola no bloquea nada, pero un lote de 20 clips pasa de
  minutos a ~1 h.
- Palancas: `concurrency` de Remotion según núcleos del Debian, o renderizar a
  720×1280 y escalar si hace falta.

---

## Fases

Al pasarlo a `06-fases.md`, va como **Fase 13 — FX Worker (motion graphics)**, con
estas subfases:

**13A — Worker mínimo. ✅ Implementado.** `fx_worker/` con Remotion, `POST /render`,
`GET /health`, presets `minimal` y `hormozi` (subtítulos por palabra). Prueba con
`curl` (ver `fx_worker/README.md`).
*Hecho cuando:* un vertical + JSON de palabras devuelve un MP4 con subtítulos animados.

Se adelantaron dos cosas de 13B/13D porque callarlas habría dado clips no
conformes: el **caption fijo del brief** (`overlay`) y el **watermark como capa
fija sin escalar**. Y el worker **responde 422** si el payload pide una capa que
todavía no pinta (`hook`, `emphasis`, `endcard`, `progress_bar`, `sfx`, `music`),
en vez de ignorarla en silencio, para que el backend caiga al camino ASS.

También se añadieron ya `backend/app/services/fx_client.py` (con el fallback) y
`GET /api/fx/presets`, que es lo que 13B necesita para enchufarlo a
`render_clip.py`.

**Notas de implementación** (cosas que costaron y conviene no volver a descubrir):

- Las URLs que se le pasan a la composición (vídeo, watermark, fuente) tienen que
  ser **absolutas** al servidor del worker. Dentro de la composición, una ruta
  relativa la resuelve Chromium contra el servidor del bundle de Remotion, que
  está en otro puerto, y da 404.
- Esas rutas necesitan **`Access-Control-Allow-Origin`**: para Chromium el bundle
  es otro origen y las **fuentes** se bloquean por CORS aunque devuelvan 200.
- `npx remotion browser ensure` no sirve en la imagen de producción (vive en
  `@remotion/cli`, que es solo de desarrollo). Se usa `ensureBrowser()` de
  `@remotion/renderer`.
- **La concurrencia por defecto de Remotion (una pestaña por núcleo) tumba el
  navegador en esta VM por falta de RAM.** Está fijada a 1 en `FX_CONCURRENCY`,
  con `FX_SCALE` como segunda palanca (0.67 = 720x1280). Hay que subirla cuando
  la máquina mejore.

**13B — Integración en clipping con fallback. ✅ Implementado.** `fx_client.py`, `--fx-preset` en
`render_clip.py`/`render_all.py`, migraciones, selector en la UI, watermark como capa
fija.
*Hecho cuando:* con worker → clip con FX y watermark intacto; worker apagado → clip
ASS de siempre con watermark ffmpeg y aviso en el log. **Verificado con un render
real por los dos caminos**, comprobando el watermark en el clip y en el fotograma
de cierre.

**Decisiones de implementación:**

- **El endcard lo sigue montando ffmpeg**, por los dos caminos. El worker aún no
  lo pinta (13C) y rechazaría el payload entero, así que `endcard` NO se le
  manda: el camino FX hace subtítulos, overlay y watermark, y
  `add_fade_and_endcard` añade el cierre después, igual que siempre.
- Como en el camino FX el vertical va SIN watermark (lo pinta Remotion), el
  fotograma de cierre se marca aparte con `stamp_watermark_on_frame`, con la
  misma geometría que `add_watermark`. Sin eso la miniatura saldría sin marca.
- El preset se valida siempre contra `GET /api/fx/presets` (`_valid_fx_preset`):
  un preset guardado cuando el worker estaba vivo no rompe nada si luego se
  apaga, simplemente cae a `none`.
- Precedencia del preset: el del clip, si no el de la campaña
  (`fxPresetDefault`), si no `none`.
- En `render_all.py`, cambiar el preset global re-renderiza los clips ya hechos
  que tuvieran otro, igual que ya hacía el encuadre.
- Columnas nuevas: `clips.fx_preset` y `campaigns.fx_preset_default`. Las de
  `hook` y `emphasis_json` se dejan para 13C, cuando haya código que las use.

**13C — Efectos completos.** Preset `hormozi`, hook cinético, punch zooms (respetando
`facecam`), emojis, barra de progreso, endcard animado, SFX y ducking. `hook` y
`emphasis_words` desde `clip_detector.py`.
*Hecho cuando:* un clip detectado sale con todo sin tocar nada a mano.

**13D — Compliance y QA.** `safe_zones` desde las reglas de campaña,
`fx_preset_default` por campaña, revisión de que watermark y overlay nunca quedan
tapados ni escalados, en `split` y en `facecam`.
*Hecho cuando:* clips aceptados en una campaña real usando el preset `hormozi`.

**13E — Reels.** `reel_compose.py` usa el worker (karaoke, hook, música con ducking).
*Hecho cuando:* un Avatar Reel sale con FX y el camino actual sigue funcionando sin worker.

---

## Avisos

- **Licencia de Remotion:** gratis para particulares y empresas pequeñas; revisar si
  esto pasa a ser empresa con más gente.
- **Los efectos no salvan un clip flojo.** La retención depende sobre todo de la
  selección del tramo y del gancho; los FX suman, no sustituyen.
- **Fuentes y SFX con licencia libre.** Nada de sonidos o tipografías de terceros sin
  permiso en `fx_worker/assets/`.
- Añadir este documento al índice de `doc/README.md` y de `ONBOARDING.md`.
