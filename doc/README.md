# Media Ops — Plataforma de Clipping (especificación)

Documentación para **reconstruir desde cero, por fases**, la parte de *clipping* de
este proyecto hasta llegar al estado actual. Pensada para abrir en un VS Code
limpio y ir levantando el proyecto guiándose por estas fases.

## Qué es

Aplicación web para **clip-farming**: a partir de un vídeo largo (un podcast, una
entrevista) detecta con IA los momentos más virales, los convierte en **shorts
verticales** (pantalla partida + subtítulos karaoke + caption fijo + cierre con
miniatura) y los sube a YouTube con SEO generado por IA, aplicando las reglas de
compliance de una campaña (ClipFarm/Whop).

Flujo de una campaña:

```
Vídeo largo (YouTube/WeTransfer)
   │  descarga + transcripción (AssemblyAI/Whisper)
   ▼
Detección de clips con IA (OpenAI)  ── divide la transcripción en partes, N clips por parte
   │
   ▼
Por cada clip:  ajustar (encuadre/zoom/proporción/subtítulos/trim/overlay)
   │            render vertical (ffmpeg) → karaoke → caption fijo → cierre+miniatura
   ▼
Subida a YouTube (SEO + compliance) → marcar "submiteado a Whop"
```

## Stack

| Capa       | Tecnología |
|------------|------------|
| Backend    | FastAPI (Python 3.11), uvicorn |
| Frontend   | React 18 + TypeScript + Vite |
| Infra      | Docker Compose (2 servicios) |
| Persistencia | SQLite (stdlib, sin ORM) |
| Jobs       | `threading` + `subprocess` (procesos de scripts), log por fichero, stream SSE |
| IA         | OpenAI (detección de clips, SEO, extracción de brief), AssemblyAI (subtítulos por palabra) |
| Vídeo      | ffmpeg / ffprobe (composición vertical, ASS karaoke, fades, endcard) |
| Descargas  | yt-dlp (+ curl_cffi para 403/Cloudflare, KVS fallback), resolutor WeTransfer |
| YouTube    | OAuth 2.0 por canal + YouTube Data API v3 (upload, update de privacidad) |

## Índice

1. [`01-arquitectura.md`](01-arquitectura.md) — infraestructura, Docker, auth, sistema de jobs.
2. [`02-modelo-de-datos.md`](02-modelo-de-datos.md) — esquema SQLite (channels, campaigns, clips, jobs) y migraciones.
3. [`03-pipeline-y-servicios.md`](03-pipeline-y-servicios.md) — el pipeline de vídeo y los servicios de IA, script por script.
4. [`04-api.md`](04-api.md) — referencia de endpoints.
5. [`05-frontend.md`](05-frontend.md) — estructura de la UI de clipping.
6. [`06-fases.md`](06-fases.md) — **hoja de ruta por fases para reconstruirlo** (empieza aquí si vas a rehacerlo).

## Cómo se ejecuta (estado actual)

```bash
docker compose up          # backend en :8800, frontend en :5074
```

- Backend: FastAPI con `--reload`, monta `.:/workspace`.
- Frontend: Vite dev server con HMR, monta `./frontend:/app`.
- Requiere `.env` (ver [`01-arquitectura.md`](01-arquitectura.md)).

> **Nota de compliance de campaña:** los vídeos deben publicarse en la plataforma
> destino en menos de **30 min** desde que se suben, o se rechazan. Por eso el flujo
> es "sube y submitea cada clip seguido", y la UI muestra una cuenta atrás.
