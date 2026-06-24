# Descargas para ComfyUI Pose ControlNet

Guia de descargas para los workflows de esta carpeta.

Define primero la ruta de tu ComfyUI:

```bash
export COMFY_HOME="/ruta/a/ComfyUI"
```

Si Civitai te pide login, crea una API key en tu cuenta y exportala asi:

```bash
export CIVITAI_TOKEN="pega_aqui_tu_api_key"
```

Los comandos funcionan sin token en modelos publicos. Si un enlace devuelve HTML,
403 o una pagina de login, usa la version con `?token=${CIVITAI_TOKEN}`.

## Minimo recomendado para anime desde videos

### 1. Illustrious XL v0.1

Checkpoint anime/illustration base para SDXL.

- Pagina: https://civitai.com/models/795765/illustrious-xl?modelVersionId=889818
- Destino: `ComfyUI/models/checkpoints/illustriousXL_v01.safetensors`
- Usado por:
  - `sdxl_illustrious_openpose_anime_api.json`
  - `sdxl_dwp_pose_from_frame_img2img_api.json`

```bash
mkdir -p "${COMFY_HOME}/models/checkpoints"
curl -L \
  -o "${COMFY_HOME}/models/checkpoints/illustriousXL_v01.safetensors" \
  "https://civitai.com/api/download/models/889818"
```

Con token:

```bash
mkdir -p "${COMFY_HOME}/models/checkpoints"
curl -L \
  -o "${COMFY_HOME}/models/checkpoints/illustriousXL_v01.safetensors" \
  "https://civitai.com/api/download/models/889818?token=${CIVITAI_TOKEN}"
```

### 2. Illustrious XL ControlNet OpenPose

ControlNet de pose compatible con Illustrious XL.

- Pagina: https://civitai.com/models/1359846/illustrious-xl-controlnet-openpose?modelVersionId=1536174
- Destino: `ComfyUI/models/controlnet/IllustriousXL_openpose.safetensors`
- Usado por:
  - `sdxl_illustrious_openpose_anime_api.json`
  - `sdxl_dwp_pose_from_frame_img2img_api.json`

```bash
mkdir -p "${COMFY_HOME}/models/controlnet"
curl -L \
  -o "${COMFY_HOME}/models/controlnet/IllustriousXL_openpose.safetensors" \
  "https://civitai.com/api/download/models/1536174"
```

Con token:

```bash
mkdir -p "${COMFY_HOME}/models/controlnet"
curl -L \
  -o "${COMFY_HOME}/models/controlnet/IllustriousXL_openpose.safetensors" \
  "https://civitai.com/api/download/models/1536174?token=${CIVITAI_TOKEN}"
```

## Opcional: SD 1.5 ligero

### 3. ControlNet OpenPose SD 1.5

ControlNet OpenPose clasico para checkpoints SD 1.5.

- Pagina: https://civitai.com/models/9557/difference-controlnets?modelVersionId=11342
- Destino: `ComfyUI/models/controlnet/control_sd15_openpose.safetensors`
- Usado por:
  - `sd15_openpose_anime_api.json`

```bash
mkdir -p "${COMFY_HOME}/models/controlnet"
curl -L \
  -o "${COMFY_HOME}/models/controlnet/control_sd15_openpose.safetensors" \
  "https://civitai.com/api/download/models/11342"
```

Con token:

```bash
mkdir -p "${COMFY_HOME}/models/controlnet"
curl -L \
  -o "${COMFY_HOME}/models/controlnet/control_sd15_openpose.safetensors" \
  "https://civitai.com/api/download/models/11342?token=${CIVITAI_TOKEN}"
```

### 4. Checkpoint SD 1.5 anime

El workflow SD 1.5 espera este nombre:

- Destino esperado: `ComfyUI/models/checkpoints/anything-v5.safetensors`

Puedes usar cualquier checkpoint anime SD 1.5 que prefieras. Si descargas otro
nombre, renombralo a `anything-v5.safetensors` o cambia el valor `ckpt_name` en
`sd15_openpose_anime_api.json`.

## Opcional: otro checkpoint anime SDXL

### 5. Animagine XL 4.0

Alternativa SDXL anime. No esta conectado por defecto a los workflows, pero
puedes cambiar `ckpt_name` de `illustriousXL_v01.safetensors` a
`animagineXL40.safetensors`.

- Pagina: https://civitai.com/models/1188071/animagine-xl-40?modelVersionId=1337429
- Destino: `ComfyUI/models/checkpoints/animagineXL40.safetensors`

```bash
mkdir -p "${COMFY_HOME}/models/checkpoints"
curl -L \
  -o "${COMFY_HOME}/models/checkpoints/animagineXL40.safetensors" \
  "https://civitai.com/api/download/models/1337429"
```

Con token:

```bash
mkdir -p "${COMFY_HOME}/models/checkpoints"
curl -L \
  -o "${COMFY_HOME}/models/checkpoints/animagineXL40.safetensors" \
  "https://civitai.com/api/download/models/1337429?token=${CIVITAI_TOKEN}"
```

## Opcional: video/motion mas adelante

### 6. AnimateDiff Motion Module SD 1.5 v2

Solo hace falta si luego usamos AnimateDiff en lugar de procesar frame a frame.

- Pagina: https://civitai.com/models/108836/animatediff-motion-modules?modelVersionId=159987
- Destino habitual: `ComfyUI/models/animatediff_models/mm_sd_v15_v2.ckpt`

```bash
mkdir -p "${COMFY_HOME}/models/animatediff_models"
curl -L \
  -o "${COMFY_HOME}/models/animatediff_models/mm_sd_v15_v2.ckpt" \
  "https://civitai.com/api/download/models/159987"
```

Con token:

```bash
mkdir -p "${COMFY_HOME}/models/animatediff_models"
curl -L \
  -o "${COMFY_HOME}/models/animatediff_models/mm_sd_v15_v2.ckpt" \
  "https://civitai.com/api/download/models/159987?token=${CIVITAI_TOKEN}"
```

## Nodos que se instalan desde ComfyUI Manager

Estos no van en `models/`; instalalos desde ComfyUI Manager:

- `ComfyUI's ControlNet Auxiliary Preprocessors`
- `ComfyUI-VideoHelperSuite`
- `ComfyUI-AnimateDiff-Evolved`

Para `sdxl_dwp_pose_from_frame_img2img_api.json`, el importante es
`ComfyUI's ControlNet Auxiliary Preprocessors`, porque aporta `DWPreprocessor`.

## Comprobacion rapida

```bash
ls -lh "${COMFY_HOME}/models/checkpoints/illustriousXL_v01.safetensors"
ls -lh "${COMFY_HOME}/models/controlnet/IllustriousXL_openpose.safetensors"
```

Reinicia ComfyUI despues de descargar modelos o instalar nodos.
