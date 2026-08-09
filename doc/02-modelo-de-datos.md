# 02 — Modelo de datos (SQLite)

Fichero: `backend/runs/jobs.db`. Sin ORM: SQL a mano en `backend/app/db.py`.
`db.init(path)` crea el `SCHEMA` (CREATE TABLE IF NOT EXISTS) y aplica las
listas de migraciones (ALTER TABLE envueltos en try/except `sqlite3.OperationalError`
para que sean idempotentes — si la columna ya existe, se ignora).

## Patrón de migraciones

Cada columna nueva se añade en dos sitios:
1. En el `CREATE TABLE` del `SCHEMA` (para bases nuevas).
2. En la lista `*_MIGRATIONS` como `ALTER TABLE ... ADD COLUMN ...` (para bases existentes).

Y además:
3. En `_<tabla>_to_dict` (mapeo fila → dict camelCase para el API).
4. En el set `allowed` de `update_<tabla>` si es editable.

```python
for stmt in CLIP_MIGRATIONS:
    try: conn.execute(stmt)
    except sqlite3.OperationalError: pass   # columna ya existe
```

## Tabla `jobs`

| Columna | Tipo | Notas |
|---------|------|-------|
| id | TEXT PK | 12 hex |
| script | TEXT | nombre del script ejecutado |
| args | TEXT | JSON de argumentos |
| command | TEXT | JSON del comando completo |
| status | TEXT | queued / running / completed / failed |
| created_at, started_at, ended_at | TEXT | ISO |
| return_code | INTEGER | |
| log_path | TEXT | ruta del log |

## Tabla `channels`

Un canal = una marca con su vinculación a YouTube y sus reglas SEO.

| Columna | Tipo | Notas |
|---------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| name | TEXT | |
| language | TEXT `'es'` | idioma para SEO y subtítulos (es/en) |
| seo_rules | TEXT | instrucciones SEO libres del canal |
| youtube_linked | INTEGER 0/1 | |
| youtube_name | TEXT | nombre del canal de YouTube vinculado |
| created_at | TEXT | |

Credenciales OAuth NO van en la BD: viven en `youtube_creds/channel_{id:04d}/`.

## Tabla `campaigns`

Una campaña = un vídeo fuente + un link de campaña (Whop) + su brief + sus clips.

| Columna | Tipo | Notas |
|---------|------|-------|
| id | INTEGER PK AUTOINCREMENT | |
| channel_id | INTEGER | canal al que pertenece |
| name | TEXT | |
| source_url | TEXT | vídeo a clipear (YouTube o WeTransfer) |
| campaign_url | TEXT | link de la campaña en Whop |
| transcript_path | TEXT | ruta de la transcripción (nexo con los clips) |
| video_path | TEXT | ruta del vídeo descargado |
| status | TEXT `'preparing'` | preparing / ready |
| created_at | TEXT | |
| brief_url | TEXT | Google Docs con las instrucciones |
| rules_json | TEXT | reglas de compliance extraídas (JSON, ver abajo) |

`rules_json` (parseado al dict `rules`): `onScreenText`, `captionRequired`,
`handles{youtube,tiktok,instagram}`, `hashtags[]`, `mentions[]`, `keepWatermark`,
`audience`, `payout`, `sourceUrl`, `notes`.

El nexo campaña↔clips es `transcript_path` (no un FK): `get_campaign_by_transcript(path)`.

## Tabla `clips`

Un clip = un candidato detectado con sus ajustes de render y su estado de subida.

| Columna | Tipo | Notas |
|---------|------|-------|
| id | TEXT PK | 12 hex |
| transcript_path | TEXT | nexo con la campaña |
| video_path | TEXT | vídeo fuente del que se corta |
| start, end | REAL | segundos |
| title, reason, score | TEXT/INT | de la detección IA |
| transcript | TEXT | texto del tramo |
| created_at | TEXT | |
| channel_id | INTEGER | canal destino |
| **focus** | TEXT `'center'` | encuadre del recorte superior: left/center/right |
| **zoom** | REAL `1.0` | zoom del recorte superior |
| **top_ratio** | REAL `0.7` | proporción pantalla partida (arriba/abajo) |
| **subtitles** | INTEGER `1` | quemar karaoke sí/no |
| rendered_path | TEXT | ruta del MP4 renderizado (vacío = sin render) |
| youtube_url | TEXT | URL tras subir (vacío = sin subir) |
| seo_title, seo_description, seo_tags | TEXT | SEO generado/previsualizado |
| **overlay_text** | TEXT | caption fijo visible todo el clip |
| youtube_privacy | TEXT | private/unlisted/public tras subir |
| **endcard_percent** | INTEGER `50` | % del clip para el fotograma de cierre (0 = sin cierre) |
| **submitted** | INTEGER `0` | marcado como enviado a Whop |
| **uploaded_at** | TEXT | ISO de la subida (para la cuenta atrás de 30 min) |

Estados derivados (los calcula el API en `_annotate_clip`, no son columnas):
- `rendered = bool(rendered_path) and el fichero existe`
- `uploaded = bool(youtube_url)`

Índice: `idx_clips_transcript ON clips(transcript_path)`.

Funciones clave en `db.py`:
- `replace_clips(transcript_path, video_path, channel_id, clips, created_at)`:
  reemplaza los clips **detectados** de una transcripción borrando solo los que no
  tienen render ni youtube (`rendered_path='' AND youtube_url=''`), así al re-detectar
  no se pierden los ya trabajados. Inserta `endcard_percent=50` por defecto.
- `load_clips(transcript_path)`, `get_clip(id)`, `update_clip(id, fields)` (con set `allowed`).
- `get_campaign_by_transcript(path)` para recuperar las reglas de compliance al subir.
