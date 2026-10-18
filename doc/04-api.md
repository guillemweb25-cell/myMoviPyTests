# 04 — Referencia de API

Base: backend FastAPI. Todas requieren el token (Bearer / X-API-Key / `?token=`)
si `MEDIA_OPS_TOKEN` está definido.

## Sistema / jobs

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/health` | `{status, authRequired}` |
| GET | `/api/jobs` | lista de jobs |
| GET | `/api/jobs/{id}` | un job |
| GET | `/api/jobs/{id}/log` | contenido del log |
| GET | `/api/jobs/{id}/stream` | SSE del log en vivo (usar `?token=`) |
| POST | `/api/jobs` | lanzar un script arbitrario (UI "Ejecutar Scripts") |

## Canales

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/channels` | lista |
| POST | `/api/channels` | crear `{name, language, seoRules?}` |
| PATCH | `/api/channels/{id}` | actualizar |
| DELETE | `/api/channels/{id}` | borrar |

## YouTube (por canal)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/youtube/{channelId}/status` | `{hasSecret, linked, channelName}` |
| POST | `/api/youtube/{channelId}/secret` | subir `client_secret.json` (multipart) |
| GET | `/api/youtube/{channelId}/auth-url` | URL de consentimiento OAuth |
| POST | `/api/youtube/finish` | cerrar OAuth `{code, state}` (state = channelId) |
| POST | `/api/youtube/{channelId}/unlink` | desvincular (borra token) |

Flujo OAuth: `auth-url` → Google redirige a la raíz de la app con `?code=&state=` →
el frontend detecta esos params y hace `POST /api/youtube/finish`.

## Campañas

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/campaigns?channelId=` | lista del canal (incluye `clipStats` por campaña) |
| GET | `/api/campaigns/{id}` | una campaña (incluye `clipStats`) |
| POST | `/api/campaigns` | crear `{channelId, name, sourceUrl, campaignUrl, cookiesFile?}` → descarga+transcribe (job) |
| PATCH | `/api/campaigns/{id}` | actualizar `{name?, campaignUrl?, tagHandle?}` (la `@` se añade sola) |
| POST | `/api/campaigns/{id}/tag-descriptions` | antepone el canal a etiquetar a las descripciones SEO que no lo lleven (idempotente, no llama al modelo) |
| POST | `/api/campaigns/{id}/sync-youtube` | sube a YouTube la descripción guardada de los clips publicados. `{dryRun}` **por defecto `true`**: solo informa de qué tocaría |
| POST | `/api/campaigns/{id}/brief` | extraer reglas del brief `{briefUrl? | briefText?}` |
| POST | `/api/campaigns/{id}/apply-rules` | aplicar reglas a los clips |
| DELETE | `/api/campaigns/{id}` | borrar |

## Fuentes de clip

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/clips/sources?channelId=` | vídeos con transcripción disponibles |
| POST | `/api/clips/source-from-url` | descargar+transcribir una URL (job) |

## Clips

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/api/clips/detect` | `{transcriptPath, channelId, parts, clipsPerPart, targetDuration}` → detecta y guarda |
| POST | `/api/clips/manual` | `{transcriptPath, start, end, title?, channelId?}` (segundos) → añade un clip a mano con el texto de la transcripción de ese tramo y el texto en pantalla de la campaña; valida fin ≤ duración del vídeo |
| POST | `/api/clips/combine` | `{clipIds (≥2, mismo vídeo), targetDuration}` → la IA monta un clip nuevo con fragmentos de esos clips (corte seco). Ver `clip_combiner.py` |
| PATCH | `/api/clips/{id}/segments` | `{segments: [[s,e],...]}` (segundos del vídeo fuente) → cambia los fragmentos de un combinado y lo vuelve a montar; borra el render (no si ya está subido) |
| GET | `/api/clips/list?transcriptPath=` | clips guardados (con `rendered`/`uploaded` y `rawPath`: vertical sin subtítulos, o `null`) |
| PATCH | `/api/clips/{id}/trim` | `{start, end}` |
| PATCH | `/api/clips/{id}/settings` | `{focus, zoom, topRatio, subtitles, overlayText, endcardPercent}` |
| POST | `/api/clips/{id}/render` | render de UN clip (job) |
| GET | `/api/clips/{id}/horizontal` | tramo original en 16:9 sin subtítulos (H.264/AAC 720p, para WhatsApp); se genera al pedirlo y se cachea en `clips/clip_<id>_16x9_<ms0>_<ms1>.mp4` |
| POST | `/api/clips/render-all` | `{transcriptPath, focus}` → render EN COLA de los pendientes (job backend) |
| POST | `/api/clips/{id}/frames` | extrae 3 fotogramas (25/50/75%) del render para elegir miniatura |
| POST | `/api/clips/{id}/seo` | genera título/desc/tags |
| POST | `/api/clips/{id}/upload` | `{privacy}` → sube a YouTube (job) |
| | | **Resubir**: el mismo endpoint vale para un clip ya subido. YouTube no reemplaza el fichero, así que crea un vídeo NUEVO y el anterior sigue publicado; su URL se guarda en `clips.previous_youtube_url` para poder ir a ocultarlo |
| POST | `/api/clips/{id}/visibility` | `{privacy}` → cambia visibilidad tras subir |
| POST | `/api/clips/{id}/submitted` | `{submitted}` → marca enviado a Whop |

## Ficheros

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/api/files?path=` | listar directorio (dentro de `output/`) |
| GET | `/api/file?path=` | servir/descargar un fichero (acepta `?token=`) |

> **`clipStats`** (en las respuestas de campañas): `{total, rendered, uploaded, submitted}`,
> agregado de los clips por `transcript_path`. Se usa para el progreso en "Mis campañas".
