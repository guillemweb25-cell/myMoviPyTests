import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, continueRender, delayRender } from "remotion";
import { Captions } from "./Captions.tsx";
import { getPreset, PRESETS } from "./presets/index.ts";
import type { ShortProps } from "./types.ts";

/**
 * La fuente llega montada desde backend/assets/fonts y la sirve el propio
 * servidor en /assets/fonts. Se declara con @font-face y se espera a que
 * Chromium la tenga cargada antes de pintar el primer frame: sin esto los
 * primeros fotogramas saldrían con la tipografía de reserva y el subtítulo
 * "saltaría" de ancho a mitad del clip.
 */
const FONT_FAMILY = "Anton";

const useFontReady = (family: string) => {
  const [ready, setReady] = React.useState(false);
  React.useEffect(() => {
    const handle = delayRender(`Cargando la tipografía ${family}`);
    document.fonts
      .load(`1em ${family}`)
      .catch((err: unknown) => {
        // Si la fuente no carga seguimos con la de reserva: un subtítulo con otra
        // tipografía es mejor que un render abortado. El aviso queda en el log.
        console.warn("[fx] no se pudo cargar la tipografía:", err);
      })
      .finally(() => {
        setReady(true);
        continueRender(handle);
      });
  }, [family]);
  return ready;
};

export const Short: React.FC<ShortProps> = (props) => {
  const { videoSrc, watermarkSrc, fontUrl, words, overlay, watermark, safe_zones, brand } = props;
  const preset = getPreset(props.preset) ?? PRESETS.minimal!;
  const fontReady = useFontReady(FONT_FAMILY);

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      <style>{`@font-face {
        font-family: "${FONT_FAMILY}";
        src: url("${fontUrl}") format("truetype");
        font-display: block;
      }`}</style>

      {/* Capa base: el vertical ya compuesto por ffmpeg (con blur ya aplicado). */}
      <OffthreadVideo src={videoSrc} style={{ width: "100%", height: "100%" }} />

      {fontReady && (
        <Captions
          words={words}
          preset={preset}
          safeZones={safe_zones}
          overlayCenterY={overlay ? overlay.center_y : null}
        />
      )}

      {/* Caption fijo del brief. Va por encima de los subtítulos: es obligatorio
          y no lo puede tapar ninguna capa. */}
      {overlay && fontReady && (
        <div
          style={{
            position: "absolute",
            left: 0,
            right: 0,
            top: `${overlay.center_y * 100}%`,
            transform: "translateY(-50%)",
            textAlign: "center",
            padding: "0 7%",
            fontFamily: preset.fontFamily,
            fontSize: `${1080 * 0.042}px`,
            color: "#FFFFFF",
            textShadow: `0 0 ${1080 * 0.006}px ${brand.stroke}, 0 ${1080 * 0.003}px 0 ${brand.stroke}`,
          }}
        >
          {overlay.text}
        </div>
      )}

      {/* Watermark de campaña: capa fija SIN escalar, la última de todas. Cuando
          lleguen los punch zooms (13C) solo se escalará la capa base, nunca esta:
          un watermark que se mueve o se recorta es un clip no conforme. */}
      {watermark && watermarkSrc && (
        <Img
          src={watermarkSrc}
          style={{
            position: "absolute",
            top: `${watermark.top_frac * 100}%`,
            left: "50%",
            transform: "translateX(-50%)",
            width: `${watermark.width_frac * 100}%`,
          }}
        />
      )}
    </AbsoluteFill>
  );
};
