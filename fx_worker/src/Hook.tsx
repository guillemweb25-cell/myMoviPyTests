import React from "react";
import { interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import type { Preset } from "./presets/index.ts";

type Props = { text: string; duration: number; preset: Preset };

/**
 * Titulo gancho de los primeros segundos. Entra con un muelle y sale con un
 * fundido corto. Va en el tercio superior pero por debajo de la zona del
 * watermark, que nunca se toca.
 */
export const Hook: React.FC<Props> = ({ text, duration, preset }) => {
  const frame = useCurrentFrame();
  const { fps, width } = useVideoConfig();
  const endFrame = duration * fps;
  if (frame > endFrame) return null;

  const enter = spring({ frame, fps, config: { damping: 12, mass: 0.6 } });
  // Se va en los ultimos 0,35 s, para que no corte en seco.
  const fade = interpolate(frame, [endFrame - 0.35 * fps, endFrame], [1, 0], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const fontSize = width * 0.072;
  const stroke = width * 0.004;

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        right: 0,
        top: "20%",
        padding: `0 ${width * 0.08}px`,
        textAlign: "center",
        fontFamily: preset.fontFamily,
        fontSize,
        lineHeight: 1.1,
        textTransform: "uppercase",
        color: "#FFFFFF",
        opacity: fade,
        transform: `scale(${0.8 + enter * 0.2})`,
        textShadow: [
          `${stroke}px 0 0 #000`, `-${stroke}px 0 0 #000`,
          `0 ${stroke}px 0 #000`, `0 -${stroke}px 0 #000`,
          `${stroke}px ${stroke}px 0 #000`, `-${stroke}px ${stroke}px 0 #000`,
          `${stroke}px -${stroke}px 0 #000`, `-${stroke}px -${stroke}px 0 #000`,
        ].join(", "),
      }}
    >
      {text}
    </div>
  );
};
