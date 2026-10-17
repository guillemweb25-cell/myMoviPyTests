import { z } from "zod";

/**
 * Contrato de POST /render (ver doc/08-fx-worker-motion-graphics.md).
 *
 * Tiempos en SEGUNDOS. AssemblyAI los da en milisegundos: la conversión la hace
 * el backend al construir el payload, no el worker.
 */

export const wordSchema = z.object({
  text: z.string(),
  start: z.number().min(0),
  end: z.number().min(0),
});

export const layoutSchema = z.object({
  /** split = recorte arriba + escena completa abajo; facecam = webcam arriba; full = reels. */
  mode: z.enum(["split", "facecam", "full"]).default("split"),
  top_ratio: z.number().min(0).max(1).default(0.5),
});

export const safeZoneSchema = z.object({
  name: z.string(),
  y0: z.number().min(0).max(1),
  y1: z.number().min(0).max(1),
});

export const watermarkSchema = z.object({
  required: z.boolean().default(true),
  width_frac: z.number().min(0).max(1).default(0.42),
  top_frac: z.number().min(0).max(1).default(0.03),
});

export const overlaySchema = z.object({
  text: z.string(),
  center_y: z.number().min(0).max(1).default(0.63),
});

export const brandSchema = z.object({
  font: z.string().default("Anton"),
  primary: z.string().default("#FFD400"),
  stroke: z.string().default("#000000"),
});

export const emphasisSchema = z.object({
  /** Indice dentro de `words`. Fuera de rango = se ignora ese enfasis. */
  word_index: z.number().int().min(0),
  effect: z.enum(["punch_zoom", "emoji"]),
  emoji: z.string().optional(),
});

export const hookSchema = z.object({
  text: z.string(),
  duration: z.number().min(0.5).max(6).default(2),
});

export const musicSchema = z.object({
  /** null = una aleatoria del banco montado en /app/music. */
  file: z.string().nullable().default(null),
  volume: z.number().min(0).max(1).default(0.1),
  /** Baja la musica mientras hay voz. */
  duck: z.boolean().default(true),
});

/**
 * El endcard sigue montandolo ffmpeg en el backend, sobre el clip ya terminado.
 * Se declara para que el payload valide, pero el servidor RECHAZA la peticion si
 * viene: callarlo daria un clip sin el cierre obligatorio de la campana.
 * Ver "Compliance" en el documento.
 */
export const notYetImplementedSchema = z.object({
  endcard: z.unknown().optional(),
});

export const payloadSchema = notYetImplementedSchema.extend({
  fps: z.number().positive().default(30),
  duration: z.number().positive(),
  preset: z.string().default("minimal"),
  layout: layoutSchema.default({ mode: "split", top_ratio: 0.5 }),
  words: z.array(wordSchema).default([]),
  overlay: overlaySchema.optional(),
  watermark: watermarkSchema.optional(),
  safe_zones: z.array(safeZoneSchema).default([]),
  brand: brandSchema.default({ font: "Anton", primary: "#FFD400", stroke: "#000000" }),
  emphasis: z.array(emphasisSchema).default([]),
  hook: hookSchema.optional(),
  progress_bar: z.enum(["top", "split_line", "off"]).default("off"),
  sfx: z.boolean().default(false),
  music: musicSchema.optional(),
});

export type Payload = z.infer<typeof payloadSchema>;
export type Word = z.infer<typeof wordSchema>;
export type SafeZone = z.infer<typeof safeZoneSchema>;

/**
 * Lo que Short.tsx recibe como inputProps: el payload más las URLs que sirve el
 * propio worker. Son absolutas a propósito: dentro de la composición, una ruta
 * relativa la resuelve Chromium contra el servidor del bundle de Remotion (otro
 * puerto), no contra este servidor, y da 404.
 */
export type ShortProps = Payload & {
  videoSrc: string;
  watermarkSrc: string | null;
  fontUrl: string;
  /** URLs servidas por el worker; null = esa capa no suena. */
  whooshUrl: string | null;
  popUrl: string | null;
  musicUrl: string | null;
};

export type Emphasis = z.infer<typeof emphasisSchema>;
