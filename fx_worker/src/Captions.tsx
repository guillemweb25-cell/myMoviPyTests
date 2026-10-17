import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";
import type { Preset } from "./presets/index.ts";
import { groupWords, phraseAt } from "./phrases.ts";
import type { SafeZone, Word } from "./types.ts";

type Props = {
  words: Word[];
  preset: Preset;
  safeZones: SafeZone[];
  /** Fracción de altura ya ocupada por el caption fijo del brief, si lo hay. */
  overlayCenterY: number | null;
};

/**
 * Devuelve el centro vertical del bloque de subtítulos: el del preset, salvo que
 * caiga sobre una zona protegida (watermark, caption de campaña, UI de Shorts),
 * en cuyo caso se sube hasta el primer hueco libre por encima.
 *
 * Nunca baja: hacia abajo está la UI de YouTube Shorts.
 */
const resolveCenterY = (
  preferred: number,
  blockHeightFrac: number,
  safeZones: SafeZone[],
  overlayCenterY: number | null,
): number => {
  const zones = safeZones.map((z) => ({ y0: z.y0, y1: z.y1 }));
  if (overlayCenterY !== null) {
    // El caption del brief no lo tapa nadie: se reserva su franja con margen.
    zones.push({ y0: overlayCenterY - 0.05, y1: overlayCenterY + 0.05 });
  }

  const collides = (center: number) => {
    const top = center - blockHeightFrac / 2;
    const bottom = center + blockHeightFrac / 2;
    return zones.some((z) => bottom > z.y0 && top < z.y1);
  };

  let center = preferred;
  // Pasos de 1% hacia arriba; el tope es 0.18 para no invadir la zona del watermark.
  while (center > 0.18 && collides(center)) center -= 0.01;
  return center;
};

export const Captions: React.FC<Props> = ({ words, preset, safeZones, overlayCenterY }) => {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const t = frame / fps;

  const phrases = React.useMemo(
    () => groupWords(words, preset.maxWordsPerPhrase),
    [words, preset.maxWordsPerPhrase],
  );
  const phrase = phraseAt(phrases, t);
  if (!phrase) return null;

  const fontSize = width * preset.fontSizeFrac;
  const strokeWidth = width * preset.strokeWidthFrac;
  // Dos líneas como máximo con el tope de palabras actual; 1.25 de interlineado.
  const blockHeightFrac = (fontSize * 1.25 * 2) / height;
  const centerY = resolveCenterY(
    preset.captionCenterY,
    blockHeightFrac,
    safeZones,
    overlayCenterY,
  );

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: `${centerY * 100}%`,
        transform: "translateY(-50%)",
        display: "flex",
        flexWrap: "wrap",
        justifyContent: "center",
        alignItems: "center",
        gap: `${fontSize * 0.22}px`,
        padding: `0 ${width * 0.07}px`,
        fontFamily: preset.fontFamily,
        fontSize,
        lineHeight: 1.25,
        textTransform: preset.uppercase ? "uppercase" : "none",
        // Borde por sombras en 8 direcciones: se ve igual en Chromium headless que
        // en el navegador, al contrario que -webkit-text-stroke con fuentes gruesas.
        textShadow: [
          `${strokeWidth}px 0 0 ${preset.strokeColor}`,
          `-${strokeWidth}px 0 0 ${preset.strokeColor}`,
          `0 ${strokeWidth}px 0 ${preset.strokeColor}`,
          `0 -${strokeWidth}px 0 ${preset.strokeColor}`,
          `${strokeWidth}px ${strokeWidth}px 0 ${preset.strokeColor}`,
          `-${strokeWidth}px ${strokeWidth}px 0 ${preset.strokeColor}`,
          `${strokeWidth}px -${strokeWidth}px 0 ${preset.strokeColor}`,
          `-${strokeWidth}px -${strokeWidth}px 0 ${preset.strokeColor}`,
        ].join(", "),
      }}
    >
      {phrase.words.map((word, i) => {
        const active = t >= word.start && t < word.end;
        return (
          <span
            key={`${word.start}-${i}`}
            style={{
              color: active ? preset.activeColor : preset.color,
              display: "inline-block",
              transform: active ? `scale(${preset.activeScale})` : "scale(1)",
              transformOrigin: "center bottom",
            }}
          >
            {word.text}
          </span>
        );
      })}
    </div>
  );
};
