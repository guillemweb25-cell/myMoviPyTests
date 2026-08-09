#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Ejecuta el pipeline de TalkNet-ASD sobre un vídeo y devuelve un JSON de
segmentos "quién habla cuándo" (contrato con la app de clipping).

Reutiliza el `demoTalkNet.py` original del repo (pipeline ya probado:
scene_detect → S3FD → track_shot → crop_video → evaluate_network) que deja en
`{folder}/{name}/pywork/{tracks,scores}.pckl`. Aquí solo convertimos esos
resultados en segmentos por hablante.

Salida (contrato):
{
  "fps": 25.0,
  "duration_sec": float,
  "frame_size": [W, H],
  "speakers": [ {"id": 0, "center_norm": [cx, cy], "half_size_norm": s}, ... ],
  "segments": [ {"start": 0.0, "end": 3.2, "speaker": 0}, ... ]   # speaker -1 = nadie claro
}
"""
from __future__ import annotations

import glob
import pickle
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

TALKNET_DIR = Path(__file__).resolve().parent  # se copia dentro del repo TalkNet
FPS = 25.0                # demoTalkNet normaliza el vídeo a 25 fps
SPEAKER_GAP_NORM = 0.14   # centros de cara más juntos que esto = mismo hablante
MIN_DWELL_SEC = 0.6       # segmentos más cortos se fusionan con el vecino


def _run_demo(name: str, folder: str) -> None:
    cmd = [sys.executable, "demoTalkNet.py", "--videoName", name, "--videoFolder", folder]
    subprocess.run(cmd, cwd=str(TALKNET_DIR), check=True)


def _load_pickles(folder: str, name: str):
    work = Path(folder) / name / "pywork"
    tracks = pickle.load(open(work / "tracks.pckl", "rb"))
    scores = pickle.load(open(work / "scores.pckl", "rb"))
    return tracks, scores


def _frame_size(folder: str, name: str) -> tuple[int, int]:
    frame = sorted(glob.glob(str(Path(folder) / name / "pyframes" / "*.jpg")))
    if frame:
        img = cv2.imread(frame[0])
        if img is not None:
            return img.shape[1], img.shape[0]
    cap = cv2.VideoCapture(str(Path(folder) / name / "pyavi" / "video.avi"))
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
    cap.release()
    return w, h


def _cluster_speakers(track_cx: list[float], width: int) -> list[int]:
    """Agrupa tracks en hablantes por su x medio (cámara fija → 2 cajas estables).
    Devuelve, por track, el id de hablante (ordenados de izquierda a derecha)."""
    order = sorted(range(len(track_cx)), key=lambda i: track_cx[i])
    groups: list[list[int]] = []
    for i in order:
        if groups and (track_cx[i] - track_cx[groups[-1][-1]]) <= SPEAKER_GAP_NORM * width:
            groups[-1].append(i)
        else:
            groups.append([i])
    speaker_of = [0] * len(track_cx)
    for spk, grp in enumerate(groups):
        for i in grp:
            speaker_of[i] = spk
    return speaker_of


def run_asd(name: str, folder: str) -> dict:
    _run_demo(name, folder)
    tracks, scores = _load_pickles(folder, name)
    width, height = _frame_size(folder, name)

    # Centro (x,y) y tamaño de cada track a partir de proc_track suavizado.
    track_cx, track_cy, track_s, track_frames = [], [], [], []
    for t in tracks:
        pt = t["proc_track"]
        track_cx.append(float(np.median(pt["x"])))
        track_cy.append(float(np.median(pt["y"])))
        track_s.append(float(np.median(pt["s"])))
        track_frames.append(np.asarray(t["track"]["frame"]))

    speaker_of = _cluster_speakers(track_cx, width)
    n_speakers = (max(speaker_of) + 1) if speaker_of else 0

    speakers = []
    for spk in range(n_speakers):
        idxs = [i for i, s in enumerate(speaker_of) if s == spk]
        cx = float(np.median([track_cx[i] for i in idxs]))
        cy = float(np.median([track_cy[i] for i in idxs]))
        sz = float(np.median([track_s[i] for i in idxs]))
        speakers.append({
            "id": spk,
            "center_norm": [round(cx / width, 4), round(cy / height, 4)],
            "half_size_norm": round(sz / width, 4),
        })

    total_frames = 0
    for fr in track_frames:
        if len(fr):
            total_frames = max(total_frames, int(fr.max()) + 1)

    # Score por hablante y frame (máximo entre sus tracks; media temporal ±2 como el demo).
    NEG = -1e9
    spk_score = np.full((n_speakers, total_frames), NEG, dtype=np.float32)
    for i, sc in enumerate(scores):
        sc = np.asarray(sc, dtype=np.float32)
        frames = track_frames[i]
        spk = speaker_of[i]
        for local, f in enumerate(frames):
            lo, hi = max(local - 2, 0), min(local + 3, len(sc))
            avg = float(np.mean(sc[lo:hi])) if hi > lo else float(sc[local])
            if avg > spk_score[spk, f]:
                spk_score[spk, f] = avg

    # Hablante activo por frame: argmax si supera 0, si no -1 (nadie claro).
    active = np.full(total_frames, -1, dtype=int)
    for f in range(total_frames):
        col = spk_score[:, f]
        best = int(np.argmax(col)) if n_speakers else -1
        if n_speakers and col[best] >= 0:
            active[f] = best

    # Rellena huecos (-1) manteniendo el hablante anterior, para no saltar en silencios.
    last = -1
    for f in range(total_frames):
        if active[f] == -1:
            active[f] = last
        else:
            last = active[f]

    # Frames a segmentos + fusión de los demasiado cortos.
    segments = []
    if total_frames:
        start = 0
        for f in range(1, total_frames):
            if active[f] != active[f - 1]:
                segments.append([start, f, int(active[start])])
                start = f
        segments.append([start, total_frames, int(active[start])])

    min_frames = int(MIN_DWELL_SEC * FPS)
    merged = []
    for seg in segments:
        if merged and (seg[1] - seg[0]) < min_frames:
            merged[-1][1] = seg[1]  # absorbe el corto en el anterior
        else:
            merged.append(list(seg))

    out_segments = [
        {"start": round(s / FPS, 2), "end": round(e / FPS, 2), "speaker": spk}
        for s, e, spk in merged
    ]

    return {
        "fps": FPS,
        "duration_sec": round(total_frames / FPS, 2),
        "frame_size": [width, height],
        "speakers": speakers,
        "segments": out_segments,
    }
