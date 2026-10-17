import React from "react";
import { Audio, Sequence, useVideoConfig } from "remotion";
import type { Emphasis, Word } from "./types.ts";

type Props = {
  words: Word[];
  emphasis: Emphasis[];
  zoomTimes: number[];
  whooshUrl: string | null;
  popUrl: string | null;
  musicUrl: string | null;
  musicVolume: number;
  duck: boolean;
};

/**
 * Nivel de mezcla de los efectos. Los ficheros estan normalizados a -3 dBFS, asi
 * que esto es lo unico que hay que tocar para subirlos o bajarlos.
 *
 * Historia de este numero, para no volver a pasarla:
 *   - Con los ficheros sin normalizar el whoosh picaba a -17,9 dB y bajo la voz
 *     (que pica a -10) no se oia nada.
 *   - Subirlo a 0.55 lo dejo a -3,7 dB en el clip real: se oia, pero agresivo.
 *   - 0.30 lo deja ~6 dB POR DEBAJO de la voz: acompana al zoom sin pelearse
 *     con la frase, que es lo que tiene que hacer una transicion.
 */
const SFX_VOLUME = 0.3;

/** Cuanto baja la musica mientras hay voz. */
const DUCK_FACTOR = 0.28;
/** Margen antes y despues de cada palabra, para que no bombee. */
const DUCK_PAD = 0.25;

/**
 * Audio del clip aparte del original: un whoosh por cada punch zoom, un pop por
 * cada emoji, y la musica de fondo bajando bajo la voz.
 */
export const SoundLayer: React.FC<Props> = ({
  words, emphasis, zoomTimes, whooshUrl, popUrl, musicUrl, musicVolume, duck,
}) => {
  const { fps } = useVideoConfig();

  const popTimes = emphasis
    .filter((e) => e.effect === "emoji")
    .map((e) => words[e.word_index]?.start)
    .filter((t): t is number => typeof t === "number");

  // Tramos con voz, ya unidos: asi el volumen de la musica se calcula de un
  // vistazo por frame en vez de recorrer todas las palabras cada vez.
  const speech = React.useMemo(() => {
    const spans: [number, number][] = [];
    for (const w of words) {
      const from = Math.max(0, w.start - DUCK_PAD);
      const to = w.end + DUCK_PAD;
      const last = spans[spans.length - 1];
      if (last && from <= last[1]) last[1] = Math.max(last[1], to);
      else spans.push([from, to]);
    }
    return spans;
  }, [words]);

  const musicAt = (frame: number): number => {
    if (!duck) return musicVolume;
    const t = frame / fps;
    const talking = speech.some(([a, b]) => t >= a && t <= b);
    return musicVolume * (talking ? DUCK_FACTOR : 1);
  };

  return (
    <>
      {musicUrl && (
        <Audio src={musicUrl} volume={musicAt} loop />
      )}
      {whooshUrl && zoomTimes.map((t, i) => (
        <Sequence key={`w${i}`} from={Math.round(t * fps)} durationInFrames={Math.round(0.5 * fps)}>
          <Audio src={whooshUrl} volume={SFX_VOLUME} />
        </Sequence>
      ))}
      {popUrl && popTimes.map((t, i) => (
        <Sequence key={`p${i}`} from={Math.round(t * fps)} durationInFrames={Math.round(0.2 * fps)}>
          <Audio src={popUrl} volume={SFX_VOLUME} />
        </Sequence>
      ))}
    </>
  );
};
