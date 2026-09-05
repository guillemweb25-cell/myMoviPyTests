Videos Automáticos — Visión general del proyecto (para reutilizar en otros proyectos)
Documento de referencia para que otro proyecto/agente pueda aprovechar lo ya construido aquí. Explica qué hace el sistema, cómo está montado, dónde está el código y qué piezas son reutilizables.

0. Dónde está el código (acceso)
Dato	Valor
Ruta del código (host Windows)	D:\videos_automaticos
IP LAN de la máquina	192.168.1.46
Repositorio Git	github.com:guillemweb25-cell/videos_automaticos (rama main)
Dominio público de la app	https://ytauto.enguillem.es
SO	Windows 11. La app corre en Docker Desktop; ComfyUI y el TTS corren nativos en el host.
Cómo leer el código desde otro proyecto:

Si el otro proyecto está en la misma máquina: leer directamente D:\videos_automaticos\....
Si está en otra máquina de la LAN: por SSH (ver abajo), clonar el repo Git, o acceso por red a \\192.168.1.46\... (si hay recurso compartido).
Backend montado en el contenedor en /app (equivale a D:\videos_automaticos\backend).
Acceso SSH (sin contraseña):

Se puede entrar por SSH a 192.168.1.46 con el usuario guillem sin contraseña (autenticación por clave pública ya configurada).
Ejemplo: ssh guillem@192.168.1.46 y luego navegar a /d/videos_automaticos (o D:\videos_automaticos en rutas Windows).
Desde ahí se puede leer todo el código, ejecutar comandos, y acceder a los servicios locales (API 8500, ComfyUI 8188, TTS 8022, etc.).
1. Qué es el proyecto
Fábrica autoalojada de vídeo con IA para canales de YouTube "faceless" (sin cara) + un estudio de personajes/vídeo con IA. Genera guiones, voz, imágenes y vídeos automáticamente, los renderiza y sube. Todo local (GPU propia), sin depender de servicios de pago para imagen/vídeo.

Dos grandes bloques:

Pipeline de vídeo automático por canal (el núcleo original): guion → voz (TTS) → imágenes (ComfyUI) → render → SEO → subida a YouTube. ~10 canales temáticos.
Estudio LTX / Personajes (lo más nuevo y reutilizable): generación de vídeo LTX 2.5, personajes consistentes (IPAdapter + ControlNet OpenPose) e image-to-video.
Repost: descargar vídeos de YouTube con yt-dlp para resubir a otras plataformas (Bilibili).
2. Stack y arquitectura
Backend: Python + FastAPI (uvicorn --reload). Auth JWT. LLM vía OpenAI (gpt-4o-mini) / Grok.
Frontend: React + TypeScript + Vite (build estático servido con vite preview).
BD: MariaDB 11 (SQLAlchemy + Alembic).
Orquestación: Docker Compose (servicios: db, api, frontend).
IA de imagen/vídeo: ComfyUI (nativo en el host, no en Docker) vía su API HTTP (/prompt, /history, /view, /upload/image, /object_info).
TTS: XTTSv2 (Coqui) local (FastAPI aparte), + ElevenLabs y TikTok como alternativas.
Servicios y puertos
Servicio	Puerto host	Dónde	Notas
API (FastAPI)	8500 → 8000	contenedor videos_automaticos-api-1	monta D:\videos_automaticos\backend en /app
Frontend	8501 → 5173	contenedor videos_automaticos-frontend-1	Vite build + preview
MariaDB	3307 → 3306	contenedor videos_automaticos-db-1	BD videos_automaticos
ComfyUI	8188	host D:\AI\ComfyUI	COMFY_URL=http://192.168.1.46:8188
TTS XTTS local	8022	host C:\Users\guillem\local_tts_api	LOCAL_TTS_URL=http://192.168.1.46:8022
Volúmenes montados en el contenedor api: backend→/app, cache→/app/cache, overlay→/app/overlay, workflows→/app/workflows. Importante: el output/input de ComfyUI NO está montado en el contenedor → se accede por HTTP (/view, /upload/image).

