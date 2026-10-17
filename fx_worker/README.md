# FX Worker (motion graphics)

Capa de efectos animados para los clips verticales y los reels, con
[Remotion](https://remotion.dev). Diseño completo y fases en
[`doc/08-fx-worker-motion-graphics.md`](../doc/08-fx-worker-motion-graphics.md).

**Opcional.** Si el worker no está levantado (o `FX_WORKER_URL` está vacía), el
backend usa el camino de siempre (ffmpeg + subtítulos ASS).

## Estado: fase 13A

Implementado:

- `GET /health` → presets disponibles y qué capas pinta.
- `POST /render` → vídeo base + palabras → MP4 con **subtítulos por palabra**.
- Caption fijo del brief (`overlay`) y **watermark como capa fija sin escalar**.
- Presets `minimal` y `hormozi`.

Pendiente (fases 13C/13E): `hook`, `emphasis` (punch zooms y emojis), `endcard`,
`progress_bar`, `sfx` y `music`. El worker **rechaza con 422** un payload que
pida cualquiera de ellas, para que el backend caiga al camino ASS en vez de
devolver un clip al que le falta texto obligatorio.

## Desarrollo

```bash
npm install
npm run typecheck        # tsc --noEmit
npm run studio           # editor visual de Remotion
```

## Despliegue

```bash
docker compose build fx_worker && docker compose up -d fx_worker
curl -s localhost:8910/health | jq
```

El primer arranque compila el bundle de Remotion (unos segundos); `/health`
devuelve `bundled: false` hasta que termina.

## Prueba manual

```bash
printf '%s' '{"fps":30,"duration":3,"preset":"hormozi","words":[
  {"text":"Nadie","start":0.0,"end":0.5},
  {"text":"se","start":0.5,"end":0.7},
  {"text":"esperaba","start":0.7,"end":1.4},
  {"text":"esto","start":1.4,"end":2.0}]}' > /tmp/payload.json

curl -s -X POST localhost:8910/render \
  -F "video=@vertical.mp4" \
  -F "payload=<\/tmp/payload.json" \
  -o final.mp4
```

## Rendimiento

~1–3 min por clip de 30 s en CPU. Los renders se encadenan de uno en uno:
Remotion ya reparte los frames entre núcleos y dos a la vez solo se roban CPU.
`FX_CONCURRENCY` fija los núcleos por render (vacío = lo decide Remotion).
