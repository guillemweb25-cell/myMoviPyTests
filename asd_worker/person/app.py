#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mini-API del worker de detección de personas (YOLOv8).

Corre en el Windows (misma GPU que el worker de ASD, contenedor aparte para no
tocar el numpy pineado de TalkNet). La app de clipping le sube el clip y recibe las
personas detectadas (envolvente para blur + fotograma para la miniatura del panel).
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

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
