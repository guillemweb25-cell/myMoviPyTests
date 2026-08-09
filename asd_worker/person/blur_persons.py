#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Difumina regiones (cajas por frame) de un vídeo. Las cajas van normalizadas a
[0,1]; se agrandan un pelín (padding) para garantizar que no se escape nada — el
requisito de las campañas es binario, así que mejor cubrir de más."""
from __future__ import annotations

PAD = 0.06  # agranda cada caja un 6% por lado


def blur_video(in_path: str, out_path: str, frames_boxes: dict) -> None:
    import cv2

    cap = cv2.VideoCapture(in_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    out = cv2.VideoWriter(out_path, cv2.VideoWriter_fourcc(*"mp4v"), fps, (w, h))

    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        for (bx, by, bw, bh) in frames_boxes.get(str(i), []):
            x1 = int((bx - PAD * bw) * w); y1 = int((by - PAD * bh) * h)
            x2 = int((bx + bw + PAD * bw) * w); y2 = int((by + bh + PAD * bh) * h)
            x1 = max(0, x1); y1 = max(0, y1); x2 = min(w, x2); y2 = min(h, y2)
            if x2 <= x1 or y2 <= y1:
                continue
            roi = frame[y1:y2, x1:x2]
            # pixelado fuerte + gaussiano: censura clara y sin dejar rastro.
            small = cv2.resize(roi, (max(1, (x2 - x1) // 12), max(1, (y2 - y1) // 12)),
                               interpolation=cv2.INTER_LINEAR)
            pix = cv2.resize(small, (x2 - x1, y2 - y1), interpolation=cv2.INTER_NEAREST)
            k = max(15, (min(x2 - x1, y2 - y1) // 3) | 1)
            frame[y1:y2, x1:x2] = cv2.GaussianBlur(pix, (k, k), 0)
        out.write(frame)
        i += 1

    cap.release()
    out.release()
