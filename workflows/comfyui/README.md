# ComfyUI Pose ControlNet workflows

Estos JSON son "API prompts" para ComfyUI. Se pueden enviar a `POST /prompt`
cuando `COMFY_URL` apunte a tu servidor.

## Que workflow usar

- `sd15_openpose_anime_api.json`: rapido y ligero. Usa un checkpoint SD 1.5 anime y un ControlNet OpenPose SD 1.5. La imagen de entrada debe ser ya un mapa OpenPose.
- `sdxl_illustrious_openpose_anime_api.json`: mejor calidad anime. Usa Illustrious XL y su ControlNet OpenPose. La imagen de entrada debe ser ya un mapa OpenPose.
- `sdxl_dwp_pose_from_frame_img2img_api.json`: recomendado para tus videos. Entra un frame real, DWPose extrae la pose, y el sampler hace img2img anime respetando pose/composicion.

## Placeholders

Antes de mandar el JSON a ComfyUI, sustituye:

- `__INPUT_IMAGE__`: nombre de imagen que exista en `ComfyUI/input/`.
- `__POSITIVE_PROMPT__`: prompt principal.
- `__NEGATIVE_PROMPT__`: prompt negativo.
- `__SEED__`: entero.
- `__OUTPUT_PREFIX__`: prefijo de salida.

## Modelos esperados

Los nombres dentro de los JSON son intencionadamente explicitos. Si descargas con
otro nombre, o bien renombra el fichero, o cambia el valor del nodo loader.

### SD 1.5

- Checkpoint: `anything-v5.safetensors` o tu checkpoint anime SD 1.5 preferido.
- ControlNet: `control_sd15_openpose.safetensors`.

Rutas:

- `ComfyUI/models/checkpoints/anything-v5.safetensors`
- `ComfyUI/models/controlnet/control_sd15_openpose.safetensors`

### SDXL / Illustrious

- Checkpoint: `illustriousXL_v01.safetensors`.
- ControlNet: `IllustriousXL_openpose.safetensors`.

Rutas:

- `ComfyUI/models/checkpoints/illustriousXL_v01.safetensors`
- `ComfyUI/models/controlnet/IllustriousXL_openpose.safetensors`

## Nodos custom

Instala desde ComfyUI Manager:

- `ComfyUI's ControlNet Auxiliary Preprocessors`
- `ComfyUI-Manager`

Para video completo mas adelante:

- `ComfyUI-VideoHelperSuite`
- `ComfyUI-AnimateDiff-Evolved`

## Flujo recomendado para este proyecto

1. Descarga el video desde la app.
2. Extrae frames con `extract_frames.py` o una version muestreada.
3. Copia/sube los frames a `ComfyUI/input/`.
4. Encola `sdxl_dwp_pose_from_frame_img2img_api.json` para cada frame.
5. Monta los frames generados otra vez en MP4 con ffmpeg o con un script del proyecto.
