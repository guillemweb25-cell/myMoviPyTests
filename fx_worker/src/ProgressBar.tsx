import React from "react";
import { useCurrentFrame, useVideoConfig } from "remotion";

type Props = {
  mode: "top" | "split_line" | "off";
  /** Fraccion de altura de la linea de corte, para el modo split_line. */
  topRatio: number;
  color: string;
};

/**
 * Barra de progreso. En `top` va pegada arriba; con watermark NO debe usarse
 * (el backend manda `split_line` en ese caso) porque se le monta encima.
 */
export const ProgressBar: React.FC<Props> = ({ mode, topRatio, color }) => {
  const frame = useCurrentFrame();
  const { durationInFrames, height } = useVideoConfig();
  if (mode === "off") return null;

  const progress = Math.min(1, frame / Math.max(1, durationInFrames - 1));
  const thickness = Math.max(4, height * 0.004);

  return (
    <div
      style={{
        position: "absolute",
        left: 0,
        width: `${progress * 100}%`,
        height: thickness,
        top: mode === "top" ? 0 : `${topRatio * 100}%`,
        backgroundColor: color,
      }}
    />
  );
};
