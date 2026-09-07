#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sube un vídeo de maceta a YouTube en el canal elegido. Job: usa el título y la
descripción SEO (inglés + hashtags) guardados en el registro; si faltan, los genera.
Guarda la URL en el registro.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402
from app.services.plant_engine import seo as plant_seo  # noqa: E402
from app.services.youtube_service import YouTubeService  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Sube un vídeo de maceta a YouTube")
    ap.add_argument("--plant", required=True)
    ap.add_argument("--channel", required=True, type=int)
    ap.add_argument("--privacy", default="public", choices=["private", "unlisted", "public"])
    args = ap.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")
    rec = db.get_plant(args.plant)
    if not rec:
        raise SystemExit(f"Registro {args.plant} no encontrado.")
    video = root / (rec.get("video") or "")
    if not rec.get("video") or not video.exists():
        raise SystemExit("El vídeo de la maceta no está listo todavía.")
    channel = db.get_channel(args.channel)
    if not channel:
        raise SystemExit("Canal no encontrado.")

    title = (rec.get("title") or "").strip()
    description = (rec.get("seoDescription") or "").strip()
    if not title or not description:
        print("Generando SEO en inglés (título + descripción con hashtags)...", flush=True)
        s = plant_seo(rec.get("plant") or "plant", channel.get("seoRules"))
        title = title or s["title"]
        description = description or s["description"]
        db.update_plant(args.plant, {"title": title, "seo_description": description})

    # Hashtags de la descripción como tags de YouTube (sin el #). YouTubeService
    # espera una CADENA separada por comas, no una lista.
    import re
    tags = ",".join(t.lstrip("#") for t in re.findall(r"#\w+", description)[:15])

    print(f"Subiendo a YouTube (canal {channel['name']})...", flush=True)
    service = YouTubeService(channel["id"], root / "youtube_creds")
    response = service.upload_video(video, {
        "title": title, "description": description, "tags": tags,
        "privacy_status": args.privacy,
    })
    url = f"https://www.youtube.com/watch?v={response['id']}"
    db.update_plant(args.plant, {"youtube_url": url, "channel_id": args.channel})
    print(f"YOUTUBE_URL: {url}", flush=True)
    print("Subida completada.", flush=True)


if __name__ == "__main__":
    main()
