# ASD worker (TalkNet) — active speaker detection en la RTX 4060

Servicio de GPU que, dado un vídeo, devuelve los segmentos de **quién habla
cuándo** (para el modo de encuadre "Seguir al hablante" de la app de clipping).
Corre en el Windows (WSL2 + Docker con `--gpus all`); la app de Debian le sube el
vídeo por HTTP y cachea la respuesta.

## Requisitos en el Windows

1. **WSL2** con una distro (Ubuntu).
2. **Docker Desktop** con integración WSL2, o Docker dentro de WSL2.
3. **NVIDIA Container Toolkit** para pasar la GPU al contenedor (CUDA en WSL2 ya
   funciona con los drivers NVIDIA de Windows; no instales driver dentro de WSL).
   Comprueba: `docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi`

## Construir y arrancar

Desde esta carpeta (`asd_worker/`) copiada al Windows/WSL2:

```bash
docker build -t asd-worker .
docker run -d --name asd-worker --gpus all -p 8900:8900 \
  -v asd_data:/data --restart unless-stopped asd-worker
```

- `--restart unless-stopped` para que reviva tras reinicios.
- Prueba: `curl http://localhost:8900/health`  → `{"status":"ok"}`.
- Desde la máquina de Debian (misma LAN): `curl http://192.168.1.46:8900/health`.
  Abre el puerto 8900 en el firewall de Windows si no responde.

## Probar con un vídeo

```bash
curl -F "file=@clip.mp4" http://localhost:8900/asd | jq .
```

Devuelve el contrato de segmentos (ver `run_talknet.py` y
`doc/07-asd-active-speaker.md` en el repo de la app).

## Notas / primer arranque (verificar)

- La primera imagen tarda (baja PyTorch+CUDA y clona TalkNet). ~varios GB.
- `demoTalkNet.py` normaliza el vídeo a **25 fps** y, al final, renderiza un vídeo
  de visualización que no usamos → si va lento en vídeos largos, se puede parchear
  para saltarse ese paso (los pickles `tracks/scores` ya están antes).
- Si `gdown` del modelo falla en el build, se intenta en el primer `/asd`.
- TalkNet es un repo con años; si hay incompatibilidad de versiones (numpy/torch),
  fija versiones en el Dockerfile. Es el punto más probable de retoque inicial.

## Conexión desde la app

La app (backend en Debian) usa la variable de entorno `ASD_WORKER_URL`
(p.ej. `http://192.168.1.46:8900`). Si está vacía o el worker no responde, el
render cae a encuadre manual (centro/izq/der) sin fallar.
