#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Renderiza EN COLA (uno tras otro) todos los clips pendientes de una
transcripcion. Corre como un unico job en el backend, asi que sobrevive a
recargas de la pagina o cambios de pestana del navegador.

Reutiliza render_clip.py por clip (mismo pipeline que el render individual).
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Renderiza en cola todos los clips pendientes de una transcripcion")
    parser.add_argument("--transcript", required=True)
    parser.add_argument("--focus", default=None, choices=["left", "center", "right", "follow"],
                        help="Encuadre global a aplicar a todos antes de renderizar")
    args = parser.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")

    clips = db.load_clips(args.transcript)
    pending = [c for c in clips if not (c.get("renderedPath") and (root / c["renderedPath"]).exists())]
    print(f"Clips pendientes de renderizar: {len(pending)} de {len(clips)}", flush=True)

    render_clip = str(Path(__file__).with_name("render_clip.py"))
    done = 0
    for i, clip in enumerate(pending, 1):
        cid = clip["id"]
        # Aplica el encuadre global.
        if args.focus and clip.get("focus") != args.focus:
            db.update_clip(cid, {"focus": args.focus})
            clip["focus"] = args.focus

        video_rel = clip.get("videoPath") or ""
        if not video_rel:
            print(f"[{i}/{len(pending)}] {cid}: sin video, saltado", flush=True)
            continue

        out_rel = str(Path(video_rel).parent / "clips" / f"clip_{cid}.mp4")
        channel = db.get_channel(clip["channelId"]) if clip.get("channelId") else None
        lang = (channel or {}).get("language", "es") or "es"

        cmd = [
            sys.executable, render_clip,
            "--video", video_rel,
            "--start", f"{clip['start']:.3f}",
            "--end", f"{clip['end']:.3f}",
            "--out", out_rel,
            "--top-ratio", f"{clip['topRatio']:.2f}",
            "--focus", clip["focus"],
            "--zoom", f"{clip['zoom']:.2f}",
            "--lang", lang,
        ]
        if clip["subtitles"]:
            cmd.append("--subtitles")
        if clip.get("overlayText"):
            cmd += ["--overlay", clip["overlayText"]]
        if clip.get("endcardPercent"):
            cmd += ["--endcard", str(clip["endcardPercent"])]

        title = (clip.get("title") or "")[:50]
        print(f"\n[{i}/{len(pending)}] Renderizando {cid} — {title}", flush=True)
        db.update_clip(cid, {"rendered_path": out_rel})
        rc = subprocess.run(cmd, cwd=str(root)).returncode
        if rc == 0:
            done += 1
            print(f"[{i}/{len(pending)}] OK {cid}", flush=True)
        else:
            print(f"[{i}/{len(pending)}] FALLO {cid} (rc={rc})", flush=True)

    print(f"\nHecho: {done}/{len(pending)} verticales renderizados.", flush=True)


if __name__ == "__main__":
    main()
