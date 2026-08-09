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

## Estado / pendiente

- [x] Worker (`asd_worker/`) + contrato + cliente backend + caché + fallback.
- [ ] **Modo de encuadre "Seguir al hablante"** en el render (`make_vertical_clip` /
  `render_clip`): consume los segmentos del tramo del clip y mueve el recorte superior
  al `center_norm` del hablante activo, con suavizado e histéresis. Se implementa
  cuando el worker esté desplegado y tengamos un `asd.json` real que mirar.
- [ ] Opción "Seguir al hablante" en el selector de encuadre (individual y global).
