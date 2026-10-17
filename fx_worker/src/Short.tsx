import React from "react";
import { AbsoluteFill, Img, OffthreadVideo, continueRender, delayRender, useCurrentFrame, useVideoConfig } from "remotion";
import { Captions } from "./Captions.tsx";
import { Emojis } from "./Emojis.tsx";
import { Hook } from "./Hook.tsx";
import { ProgressBar } from "./ProgressBar.tsx";
import { SoundLayer } from "./SoundLayer.tsx";
import { getPreset, PRESETS } from "./presets/index.ts";
import type { ShortProps } from "./types.ts";
import { zoomAt, zoomTimes } from "./zoom.ts";

/**
 * La fuente llega montada desde backend/assets/fonts y la sirve el propio
 * servidor. Se declara con @font-face y se espera a que Chromium la tenga
 * cargada antes de pintar el primer frame: sin esto los primeros fotogramas
 * saldrían con la tipografía de reserva y el subtítulo "saltaría" de ancho a
 * mitad del clip.
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
  const {
    videoSrc, watermarkSrc, fontUrl, words, overlay, watermark, safe_zones, brand,
    emphasis, hook, progress_bar, sfx, music, layout,
    whooshUrl, popUrl, musicUrl,
  } = props;
  const preset = getPreset(props.preset) ?? PRESETS.minimal!;
  const fontReady = useFontReady(FONT_FAMILY);
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;

  // Manda el preset: con punchZoom 0 (p.ej. "minimal") no hay zooms, y por tanto
  // tampoco whoosh, aunque el backend mande enfasis. Asi el backend puede enviar
  // siempre lo mismo y el estilo lo decide el preset en un solo sitio.
  const zTimes = React.useMemo(
    () => (preset.punchZoom > 0 ? zoomTimes(words, emphasis) : []),
    [words, emphasis, preset.punchZoom],
  );
  const zoom = zoomAt(zTimes, t, preset.punchZoom);

  // En facecam el zoom SOLO puede tocar la cara: la pantalla compartida de abajo
  // tiene que poder leerse, y ampliarla la recorta. Por eso ahí se pintan dos
  // capas recortadas del mismo vídeo y solo se escala la de arriba. En split el
  // encuadre es uno solo y se escala entero.
  const isFacecam = layout.mode === "facecam";
  const split = layout.top_ratio * 100;

  return (
    <AbsoluteFill style={{ backgroundColor: "#000000" }}>
      <style>{`@font-face {
        font-family: "${FONT_FAMILY}";
        src: url("${fontUrl}") format("truetype");
        font-display: block;
      }`}</style>

      {isFacecam ? (
        <>
          <AbsoluteFill style={{ clipPath: `inset(0 0 ${100 - split}% 0)` }}>
            <AbsoluteFill style={{ transform: `scale(${zoom})` }}>
              <OffthreadVideo src={videoSrc} style={{ width: "100%", height: "100%" }} />
            </AbsoluteFill>
          </AbsoluteFill>
          <AbsoluteFill style={{ clipPath: `inset(${split}% 0 0 0)` }}>
            <OffthreadVideo src={videoSrc} muted style={{ width: "100%", height: "100%" }} />
          </AbsoluteFill>
        </>
      ) : (
        <AbsoluteFill style={{ transform: `scale(${zoom})` }}>
          <OffthreadVideo src={videoSrc} style={{ width: "100%", height: "100%" }} />
        </AbsoluteFill>
      )}

      <ProgressBar mode={progress_bar} topRatio={layout.top_ratio} color={brand.primary} />

      {fontReady && hook && (
        <Hook text={hook.text} duration={hook.duration} preset={preset} />
      )}

      {fontReady && (
        <Captions
          words={words}
          preset={preset}
          safeZones={safe_zones}
          overlayCenterY={overlay ? overlay.center_y : null}
        />
      )}

      <Emojis words={words} emphasis={emphasis} centerY={preset.captionCenterY} />

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

      {/* Watermark de campaña: capa fija SIN escalar, la última de todas. Los
          punch zooms escalan solo la capa base: un watermark que se mueve o se
          recorta es un clip no conforme. */}
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

      <SoundLayer
        words={words}
        emphasis={emphasis}
        zoomTimes={zTimes}
        whooshUrl={sfx ? whooshUrl : null}
        popUrl={sfx ? popUrl : null}
        musicUrl={musicUrl}
        musicVolume={music?.volume ?? 0.1}
        duck={music?.duck ?? true}
      />
    </AbsoluteFill>
  );
};
