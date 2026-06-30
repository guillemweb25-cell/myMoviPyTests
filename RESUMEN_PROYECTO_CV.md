# Resumen del proyecto para CV

## Proyecto

**Media Ops / myMoviPyTests** es una aplicacion web full-stack para automatizar flujos multimedia con Python. El proyecto empezo como una coleccion de scripts sueltos para descargar, convertir, transcribir y generar video, y se refactorizo hacia una herramienta operativa con backend, frontend, Docker, historial de ejecuciones, visor de archivos y pipelines reutilizables.

El objetivo principal del proyecto es convertir tareas manuales de edicion y procesamiento multimedia en workflows ejecutables desde una interfaz web: descargar audio o video desde una URL, generar transcripciones y subtitulos, explorar los resultados, lanzar scripts de conversion, extraer frames, detectar frames incrustados y preparar integraciones con ComfyUI para transformacion visual con modelos generativos.

## Stack tecnico

- **Backend:** Python, FastAPI, Pydantic, Uvicorn.
- **Frontend:** React 18, TypeScript, Vite.
- **Multimedia:** yt-dlp, ffmpeg, MoviePy, OpenCV, Pillow.
- **IA / APIs externas:** AssemblyAI para transcripcion automatica; preparacion de workflows ComfyUI con ControlNet/OpenPose.
- **Infraestructura local:** Docker Compose, contenedores separados para backend y frontend.
- **Persistencia local:** sistema de archivos para outputs, logs, uploads, metadata y artefactos generados.

## Funcionalidades construidas

### 1. Refactor de scripts Python a aplicacion web

Se reorganizo el proyecto en una arquitectura clara:

- `backend/`: API FastAPI y servicios Python.
- `backend/scripts/`: scripts multimedia originales, mantenidos como herramientas CLI ejecutables.
- `frontend/`: interfaz React + TypeScript.
- `output/`: resultados generados por descargas, transcripciones, videos, imagenes y uploads.
- `workflows/`: workflows preparados para ComfyUI.

La aplicacion permite ejecutar scripts Python desde el navegador sin tener que recordar comandos manuales.

### 2. Backend FastAPI para orquestar jobs

Se implemento una API que:

- Lista scripts disponibles y los clasifica por categoria.
- Ejecuta scripts Python con argumentos CLI.
- Crea jobs asincronos en segundo plano mediante threads.
- Guarda logs por ejecucion en `backend/runs/`.
- Expone endpoints para consultar estado, historial y logs.
- Valida rutas para evitar acceso fuera del workspace.
- Sirve archivos generados desde el backend con `FileResponse`.

Endpoints principales:

- `GET /api/health`
- `GET /api/scripts`
- `POST /api/jobs`
- `GET /api/jobs`
- `GET /api/jobs/{job_id}/log`
- `GET /api/files`
- `GET /api/file`

### 3. Pipeline URL a contenido

Se creo un pipeline dedicado para convertir una URL de video en contenido util:

- Descarga audio con `yt-dlp`.
- Convierte a MP3 mediante ffmpeg.
- Genera carpeta de salida con nombre normalizado.
- Guarda metadata de origen en `source_url.txt` y `source.json`.
- Transcribe el audio con AssemblyAI.
- Genera texto `.txt`.
- Genera subtitulos `.vtt` o `.srt`.
- Guarda idioma detectado en `.lang` cuando esta disponible.

Este flujo esta separado en servicios reutilizables:

- `VideoDownloadService`
- `AssemblyAiTranscriptionService`
- `VideoContentPipeline`

### 4. Upload local y transcripcion automatica

Se anadio la posibilidad de subir archivos locales desde la interfaz:

- Formatos soportados: `.mp3`, `.mp4`, `.m4a`, `.wav`, `.ogg`, `.oga`, `.opus`.
- Carpeta de destino obligatoria para organizar uploads.
- Conversion automatica de `.ogg`, `.oga` y `.opus` a MP3 antes de transcribir.
- Lanzamiento automatico del job de transcripcion.
- Generacion de `.txt`, subtitulos e idioma detectado.

Esto permite procesar audios propios sin depender de una URL externa.

### 5. Frontend React como panel de operaciones

Se desarrollo una interfaz web tipo dashboard con secciones:

- **Dashboard:** metricas de scripts, jobs completados, fallidos y en ejecucion.
- **Contenido Web:** descarga de MP3 + transcripcion o descarga de video MP4 desde URL.
- **Ejecutar Scripts:** lanzador generico para cualquier script Python con argumentos CLI.
- **Historial:** seguimiento de jobs y logs en tiempo casi real.
- **Explorador Output:** navegacion por resultados generados.

La interfaz permite operar el sistema sin terminal, con seleccion de cookies, idioma, formato de subtitulos y rutas opcionales de ffmpeg.

### 6. Explorador y visor de archivos multimedia

Se implemento un explorador de archivos para `output/` con:

- Navegacion por carpetas.
- Vista embebida de texto, audio, video e imagen.
- Descarga directa de archivos.
- Copia de texto de transcripciones.
- Acciones contextuales segun el tipo de archivo:
  - Generar transcripcion si falta.
  - Descargar video asociado desde `source_url.txt`.
  - Descargar miniatura.
  - Convertir imagen a PNG.
  - Detectar frames incrustados en un video.
  - Ver video, miniatura o transcripcion relacionada.

