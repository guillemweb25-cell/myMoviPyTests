#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""JOB: cola de vídeos de macetas. Genera una lista de plantas EN CADENA (una tras
otra, no en paralelo) llamando a plant_video.py por cada id. Si una falla, sigue
con la siguiente. Pensado para tandas (p. ej. de noche).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

PLANT_VIDEO = Path(__file__).with_name("plant_video.py")


def main() -> None:
    ap = argparse.ArgumentParser(description="Cola de vídeos de macetas (secuencial)")
    ap.add_argument("--plants", required=True, help="ids separados por comas")
    ap.add_argument("--provider", default="grok", choices=["grok", "veo", "wan"])
    ap.add_argument("--duration", type=int, default=15)
    ap.add_argument("--length", type=int, default=97)
    ap.add_argument("--music", default="")
    args = ap.parse_args()

    ids = [p.strip() for p in args.plants.split(",") if p.strip()]
    root = Path.cwd()
    print(f"Cola de {len(ids)} vídeos ({args.provider}). Empezando...", flush=True)
    ok, fail = 0, 0
    for i, pid in enumerate(ids, 1):
        print(f"\n===== [{i}/{len(ids)}] planta {pid} =====", flush=True)
        cmd = [sys.executable, str(PLANT_VIDEO), "--plant", pid,
               "--provider", args.provider, "--duration", str(args.duration), "--length", str(args.length)]
        if args.music:
            cmd += ["--music", args.music]
        rc = subprocess.run(cmd, cwd=str(root)).returncode
        if rc == 0:
            ok += 1
            print(f"[{i}/{len(ids)}] ✅ {pid} listo", flush=True)
        else:
            fail += 1
            print(f"[{i}/{len(ids)}] ❌ {pid} falló (rc={rc}); sigo con la siguiente", flush=True)
    print(f"\n✅ Cola terminada: {ok} ok, {fail} fallidas de {len(ids)}.", flush=True)


if __name__ == "__main__":
    main()
