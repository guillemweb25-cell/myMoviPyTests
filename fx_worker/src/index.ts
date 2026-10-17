import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import express from "express";
import multer from "multer";
import { randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { presetNames } from "./presets/index.ts";
import { payloadSchema, type ShortProps } from "./types.ts";

const PORT = Number(process.env.PORT ?? 3000);
const JOBS_DIR = process.env.FX_JOBS_DIR ?? "/tmp/fx-jobs";
const FONTS_DIR = process.env.FX_FONTS_DIR ?? "/app/fonts";
const SFX_DIR = process.env.FX_SFX_DIR ?? "/app/assets/sfx";
const MUSIC_DIR = process.env.FX_MUSIC_DIR ?? "/app/music";
/**
 * Pestañas de Chromium en paralelo por render. Remotion abre por defecto una por
 * núcleo (8 aquí) y el navegador se cae a mitad del render ("target closed")
 * porque esta VM no tiene RAM para tanto. Se arranca en 1 y se sube con
 * FX_CONCURRENCY cuando la máquina dé para más.
 */
const CONCURRENCY = Number(process.env.FX_CONCURRENCY ?? 1);
/** Tope de la caché de frames de OffthreadVideo, para que no se coma la RAM. */
const VIDEO_CACHE_BYTES = Number(process.env.FX_VIDEO_CACHE_BYTES ?? 256 * 1024 * 1024);
/**
 * Escala del render. 1 = 1080x1920. Bajarlo (p.ej. 0.67 = 720x1280) es la
 * palanca para máquinas justas: menos píxeles por frame, menos memoria. El
 * vídeo sale a menor resolución, así que es un apaño, no el modo normal.
 */
const SCALE = Number(process.env.FX_SCALE ?? 1);
/** Verbosidad de Remotion. "verbose" imprime el motivo real si Chromium se cae. */
const LOG_LEVEL = (process.env.FX_LOG_LEVEL ?? "info") as "error" | "warn" | "info" | "verbose";

/**
 * Lo unico del contrato que este worker no pinta: el endcard, que sigue
 * montando ffmpeg en el backend sobre el clip ya terminado.
 */
const NOT_IMPLEMENTED = ["endcard"] as const;

const app = express();
const upload = multer({ dest: path.join(JOBS_DIR, "_uploads"), limits: { fileSize: 2 * 1024 * 1024 * 1024 } });

/** Bundle de Remotion: se compila una vez al arrancar y se reutiliza. */
let serveUrl: string | null = null;
let bundleError: string | null = null;

const ensureBundle = async (): Promise<string> => {
  if (serveUrl) return serveUrl;
  console.log("[fx] compilando el bundle de Remotion...");
  serveUrl = await bundle({
    entryPoint: path.resolve(import.meta.dirname, "entry.ts"),
    onProgress: (p) => {
      if (p % 25 === 0) console.log(`[fx] bundle ${p}%`);
    },
  });
  console.log("[fx] bundle listo");
  return serveUrl;
};

/**
 * Los renders se encadenan de uno en uno. Remotion ya paraleliza frames entre
 * núcleos; dos renders a la vez solo se roban CPU entre ellos y es la vía rápida
 * a que los dos se pasen de timeout.
 */
let queue: Promise<unknown> = Promise.resolve();
const serialize = <T,>(task: () => Promise<T>): Promise<T> => {
  const result = queue.then(task, task);
  queue = result.catch(() => undefined);
  return result;
};

app.get("/health", (_req, res) => {
  res.json({
    ok: bundleError === null,
    presets: presetNames(),
    implemented: ["captions", "overlay", "watermark", "punch_zoom", "emoji",
                  "hook", "progress_bar", "sfx", "music"],
    pending: NOT_IMPLEMENTED,
    bundled: serveUrl !== null,
    error: bundleError,
    tuning: { concurrency: CONCURRENCY, scale: SCALE, videoCacheBytes: VIDEO_CACHE_BYTES },
  });
});

/**
 * CORS abierto en lo que sirve el worker. La composición se carga desde el
 * servidor del bundle de Remotion (otro puerto), así que para Chromium esto es
 * otro origen: sin esta cabecera las FUENTES se bloquean por CORS aunque el
 * fichero devuelva 200. Solo escucha en la red interna de compose.
 */
const allowCors: express.RequestHandler = (_req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  next();
};

/** La tipografía montada, para que Chromium la pida por HTTP desde la composición. */
app.use("/assets/fonts", allowCors, express.static(FONTS_DIR, { fallthrough: false }));
/** Los ficheros del job en curso (vídeo base y watermark) para OffthreadVideo/Img. */
app.use("/jobs", allowCors, express.static(JOBS_DIR));
/** Efectos de sonido propios y el banco de musica montado. */
app.use("/assets/sfx", allowCors, express.static(SFX_DIR));
app.use("/assets/music", allowCors, express.static(MUSIC_DIR));

app.post(
  "/render",
  upload.fields([
    { name: "video", maxCount: 1 },
    { name: "watermark", maxCount: 1 },
    { name: "endcard_frame", maxCount: 1 },
  ]),
  async (req, res) => {
    const files = req.files as Record<string, Express.Multer.File[]> | undefined;
    const videoFile = files?.video?.[0];
    const watermarkFile = files?.watermark?.[0];
    const jobId = randomUUID().slice(0, 12);
    const jobDir = path.join(JOBS_DIR, jobId);
    const cleanup = async () => {
      await fs.rm(jobDir, { recursive: true, force: true }).catch(() => undefined);
      for (const f of [videoFile, watermarkFile, files?.endcard_frame?.[0]]) {
        if (f) await fs.rm(f.path, { force: true }).catch(() => undefined);
      }
    };

    try {
      if (!videoFile) return res.status(400).json({ error: "Falta el fichero 'video'." });
      if (typeof req.body?.payload !== "string") {
        return res.status(400).json({ error: "Falta el campo 'payload' (JSON)." });
      }

      const parsed = payloadSchema.safeParse(JSON.parse(req.body.payload));
      if (!parsed.success) {
        return res.status(400).json({ error: "Payload inválido.", detail: parsed.error.issues });
      }
      const payload = parsed.data;

      if (!presetNames().includes(payload.preset)) {
        return res.status(400).json({
          error: `Preset desconocido: ${payload.preset}. Disponibles: ${presetNames().join(", ")}`,
        });
      }

      // Nada de ignorar capas en silencio: si el payload pide algo que aún no se
      // pinta (endcard, hook, música...), se rechaza para que el backend caiga al
      // camino ASS, que sí lo hace. Callarlo daría un clip sin texto obligatorio.
      const asked = NOT_IMPLEMENTED.filter((k) => {
        const v = payload[k];
        return v !== undefined && v !== null && v !== false && v !== "off"
          && !(Array.isArray(v) && v.length === 0);
      });
      if (asked.length > 0) {
        return res.status(422).json({
          error: `Capas aún no implementadas en este worker: ${asked.join(", ")}. Usa el camino ASS para estos clips.`,
          pending: asked,
        });
      }

      // Compliance: si la campaña exige watermark y no llega el PNG, no se genera
      // nada. Es preferible el fallback a ffmpeg que un clip sin marca.
      if (payload.watermark?.required && !watermarkFile) {
        return res.status(422).json({
          error: "El payload exige watermark pero no se recibió el PNG 'watermark'.",
        });
      }

      await fs.mkdir(jobDir, { recursive: true });
      const videoPath = path.join(jobDir, "video.mp4");
      await fs.rename(videoFile.path, videoPath);
      let watermarkUrl: string | null = null;
      if (watermarkFile) {
        await fs.rename(watermarkFile.path, path.join(jobDir, "watermark.png"));
        watermarkUrl = `http://127.0.0.1:${PORT}/jobs/${jobId}/watermark.png`;
      }

      const base = `http://127.0.0.1:${PORT}`;
      // Pista de musica: la pedida, o una al azar del banco montado.
      let musicUrl: string | null = null;
      if (payload.music) {
        let track = payload.music.file;
        if (!track) {
          const bank = await fs.readdir(MUSIC_DIR).catch(() => [] as string[]);
          const tracks = bank.filter((f) => /\.(mp3|m4a|wav|ogg)$/i.test(f));
          track = tracks.length ? tracks[Math.floor(Math.random() * tracks.length)]! : null;
        }
        if (track) musicUrl = `${base}/assets/music/${encodeURIComponent(track)}`;
        else console.warn("[fx] se pidio musica pero el banco esta vacio; el clip ira sin ella.");
      }

      const inputProps: ShortProps = {
        ...payload,
        videoSrc: `${base}/jobs/${jobId}/video.mp4`,
        watermarkSrc: watermarkUrl,
        fontUrl: `${base}/assets/fonts/Anton-Regular.ttf`,
        whooshUrl: `${base}/assets/sfx/whoosh.wav`,
        popUrl: `${base}/assets/sfx/pop.wav`,
        musicUrl,
      };

      const url = await ensureBundle();
      const outPath = path.join(jobDir, "final.mp4");

      let lastStep = -1;
      await serialize(async () => {
        const composition = await selectComposition({ serveUrl: url, id: "Short", inputProps });
        const capas = [
          `palabras=${payload.words.length}`,
          `enfasis=${payload.emphasis.length}`,
          payload.hook ? "hook" : null,
          payload.progress_bar !== "off" ? `barra=${payload.progress_bar}` : null,
          payload.sfx ? "sfx" : null,
          musicUrl ? "musica" : null,
        ].filter(Boolean).join(" ");
        console.log(
          `[fx] render ${jobId}: preset=${payload.preset} ${composition.durationInFrames}f ` +
            `@${composition.fps}fps ${capas}`,
        );
        await renderMedia({
          composition,
          serveUrl: url,
          codec: "h264",
          outputLocation: outPath,
          inputProps,
          concurrency: CONCURRENCY,
          offthreadVideoCacheSizeInBytes: VIDEO_CACHE_BYTES,
          scale: SCALE,
          logLevel: LOG_LEVEL,
          onBrowserLog: ({ text, type }) => console.log(`[chromium:${type}] ${text}`),
          // Render por software: en un contenedor sin GPU, dejar que Chromium
          // elija backend de GL es otra vía a que se caiga.
          chromiumOptions: { gl: "swangle" },
          onProgress: ({ progress }) => {
            // Solo cuando el tramo CAMBIA: con `pct % 20` se repetía la misma
            // linea decenas de veces mientras el progreso seguia dentro del
            // mismo 20%, y el log del job quedaba ilegible.
            const step = Math.floor(progress * 5) * 20;
            if (step > lastStep) {
              lastStep = step;
              console.log(`[fx] ${jobId} ${step}%`);
            }
          },
        });
      });

      console.log(`[fx] render ${jobId} OK`);
      res.sendFile(outPath, async (err) => {
        if (err) console.error(`[fx] error enviando ${jobId}:`, err);
        await cleanup();
      });
    } catch (err) {
      console.error("[fx] render falló:", err);
      await cleanup();
      if (!res.headersSent) {
        res.status(500).json({ error: err instanceof Error ? err.message : String(err) });
      }
    }
  },
);

await fs.mkdir(JOBS_DIR, { recursive: true });
app.listen(PORT, () => console.log(`[fx] worker escuchando en :${PORT}`));

// El bundle tarda; se compila al arrancar para que el primer clip no pague la espera.
ensureBundle().catch((err) => {
  bundleError = err instanceof Error ? err.message : String(err);
  console.error("[fx] no se pudo compilar el bundle:", err);
});