### 7. Deteccion y tratamiento de contenido multimedia

El proyecto incluye scripts para:

- Descargar MP3, MP4 y miniaturas.
- Convertir formatos: AVI, MKV, WEBM, M4A, WAV, MP3.
- Extraer frames de video.
- Detectar frames incrustados o segmentos insertados.
- Convertir imagenes a PNG.
- Voltear imagenes.
- Crear videos simples y slideshows.
- Generar efectos Ken Burns.
- Crear overlays de video.
- Normalizar outputs.

### 8. Integracion inicial con ComfyUI

Se preparo una primera capa de integracion con ComfyUI:

- Endpoint `GET /api/comfy/status`.
- Cliente Python `ComfyUiClient` configurable por `COMFY_URL`.
- Deteccion de estado online/offline.
- Lectura de cola pendiente y en ejecucion.
- Visualizacion del estado en el dashboard.

Tambien se anadieron workflows API para ComfyUI:

- `sd15_openpose_anime_api.json`
- `sdxl_illustrious_openpose_anime_api.json`
- `sdxl_dwp_pose_from_frame_img2img_api.json`

Estos workflows estan orientados a transformar frames de video usando pose/control de composicion con OpenPose, DWPose, ControlNet y modelos SDXL/Illustrious.

### 9. Dockerizacion

Se preparo `docker-compose.yml` con dos servicios:

- Backend FastAPI en contenedor Python.
- Frontend React/Vite en contenedor Node.

La configuracion monta el workspace como volumen para desarrollo y expone:

- Backend: `localhost:8800`
- Frontend: `localhost:5074`

Esto facilita levantar la aplicacion completa con:

```bash
docker compose up --build
```

## Retos tecnicos resueltos

- Pasar de scripts aislados a una arquitectura web mantenible.
- Ejecutar procesos largos en segundo plano sin bloquear la API.
- Capturar logs incrementales para mostrar feedback al usuario.
- Mantener compatibilidad con scripts CLI existentes.
- Organizar outputs multimedia con metadata de origen.
- Gestionar uploads y conversiones de audio antes de transcribir.
- Validar rutas del filesystem para reducir riesgos al servir archivos.
- Integrar herramientas externas como yt-dlp, ffmpeg, AssemblyAI y ComfyUI.
- Disenar una interfaz capaz de operar pipelines reales, no solo lanzar comandos.

## Impacto del proyecto

El proyecto transforma un conjunto de automatizaciones personales en una plataforma local de media operations. Reduce trabajo manual repetitivo, centraliza procesos multimedia y permite operar flujos complejos desde una interfaz web. Es especialmente util para creacion de contenido, analisis de videos, transcripcion automatica, preparacion de subtitulos y experimentacion con generacion visual basada en frames.

## Posibles bullets para CV

- Refactorice una coleccion de scripts multimedia en una aplicacion full-stack con FastAPI, React, TypeScript y Docker.
- Desarrolle un sistema de jobs asincronos para ejecutar scripts Python desde una interfaz web, con historial, estados y logs persistentes.
- Implemente pipelines automatizados para descargar audio/video con yt-dlp, convertir con ffmpeg y generar transcripciones/subtitulos con AssemblyAI.
- Construí un explorador multimedia con previsualizacion de texto, audio, video e imagen, ademas de acciones contextuales para procesar archivos generados.
- Integre soporte para uploads locales, conversion automatica de formatos de audio y transcripcion con deteccion de idioma.
- Prepare workflows ComfyUI con ControlNet/OpenPose para transformar frames de video mediante modelos generativos.
- Dockerice backend y frontend para facilitar el desarrollo local reproducible.

## Version breve para LinkedIn

Desarrolle una herramienta full-stack de automatizacion multimedia con FastAPI, React, TypeScript y Docker. La aplicacion permite descargar audio/video, transcribir contenido con AssemblyAI, generar subtitulos, explorar outputs, ejecutar scripts Python como jobs asincronos y preparar workflows de IA generativa con ComfyUI y ControlNet/OpenPose. El proyecto convierte tareas manuales de procesamiento multimedia en pipelines operables desde una interfaz web local.

## Version orientada a entrevista tecnica

Este proyecto demuestra capacidad para convertir scripts experimentales en una aplicacion mantenible. La parte mas relevante fue disenar una capa de orquestacion en FastAPI capaz de ejecutar scripts CLI existentes como jobs asincronos, capturar logs, exponerlos por API y conectarlos con una interfaz React. Tambien se trabajo la gestion de archivos generados, uploads, validacion de rutas, conversion multimedia con ffmpeg, descarga con yt-dlp, transcripcion con AssemblyAI y una primera integracion con ComfyUI para workflows generativos basados en frames y pose.

## Prompt sugerido para Claude

Puedes subir este archivo a Claude y pedirle:

```text
Quiero convertir este resumen de proyecto en una descripcion profesional para mi CV.
Hazme:
1. Una version corta de 2-3 lineas.
2. Una version detallada para seccion de proyectos.
3. 5 bullets orientados a impacto tecnico.
4. Una version en ingles.
Mantén un tono profesional, claro y creible para perfil de desarrollador full-stack / Python automation.
```
