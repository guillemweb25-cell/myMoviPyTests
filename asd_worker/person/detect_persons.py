#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Detecta + trackea personas en un vídeo con YOLOv8 (ultralytics + ByteTrack).

Devuelve, por persona (track), su "envolvente" (bbox que cubre TODO su recorrido,
para blurear con garantía) y un fotograma representativo (para que el backend recorte
la miniatura del panel). Todo normalizado a [0,1] sobre el tamaño del frame.
"""
from __future__ import annotations

import numpy as np

_MODEL = None


def _model():
    global _MODEL
    if _MODEL is None:
        from ultralytics import YOLO
        _MODEL = YOLO("yolov8s.pt")
    return _MODEL


def detect_persons(video_path: str) -> dict:
    import cv2

    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    W = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1920
    H = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 1080
    cap.release()

    tracks: dict[int, list] = {}
    fi = 0
    # classes=[0] = 'person'. persist=True mantiene los ids entre frames.
    for r in _model().track(source=video_path, classes=[0], persist=True,
                            stream=True, verbose=False, tracker="bytetrack.yaml"):
        boxes = getattr(r, "boxes", None)
        if boxes is not None and boxes.id is not None:
            ids = boxes.id.cpu().numpy().astype(int)
            xyxy = boxes.xyxy.cpu().numpy()
            for tid, box in zip(ids, xyxy):
                x1, y1, x2, y2 = box
                tracks.setdefault(int(tid), []).append((fi, float(x1), float(y1), float(x2), float(y2)))
        fi += 1

    min_frames = max(3, int(fps * 0.5))  # descarta detecciones fugaces (<0.5s)
    persons = []
    for tid, boxes in tracks.items():
        if len(boxes) < min_frames:
            continue
        arr = np.array([[b[1], b[2], b[3], b[4]] for b in boxes], dtype=np.float32)
        ux1, uy1 = float(arr[:, 0].min()), float(arr[:, 1].min())
        ux2, uy2 = float(arr[:, 2].max()), float(arr[:, 3].max())
        # fotograma representativo = donde la persona sale más grande (más clara).
        areas = (arr[:, 2] - arr[:, 0]) * (arr[:, 3] - arr[:, 1])
        j = int(areas.argmax())
        rframe, rb = boxes[j][0], arr[j]
        persons.append({
            "bbox_union_norm": [round(ux1 / W, 4), round(uy1 / H, 4),
                                round((ux2 - ux1) / W, 4), round((uy2 - uy1) / H, 4)],
            "repr_time": round(rframe / fps, 2),
            "repr_bbox_norm": [round(rb[0] / W, 4), round(rb[1] / H, 4),
                               round((rb[2] - rb[0]) / W, 4), round((rb[3] - rb[1]) / H, 4)],
            "frames": len(boxes),
            "_x": ux1,
        })

    persons.sort(key=lambda p: p["_x"])  # de izquierda a derecha
    for i, p in enumerate(persons):
        p["id"] = i
        del p["_x"]

    return {"fps": round(fps, 3), "frame_size": [W, H], "persons": persons}