3. Infra de IA (ComfyUI en el host)
Ruta: D:\AI\ComfyUI (git + venv; se lanza con start.bat, que activa el venv).
Versión: ComfyUI 0.34 (torch 2.10/cu126). GPU: RTX 4060 Ti 16 GB (+ 1050 Ti 4GB sin usar).
Punto de restauración pre-actualización: D:\AI\comfyui_backup_pre_ltx\snapshot_before_ltx.json (restaurar con cm-cli.py restore-snapshot).
Custom nodes clave: ComfyUI-GGUF, ComfyUI-LTXVideo (Kijai), comfyui_AcademiaSD, WhatDreamsCost-ComfyUI, ComfyUI_IPAdapter_plus, comfyui_controlnet_aux, ComfyUI-KJNodes, rgthree-comfy, ComfyUI-VideoHelperSuite.
Modelos instalados (en D:\AI\ComfyUI\models)
Checkpoints SDXL: RealVisXL_V5.0_fp16 (realista), novaAnimeXL_xlV10 (anime), disneyrealcartoonmix, juggernautXL, etc.
LTX 2.5: LTX-2.5-Distilled-Q3_K_M.gguf (unet, en diffusion_models), gemma4-12b-with-proj-ltx-2.5-comfy-int8-convrot (text encoder, en text_encoders), ltx-2.5-video-vae-bf16 + ltx-2.5-audio-vae-bf16 (vae), ltx-2.5-latent-spatial-upscaler-x2 (latent_upscale_models).
IPAdapter: ip-adapter-plus-face_sdxl_vit-h (cara), ip-adapter-plus_sdxl_vit-h + CLIP-Vision ViT-H-14.
ControlNet OpenPose SDXL: controlnet-openpose-sdxl-xinsir.safetensors (2,3 GB, fuerte) + t2i-adapter-openpose-sdxl-1.0 (ligero).
4. Módulos REUTILIZABLES (con sus endpoints)
Todos los endpoints requieren JWT (Authorization: Bearer <token>), salvo los marcados. Base URL API: http://192.168.1.46:8500.

