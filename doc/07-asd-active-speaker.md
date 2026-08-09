# 07 — Active Speaker Detection ("Seguir al hablante")

Encuadre dinámico que recorta a **quien está hablando** en cada momento (estilo Opus
Clip), para podcasts en plano fijo de 2+ personas donde centro/izq/der quedan mal.

## Arquitectura (desacoplada de la GPU)

La GPU (RTX 4060) vive en el **Windows** (junto a videos_automaticos). En vez de mover
el Docker de la app allí, se monta un **worker de GPU** aparte y la app lo llama:

```
Docker app (Debian)  ──HTTP POST vídeo──►  Worker ASD (Windows, WSL2 + Docker --gpus)
   asd_client.py                            TalkNet-ASD sobre la 4060
      │  ◄──── asd.json (segmentos) ────
      │  cachea en <carpeta_video>/asd.json (1 vez por vídeo fuente)
      ▼
   render modo "Seguir al hablante" → recorte dinámico por segmentos
```

- **Worker:** carpeta [`asd_worker/`](../asd_worker/) — FastAPI + TalkNet-ASD en un
  contenedor CUDA. Ver su `README.md` para desplegarlo en WSL2.
- **Cliente:** `backend/app/services/asd_client.py` — sube el vídeo, cachea `asd.json`,
  y devuelve `None` si el worker no responde (el render cae a encuadre manual).
- **Config:** variable de entorno `ASD_WORKER_URL` (p.ej. `http://192.168.1.46:8900`)
  en `.env`. Vacía = función desactivada (siempre encuadre manual).
- **Coste:** el ASD se corre **una vez por vídeo fuente** (no por clip) y se cachea;
  cada clip solo recorta los segmentos de su tramo.

## Pipeline del worker (TalkNet-ASD)

Reutiliza el `demoTalkNet.py` del repo (probado): `scene_detect → S3FD (caras) →
track_shot → crop_video → evaluate_network`. Produce `tracks.pckl` y `scores.pckl`
(por track: frames, bbox, y score de "habla" por frame; `score >= 0` ≈ hablando).

`run_talknet.py` los convierte en segmentos:
1. Centro (x,y) y tamaño de cada track (mediana de `proc_track`).
2. **Clustering** de tracks en hablantes por su x (cámara fija → cajas estables).
3. Score por hablante y frame (máx entre sus tracks, media temporal ±2 como el demo).
4. Hablante activo por frame = argmax si `score >= 0`, si no -1; los huecos (-1) se
   rellenan manteniendo el anterior (no saltar en silencios).
5. Frames→segmentos + fusión de los más cortos que `MIN_DWELL_SEC` (0.6 s).

## Contrato (asd.json)

```json
{
  "fps": 25.0,
  "duration_sec": 921.3,
  "frame_size": [1920, 1080],
  "speakers": [
    { "id": 0, "center_norm": [0.28, 0.55], "half_size_norm": 0.08 },
    { "id": 1, "center_norm": [0.74, 0.52], "half_size_norm": 0.08 }
  ],
  "segments": [
    { "start": 0.0,  "end": 3.2, "speaker": 0 },
    { "start": 3.2,  "end": 5.1, "speaker": 1 }
  ]
}
```

- `center_norm` / `half_size_norm`: posición y tamaño de la cara del hablante,
  normalizados a [0,1] sobre `frame_size`. El render los usa para posicionar el
  recorte vertical horizontalmente sobre el hablante activo.
- `speaker = -1`: nadie claro (silencio); el render mantiene el último o encuadra ancho.

## Estado

- [x] Worker (`asd_worker/`) + contrato + cliente backend + caché + fallback.
- [x] **Modo de encuadre "Seguir al hablante"** en el render: `render_clip.py` corta
  SOLO el tramo del clip, lo manda al worker (`asd_client.fetch_segments`, cache
  `asd_<clip>_<start>_<end>.json`) y pasa los segmentos a `make_vertical_clip`, que
  construye una `x` de recorte por tiempo (`_follow_x_expr`) que centra el recorte
  superior en la cara del hablante activo. Fallback a centro si el worker no responde.

  **Per-clip, NO vídeo entero (decisión):** el coste del ASD escala con la duración de
  lo que se analiza. Analizar el vídeo entero escala con la fuente (una fuente de 3 h =
  ~270k frames = inviable). Analizar por clip está ACOTADO por nº de clips × ~30s
  (~15k frames) sea cual sea la duración de la fuente. Se probó el vídeo entero y se
  descartó por esto. El worker tiene la visualización desactivada (paso más lento).
- [x] Opción "🎙 Seguir al hablante" en el selector de encuadre (individual y global).

Validado con el podcast WATO (plano fijo de 2 personas): detecta las 2 caras
(x≈0.17 izq / x≈0.86 der) y el recorte sigue al que habla en cada tramo.

## Despliegue real (Windows, RTX 4060 Ti)

Montado en `D:\media-ops-asd` (WSL2 + Docker Desktop, `--gpus`). `docker compose up`.
`ASD_WORKER_URL=http://192.168.1.46:8900` en el `.env` del backend (recrear el
contenedor backend tras añadirlo: `docker compose up -d --force-recreate backend`).

**El build DEBE ser interactivo** en la máquina (una terminal normal), no por SSH:
Docker Desktop usa el credential helper `wincred`, que falla en sesión SSH no
interactiva al resolver el manifest de la imagen base en el registry.

**Pines que hacen funcionar el TalkNet antiguo** (en `asd_worker/Dockerfile`):
base `pytorch/pytorch:2.1.0-cuda11.8-cudnn8-runtime`; `DEBIAN_FRONTEND=noninteractive`
(tzdata); TODO el pip en UN comando con `numpy==1.23.5` (alias `np.int` que usa el
repo, quitado en 1.24), `scipy==1.10.1`, `scikit-learn==1.2.2`, `pandas==1.5.3`,
`scenedetect==0.6.0.3`, `gdown<5` (aún soporta `--id`); y `MKL_THREADING_LAYER=GNU`
(en `docker-compose.yml`) para el choque MKL/OpenMP al lanzar demoTalkNet.
