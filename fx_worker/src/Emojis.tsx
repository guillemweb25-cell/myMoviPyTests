import React from "react";
import { spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Emphasis, Word } from "./types.ts";

type Props = { words: Word[]; emphasis: Emphasis[]; centerY: number };

const VISIBLE_SECS = 1.1;

/**
 * Emojis que aparecen de golpe sobre la palabra marcada. Se colocan por encima
 * del bloque de subtitulos (no sobre el): tapar la palabra que se esta leyendo
 * seria peor que no ponerlo.
 */
export const Emojis: React.FC<Props> = ({ words, emphasis, centerY }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const t = frame / fps;

  const active = emphasis
    .filter((e) => e.effect === "emoji" && e.emoji)
    .map((e) => ({ emoji: e.emoji!, start: words[e.word_index]?.start }))
    .filter((e): e is { emoji: string; start: number } =>
      typeof e.start === "number" && t >= e.start && t < e.start + VISIBLE_SECS);

  if (!active.length) return null;

  return (
    <>
      {active.map(({ emoji, start }, i) => {
        const enter = spring({
          frame: frame - start * fps,
          fps,
          config: { damping: 9, mass: 0.5 },
        });
        return (
          <div
            key={`${start}-${i}`}
            style={{
              position: "absolute",
              left: 0,
              right: 0,
              top: `${(centerY - 0.11) * 100}%`,
              textAlign: "center",
              fontSize: width * 0.13,
              transform: `scale(${enter})`,
            }}
          >
            {emoji}
          </div>
        );
      })}
    </>
  );
};
