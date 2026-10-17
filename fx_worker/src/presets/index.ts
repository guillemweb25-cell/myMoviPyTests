/**
 * Presets de estilo. Un preset decide tipografía, colores, tamaño y cuánta
 * animación lleva el subtítulo. Los efectos pesados (punch zooms, emojis, hook
 * cinético) llegan en la fase 13C y se activarán desde aquí.
 */
export type Preset = {
  name: string;
  /** Familia tipográfica ya registrada en el contenedor (ver fonts.css). */
  fontFamily: string;
  uppercase: boolean;
  /** Tamaño de la palabra como fracción del ancho del lienzo. */
  fontSizeFrac: number;
  color: string;
  /** Color de la palabra que suena en ese instante. */
  activeColor: string;
  strokeColor: string;
  strokeWidthFrac: number;
  /** Cuánto crece la palabra activa (1 = no crece). */
  activeScale: number;
  /** Y del bloque de subtítulos, fracción de la altura (centro del bloque). */
  captionCenterY: number;
  maxWordsPerPhrase: number;
};

export const PRESETS: Record<string, Preset> = {
  minimal: {
    name: "minimal",
    fontFamily: "Anton, sans-serif",
    uppercase: false,
    fontSizeFrac: 0.062,
    color: "#FFFFFF",
    activeColor: "#FFFFFF",
    strokeColor: "#000000",
    strokeWidthFrac: 0.0035,
    activeScale: 1.0,
    captionCenterY: 0.78,
    maxWordsPerPhrase: 4,
  },
  hormozi: {
    name: "hormozi",
    fontFamily: "Anton, sans-serif",
    uppercase: true,
    fontSizeFrac: 0.075,
    color: "#FFFFFF",
    activeColor: "#FFD400",
    strokeColor: "#000000",
    strokeWidthFrac: 0.005,
    activeScale: 1.14,
    captionCenterY: 0.76,
    maxWordsPerPhrase: 3,
  },
};

export const presetNames = (): string[] => Object.keys(PRESETS);

export const getPreset = (name: string): Preset | null => PRESETS[name] ?? null;
