#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detecta + trackea personas (YOLOv8 + ByteTrack) y devuelve, POR PERSONA, sus
cajas FRAME A FRAME (para blurear siguiendo el movimiento, aguantando cortes de
cámara). Fusiona fragmentos del mismo individuo por histograma de color (misma ropa)
de forma CONSERVADORA (mejor no fusionar que fusionar de más: si dudamos, salen dos
thumbnails y el usuario marca ambos; fusionar mal podría dejar sin blurear a alguien).

Salida:
{
  "fps": 25.0, "frame_size": [W,H],
  "persons": [
    { "id": 0, "repr_time": 3.2, "repr_bbox_norm": [x,y,w,h],
      "frames": 512,
      "boxes": [[frame_idx, x,y,w,h], ...]   # normalizado, por frame
    }, ...
  ]
}
"""
from __future__ import annotations

import numpy as np

_MODEL = None
MERGE_THRESHOLD = 0.72  # correlación de histograma para fusionar (alto = conservador)


def _model():
    global _MODEL
    if _MODEL is None:
        from ultralytics import YOLO
        _MODEL = YOLO("yolov8s.pt")
    return _MODEL


def _hist(crop):
    import cv2
    if crop is None or crop.size == 0:
        return None
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    h = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
    cv2.normalize(h, h)
    return h.flatten().astype(np.float32)


def detect_persons(video_path: str) -> dict:
    import cv2

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080

    # 1) YOLO track -> por track, lista de (frame, x1,y1,x2,y2)
    tracks: dict[int, list] = {}
    fi = 0
    for r in _model().track(source=video_path, classes=[0], persist=True,
                            stream=True, verbose=False, tracker="bytetrack.yaml"):
        boxes = getattr(r, "boxes", None)
        if boxes is not None and boxes.id is not None:
            ids = boxes.id.cpu().numpy().astype(int)
            xyxy = boxes.xyxy.cpu().numpy()
            for tid, box in zip(ids, xyxy):
                tracks.setdefault(int(tid), []).append(
                    (fi, float(box[0]), float(box[1]), float(box[2]), float(box[3])))
        fi += 1

    min_frames = max(3, int(fps * 0.4))
    tracks = {t: b for t, b in tracks.items() if len(b) >= min_frames}

    # 2) por track: fotograma representativo (área máxima) + histograma de color
    reprs = {}
    for tid, b in tracks.items():
        arr = np.array([[x[1], x[2], x[3], x[4]] for x in b], dtype=np.float32)
        areas = (arr[:, 2] - arr[:, 0]) * (arr[:, 3] - arr[:, 1])
        j = int(areas.argmax())
        f = b[j][0]
        cap.set(cv2.CAP_PROP_POS_FRAMES, f)
        ok, frame = cap.read()
        hist = None
        if ok:
            x1, y1, x2, y2 = [int(v) for v in arr[j]]
            hist = _hist(frame[max(0, y1):y2, max(0, x1):x2])
        reprs[tid] = {"frame": f, "bbox": arr[j], "hist": hist}
    cap.release()

    # 3) fusiona tracks -> personas por similitud de histograma (conservador)
    tids = sorted(tracks.keys(), key=lambda t: -len(tracks[t]))  # los más largos primero
    persons_tracks: list[list[int]] = []
    person_hist: list = []
    for tid in tids:
        h = reprs[tid]["hist"]
        placed = False
        if h is not None:
            for k, ph in enumerate(person_hist):
                if ph is not None and cv2.compareHist(h, ph, cv2.HISTCMP_CORREL) >= MERGE_THRESHOLD:
                    persons_tracks[k].append(tid)
                    placed = True
                    break
        if not placed:
            persons_tracks.append([tid])
            person_hist.append(h)

    # 4) construye personas: cajas frame-a-frame (de todos sus tracks) + repr
    out = []
    for grp in persons_tracks:
        boxes = []
        for tid in grp:
            for (f, x1, y1, x2, y2) in tracks[tid]:
                boxes.append([f, round(x1 / W, 4), round(y1 / H, 4),
                              round((x2 - x1) / W, 4), round((y2 - y1) / H, 4)])
        boxes.sort(key=lambda z: z[0])
        # repr = el del track más grande del grupo
        best = max(grp, key=lambda t: len(tracks[t]))
        rb = reprs[best]["bbox"]
        out.append({
            "repr_time": round(reprs[best]["frame"] / fps, 2),
            "repr_bbox_norm": [round(rb[0] / W, 4), round(rb[1] / H, 4),
                               round((rb[2] - rb[0]) / W, 4), round((rb[3] - rb[1]) / H, 4)],
            "frames": len(boxes),
            "boxes": boxes,
            "_x": rb[0],
        })

    out.sort(key=lambda p: p["_x"])  # izquierda -> derecha
    for i, p in enumerate(out):
        p["id"] = i
        del p["_x"]

    return {"fps": round(fps, 3), "frame_size": [W, H], "persons": out}
