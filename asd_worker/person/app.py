#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mini-API del worker de personas (YOLOv8): detección + blur.

- POST /persons : sube un clip, devuelve las personas (cajas frame-a-frame + repr).
- POST /blur    : sube un clip + las cajas a difuminar (JSON), devuelve el clip
                  difuminado (sin audio; el render remuxea el audio original).
Contenedor aparte del de TalkNet para no tocar su numpy.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask

from blur_persons import blur_video
from detect_persons import detect_persons

app = FastAPI(title="Person worker (YOLOv8)")
DATA = Path("/data")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/persons")
async def persons(file: UploadFile = File(...)) -> JSONResponse:
    job = uuid.uuid4().hex[:8]
    folder = DATA / job
    folder.mkdir(parents=True, exist_ok=True)
    src = folder / "input.mp4"
    with src.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        result = detect_persons(str(src))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"YOLO falló: {exc}") from exc
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return JSONResponse(result)


@app.post("/blur")
async def blur(file: UploadFile = File(...), boxes: str = Form(...)) -> FileResponse:
    """`boxes` = JSON {"frames": {"<idx>": [[x,y,w,h], ...], ...}} normalizado."""
    job = uuid.uuid4().hex[:8]
    folder = DATA / job
    folder.mkdir(parents=True, exist_ok=True)
    src = folder / "input.mp4"
    out = folder / "blurred.mp4"
    with src.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        frames_boxes = json.loads(boxes).get("frames", {})
        blur_video(str(src), str(out), frames_boxes)
    except Exception as exc:  # noqa: BLE001
        shutil.rmtree(folder, ignore_errors=True)
        raise HTTPException(status_code=500, detail=f"Blur falló: {exc}") from exc
    # borra la carpeta después de enviar el fichero.
    return FileResponse(str(out), media_type="video/mp4", filename="blurred.mp4",
                        background=BackgroundTask(shutil.rmtree, folder, ignore_errors=True))
