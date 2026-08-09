# 03 — Pipeline de vídeo y servicios de IA

## Descarga + transcripción del vídeo fuente

- `video_download.py` / `download_*.py`: yt-dlp con fallbacks:
  - `curl_cffi` (impersonation de navegador) para 403 / Cloudflare.
  - `kvs_fallback.py`: extractor para sitios KVS con variable `flashvars` aleatoria
    (parser de llaves balanceadas + reutiliza `GenericIE._kvs_get_real_url`).
  - `wetransfer_dl.py`: resuelve links de WeTransfer (API `/transfers/{id}/download` → `direct_link`).
- Transcripción → fichero de subtítulos con tiempos. La transcripción (`.txt`/`.vtt`)
  es la **fuente de verdad** para detectar clips; el nexo con la campaña es su ruta.

## Detección de clips — `services/clip_detector.py`

`detect_clips(subtitles_path, parts=4, clips_per_part=5, target_dur=25, model=None)`:
- Divide las cues de la transcripción en `parts` trozos (`_resolve_parts`: auto ≈ 1
  parte por cada 15 min de vídeo → más cobertura y peticiones más pequeñas a OpenAI).
- Por cada trozo, una llamada a OpenAI (gpt-4o) pidiendo `clips_per_part` clips de
  ~`target_dur` s (min = target−10, max = target+15).
- Agrega todos y ordena cronológicamente por `start`.
- Cada clip: `{start, end, title, reason, score, transcript}`.

## Render de UN clip — `render_clip.py`

Orquesta el pipeline completo de un short. Argumentos: `--video --start --end --out
--top-ratio --focus --zoom --subtitles --lang --overlay --endcard --ffmpeg`.

Orden de pasos:

1. **Composición vertical** — `make_vertical_clip.py` (`make_clip`):
   - Lienzo 1080×1920. `build_filter(top_ratio, focus, zoom, duration)`:
     - **Arriba** (`top_ratio`): recorte enfocado del vídeo. `scale=…force_original_aspect_ratio=increase,crop=…:{x_expr}:(ih-oh)/2`.
       `focus` → `x_expr`: left `0`, center `(iw-ow)/2`, right `iw-ow`. `zoom` amplía el recorte.
     - **Abajo** (resto): la escena COMPLETA sin recortar, con letterbox (`force_original_aspect_ratio=decrease,pad=…:color=black`).
2. **Extraer fotograma de cierre LIMPIO** (si `--endcard > 0`): se saca AHORA del
   vertical (antes de quemar karaoke/overlay) al `endcard%`, para que la miniatura
   no arrastre subtítulos. Se pasa luego como `clean_frame`.
3. **Subtítulos karaoke** (si `--subtitles`) — `subtitle_engine.py` (`add_subtitles`):
   - Extrae audio → AssemblyAI transcribe **por palabra** (`transcribe_words`, con `--lang`).
   - Genera ASS con tags `\kf` (resaltado karaoke palabra a palabra).
   - Estilo `Karaoke`: Alignment 2 (abajo-centro), `MarginV = 22%` del alto (vertical).
   - Quema con ffmpeg.
4. **Caption fijo (overlay)** (si `--overlay`) — `burn_overlay`:
   - Texto persistente en una **barra semitransparente** dibujada con ASS
     (`{\pos(0,0)\p1}m 0 y1 l W y1 W y2 0 y2{\p0}`) + texto amarillo negrita.
   - Posición `center_y = 0.63*H` (por ENCIMA del karaoke, que sube hasta ~0.71*H).
5. **Cierre + miniatura** (si `--endcard > 0`) — `add_fade_and_endcard`:
   - **Sin fundido a negro.** El clip corta a `duration − fade_secs`; esos últimos
     segundos de vídeo se sustituyen por el fotograma fijo (`clean_frame`) mientras
     el **audio hace fade out** (la cola del clip suena bajo el fotograma). Tras el
     fadeout el fotograma se mantiene `hold_secs` (para usarlo de miniatura).
   - El fotograma lleva el caption obligatorio en grande (barra semitransparente +
     amarillo negrita, `_endcard_ass`, font ~0.06*W).
   - Implementación ffmpeg: `body` (0…body_dur) + `endcard` (frame loop + ass +
     audio = cola con `afade=out` + `apad`) unidos con `concat=n=2:v=1:a=1`.

