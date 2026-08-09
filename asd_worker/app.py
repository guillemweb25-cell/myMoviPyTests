#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mini-API del worker de ASD (active speaker detection).

Corre en el Windows (WSL2 + Docker con --gpus all), junto a TalkNet-ASD.
La app de clipping le sube el vídeo fuente y recibe los segmentos de
"quién habla cuándo" (ver run_talknet.run_asd).
"""
from __future__ import annotations

import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse

from run_talknet import run_asd

app = FastAPI(title="ASD worker (TalkNet)")
DATA = Path("/data")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/asd")
async def asd(file: UploadFile = File(...)) -> JSONResponse:
    job = uuid.uuid4().hex[:8]
    folder = DATA / job
    folder.mkdir(parents=True, exist_ok=True)
    name = "input"
    src = folder / f"{name}.mp4"
    with src.open("wb") as f:
        shutil.copyfileobj(file.file, f)
    try:
        result = run_asd(name, str(folder))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"TalkNet falló: {exc}") from exc
    finally:
        shutil.rmtree(folder, ignore_errors=True)
    return JSONResponse(result)