4.1 Generación de imágenes con ComfyUI (backend/app/services/comfy_service.py, image_engine.py)
Patrón headless reutilizable: cargar un workflow JSON en formato API (workflows/*.json), inyectar prompt/negativo/seed/resolución/LoRAs vía ComfyService.prepare_workflow(), enviarlo a ComfyUI /prompt, sondear /history y recuperar la imagen por /view.

Normaliza rutas de checkpoint /→\ (Windows) — ver comfy_service.py.
Sistema de estilos por canal (style_service.py) y LoRAs (lora_service.py, tabla loras).
4.2 Vídeo LTX 2.5 — texto→vídeo e imagen→vídeo (backend/app/routers/video_ltx.py)
Grafos LTX 2.5 headless (ingenierizados a mano, plantillas en workflows/LTX25-*.json).

POST /ltx/generate — texto→vídeo vertical. Auto-traduce el prompt ES→EN (gemma solo entiende inglés). Plantilla LTX25-T2V-Vertical.json.
POST /ltx/i2v — imagen→vídeo (anima una imagen manteniendo apariencia). Nodo clave LTXVImgToVideoInplace. Plantilla LTX25-I2V-Vertical.json.
GET /ltx/status/{prompt_id} — estado (running/done/error + fichero).
GET /ltx/video?filename= — sirve el MP4 (proxy de ComfyUI /view).
POST /ltx/save, GET /ltx/history, DELETE /ltx/history/{id} — historial persistente (cache/ltx_history/user_<id>.json).
Grafo mínimo LTX 2.5 (clave): UnetLoaderGGUF + CLIPLoader(type=ltxv) + latente AV (EmptyLTXVLatentVideo+LTXVEmptyLatentAudio→LTXVConcatAVLatent) + SamplerCustomAdvanced (euler + ManualSigmas del distilled, cfg 1) + LTXVSpatioTemporalTiledVAEDecode + VHS_VideoCombine.
4.3 Generador de personajes consistentes (backend/app/routers/characters.py)
Genera un personaje coherente (misma cara) con SDXL + IPAdapter-face, en varias poses controladas con ControlNet OpenPose.

POST /characters/generate — crea personaje: base + poses. Opciones: style (anime/realista/cartoon), gender (hombre/mujer), neutral_bg (fondo blanco para dataset LoRA), pose_control (usar ControlNet).
POST /characters/scene — genera imágenes nuevas del personaje en cualquier escena/pose (antepone su descripción al prompt para mantener identidad + IPAdapter 0.85). Opcional pose (de la librería).
POST /characters/{id}/regenerate-poses — rehace el "character sheet" (frontal, 3/4, perfil, brazos cruzados, caminando, saludando + retrato). Param gender. Poll de fondo que actualiza el personaje al terminar.
POST /characters/{id}/update-images, GET /characters/list, GET /characters/status/{pid}, GET /characters/poses?gender=, GET /characters/image?filename=, DELETE /characters/{id}.
Librería de poses OpenPose por género: backend/pose_library/{hombre,mujer}/*.png (esqueletos extraídos con DWPreprocessor). Nodos: ControlNetLoader + ControlNetApplyAdvanced, IPAdapterUnifiedLoader (PLUS FACE = cara).
Almacén de personajes: cache/characters/user_<id>.json.
Patrón reutilizable: subir una imagen de referencia del output de ComfyUI a su input (/upload/image) para usarla con LoadImage (IPAdapter/ControlNet/I2V).
4.4 Repost / descarga de YouTube (backend/app/routers/repost.py, services/youtube_dl.py)
Descargar vídeos de YouTube (yt-dlp) para resubir a mano a otras plataformas.

GET /repost/{channel_id}/info?url= — metadatos sin descargar (título, descripción, miniatura).
GET /repost/{channel_id}/thumbnail?url= — proxy de miniatura, convertida a PNG con Pillow.
POST /repost/{channel_id}/download — descarga MP4 (mejor calidad). Usa player_client=android para evitar 403.
GET /repost/{channel_id}/downloads, GET /repost/{channel_id}/file?rel=.
scan_channel() en youtube_dl.py: lista todos los vídeos públicos de un canal por su handle (sin OAuth).
4.5 Pipeline de vídeo automático (canales) (backend/app/routers/video_gen.py)
El flujo completo original: generar guion (LLM) → audio (audio_engine.py) → imágenes (auto-encadenado tras el audio) → render (rendering_engine.py, moviepy/ffmpeg) → subtítulos (subtitle_engine.py) → SEO (seo_engine.py, título/desc/tags) → subida YouTube (youtube_api.py, OAuth) → aviso Telegram (telegram_service.py).

4.6 Audio / TTS (backend/app/services/audio_engine.py)
XTTSv2 local (LOCAL_TTS_URL): clonación de voz por seeds, detección de idioma, troceado inteligente + crossfade. Servidor aparte en C:\Users\guillem\local_tts_api\app.py (ojo: es una copia, editar a mano).
También ElevenLabs y TikTok TTS.
4.7 Canales (backend/app/routers/channels.py, models/channel.py)
Config por canal en BD + cache/ (no en git): image_style_prompt, negative_prompt, default_style, default_workflow, loras, guía de estilos (cache/.../style-guide.md). Export/import portable con backend/scripts/manage_channels.py.

5. Estructura de ficheros clave
D:\videos_automaticos\
├─ backend/
│  ├─ app/
│  │  ├─ main.py                 # incluye todos los routers
│  │  ├─ routers/                # auth, channels, video_gen, video_ltx, characters, repost, youtube, loras, settings, payments, admin
│  │  ├─ services/               # comfy_service, image_engine, audio_engine, rendering_engine, seo_engine, youtube_dl, style_service, lora_service, telegram_service, ...
│  │  └─ models/                 # SQLAlchemy (channel, user, video, lora, ...)
│  ├─ pose_library/{hombre,mujer}/*.png   # esqueletos OpenPose (ControlNet)
│  └─ requirements.txt
├─ frontend/src/
│  ├─ App.tsx                    # layout + navegación (sidebar)
│  ├─ api.ts                     # cliente API (fetch + JWT)
│  └─ components/                # ChannelDashboard, VideoCreator, LtxStudio (Vídeo/Personajes/Imágenes), CharacterGenerator, CharacterImages, RepostManager, LoraManager, ...
├─ workflows/*.json              # workflows ComfyUI en formato API (imagen + LTX vídeo)
├─ cache/                        # datos NO versionados (guías de estilo, historial LTX, personajes)
└─ docker-compose.yml
(La carpeta docs/ tiene documentación adicional más detallada del pipeline original.)

6. Piezas más valiosas para reutilizar
Integración ComfyUI headless (enviar workflow API + sondeo + recuperar output por HTTP) — patrón en comfy_service.py y video_ltx.py/characters.py. Sirve para cualquier proyecto que quiera generar imagen/vídeo con ComfyUI sin la UI.
Grafos LTX 2.5 ya funcionando (T2V e I2V) en workflows/LTX25-*.json — difíciles de montar desde cero.
Generador de personajes consistentes (IPAdapter-face + ControlNet OpenPose por género + librería de esqueletos) — characters.py + pose_library/.
Descarga YouTube robusta (youtube_dl.py, fix 403 con player_client=android).
Auto-traducción de prompts ES→EN para modelos que solo entienden inglés (video_ltx._to_english_prompt).
Pipeline completo guion→voz→imagen→render→SEO→subida para vídeo automatizado.
7. Notas / gotchas
ComfyUI en Windows lista los checkpoints con backslash (SDXL\modelo.safetensors); normalizar /→\.
El output de ComfyUI no está montado en el contenedor → todo por HTTP (/view, /upload/image).
Cambios de frontend requieren rebuild (reiniciar el contenedor frontend). Cambios de backend los recoge uvicorn --reload.
cache/ está en .gitignore (datos, no código). Los secretos van en .env (no versionado).
El texto en pantalla (UI de software, texto de personaje) hay que permitirlo quitando text del negativo cuando aplique.
Generado el 2026-09-05. Estado del repo: rama main, último commit sobre el estudio de personajes/LTX.