## Render EN COLA — `render_all.py`

Renderiza secuencialmente todos los clips **pendientes** (sin `rendered_path`
existente) de una transcripción. Corre como **un solo job de backend**, así sobrevive
a recargas del navegador. Args: `--transcript --focus`.
- Aplica el `--focus` global a cada clip (update_clip) antes de renderizar.
- Reutiliza `render_clip.py` por clip (subproceso), heredando su stdout al log.
- Marca `rendered_path` antes de renderizar (igual que el endpoint individual).

## Subida a YouTube — `upload_clip.py` + `services/youtube_service.py`

`upload_clip.py --clip --privacy`:
- Reutiliza el SEO ya previsualizado (`seo_title/description/tags`) o lo genera.
- Quita comillas envolventes del título (`strip_wrapping_quotes`).
- Sube con `YouTubeService.upload_video` y guarda `youtube_url`, `youtube_privacy`
  y `uploaded_at` (ISO UTC, para la cuenta atrás de 30 min).

`YouTubeService` (credenciales por canal en `youtube_creds/channel_{id:04d}/`):
- `get_auth_url` (prompt `select_account consent`, `state = channel_id`, redirect a
  la raíz de la app), `finish_oauth`, `is_authenticated`, `unlink`.
- `upload_video(path, metadata)`: `videos.insert`. **Sanea los tags**: YouTube
  envuelve entre comillas los tags con espacios y esas comillas cuentan para el
  límite de 500 → se cuenta el coste real (len + 2 comillas si multi-palabra + 1) con
  margen a 480, se descartan frases > 60 y se limpian `< > " ? ¿`.
- `set_video_privacy(video_id, privacy)`: `videos.update` (más barato que un insert).

> **Cuota YouTube:** insert ≈ 1600 unidades, update ≈ 50, límite diario 10 000 →
> ~6 subidas/día por proyecto. Para escalar: pedir ampliación o varios proyectos.

## SEO por clip — `services/clip_seo.py` + `seo_engine.py`

`generate_clip_seo(clip, channel, root, campaign_rules)`:
- Título y descripción con OpenAI (gpt-4o-mini) según idioma y `seo_rules` del canal.
- `strip_markdown` (respeta hashtags `#shorts`), `strip_wrapping_quotes` en el título.
- Pone el `captionRequired` + el handle de YouTube (`handles.youtube`) AL PRINCIPIO de
  la descripción (compliance visible; un rejection típico es "tag properly" cuando el
  handle iba enterrado al final). Añade los `hashtags` de la campaña al final.
- Añade título + link del vídeo original en la descripción, **salvo** si la fuente es
  WeTransfer (no se expone ese link).

## Compliance del brief — `services/brief_extractor.py`

- `fetch_brief_text`: descarga el Google Doc (`export?format=txt`).
- `extract_rules`: OpenAI devuelve JSON con las reglas (caption obligatorio, handles
  por plataforma, hashtags, watermark, fuente…). Se guardan en `campaigns.rules_json`
  y se auto-aplican (texto en pantalla + añadidos a la descripción al subir).
  - `onScreenText` se deja VACÍO si el brief solo pide subtítulos que coincidan con el
    diálogo (eso ya es el karaoke); solo se rellena si exige una frase/handle FIJA quemada.
  - `captionRequired` vacío si el requisito del caption son solo hashtags/menciones.
  - `notes` recoge tramos/segmentos prohibidos de clipear (ej: "no clipear 14:32-14:43").

## Utilidades

- `privatize_pending.py --channel --cutoff --apply`: privatiza vídeos antiguos de un
  canal (p.ej. contenido previo al renombrarlo) SIN tocar los clips de campaña.
  Doble salvaguarda: conserva los `video_id` que están en la BD (subidos por la app)
  y los publicados a partir del cutoff. Dry-run por defecto.
