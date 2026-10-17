import type { Emphasis, Word } from "./types.ts";

/** Instantes (en segundos) en los que dispara un punch zoom. */
export const zoomTimes = (words: Word[], emphasis: Emphasis[]): number[] =>
  emphasis
    .filter((e) => e.effect === "punch_zoom")
    .map((e) => words[e.word_index]?.start)
    .filter((t): t is number => typeof t === "number")
    .sort((a, b) => a - b);

const IN_SECS = 0.25;   // entrada rapida: es el golpe
const OUT_SECS = 0.4;   // salida mas lenta, para que no de tiron

/**
 * Escala del vídeo base en el instante `t`. 1 = sin zoom.
 *
 * Entra rapido y sale despacio. Si dos enfasis caen muy juntos gana el mas
 * fuerte en ese instante, en vez de sumarse: encadenar zooms multiplicandolos
 * dispararia la escala y recortaria la imagen.
 */
export const zoomAt = (times: number[], t: number, amount: number): number => {
  let best = 0;
  for (const start of times) {
    const dt = t - start;
    if (dt < 0 || dt > IN_SECS + OUT_SECS) continue;
    const k = dt < IN_SECS
      ? dt / IN_SECS                               // 0 -> 1
      : 1 - (dt - IN_SECS) / OUT_SECS;             // 1 -> 0
    // easeOutCubic en la entrada y easeInOut en la vuelta: el golpe se nota,
    // el regreso no.
    const eased = dt < IN_SECS ? 1 - Math.pow(1 - k, 3) : k * k * (3 - 2 * k);
    best = Math.max(best, eased);
  }
  return 1 + best * amount;
};
