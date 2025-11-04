#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from moviepy import ImageClip, CompositeVideoClip

# --- Configuració ---
IMATGES = ["img/p001_01.png", "img/p001_02.png", "img/p002_01.png"]
DURADA = 3        # segons que dura cada imatge
FADE = 1          # segons de transició
FPS = 24

# --- Helpers ---
def crossfade_pair(img1, img2, durada, fade):
    """Crea un crossfade entre dues imatges."""
    c1 = ImageClip(img1).with_duration(durada)
    c2 = ImageClip(img2).with_duration(durada).with_start(durada - fade)

    # Animar opacitat de la segona imatge (0→1)
    c2 = c2.with_opacity(lambda t: max(0, min(1, t / fade)))

    # Combinar les dues imatges en un sol clip
    comp = CompositeVideoClip([c1, c2]).with_duration(durada + fade)
    return comp

# --- Construcció del vídeo ---
clips = []
for i in range(len(IMATGES) - 1):
    clips.append(crossfade_pair(IMATGES[i], IMATGES[i + 1], DURADA, FADE))

# Concatena tots els crossfades
final = CompositeVideoClip([clips[0]])
for i in range(1, len(clips)):
    final = CompositeVideoClip([final, clips[i].with_start(final.duration - FADE)])

final.write_videofile("output/crossfade_demo.mp4", fps=FPS)
print("✅ Crossfade creat correctament!")
