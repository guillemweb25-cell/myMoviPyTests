import React from "react";
import { Composition } from "remotion";
import { Short } from "./Short.tsx";
import type { ShortProps } from "./types.ts";

/**
 * Las dimensiones y la duración reales las fija el servidor por cada render
 * (renderMedia + selectComposition con el payload). Lo de aquí son solo los
 * valores por defecto con los que abre `remotion studio`.
 */
const defaultProps: ShortProps = {
  fps: 30,
  duration: 5,
  preset: "minimal",
  layout: { mode: "split", top_ratio: 0.5 },
  words: [],
  safe_zones: [],
  brand: { font: "Anton", primary: "#FFD400", stroke: "#000000" },
  videoSrc: "",
  watermarkSrc: null,
  fontUrl: "/assets/fonts/Anton-Regular.ttf",
  emphasis: [],
  progress_bar: "off",
  sfx: false,
  whooshUrl: null,
  popUrl: null,
  musicUrl: null,
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Short"
    component={Short}
    durationInFrames={150}
    fps={30}
    width={1080}
    height={1920}
    defaultProps={defaultProps}
    calculateMetadata={({ props }) => ({
      fps: props.fps,
      durationInFrames: Math.max(1, Math.round(props.duration * props.fps)),
    })}
  />
);
