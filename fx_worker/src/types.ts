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

/**
 * Campos del contrato que todavía NO renderiza nadie (fases 13C/13E).
 *
 * Se declaran para que el payload del backend valide sin cambios cuando lleguen,
 * pero el servidor RECHAZA la petición si vienen con contenido: callarlos sería
 * perder texto obligatorio de campaña o un endcard, y eso es un clip no conforme.
 * Ver "Compliance" en el documento.
 */
export const notYetImplementedSchema = z.object({
  emphasis: z.array(z.unknown()).optional(),
  hook: z.unknown().optional(),
  endcard: z.unknown().optional(),
  progress_bar: z.enum(["top", "split_line", "off"]).optional(),
  sfx: z.boolean().optional(),
  music: z.unknown().optional(),
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
};
