#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sube un reel (Avatar Reel) a YouTube en el canal elegido. Job: genera SEO desde
el guion y sube el MP4 con YouTubeService. Guarda la URL en la generación.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402
from app.services.clip_seo import generate_clip_seo, strip_wrapping_quotes  # noqa: E402
from app.services.youtube_service import YouTubeService  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Sube un reel a YouTube con SEO")
    ap.add_argument("--reel", required=True)
    ap.add_argument("--channel", required=True, type=int)
    ap.add_argument("--privacy", default="public", choices=["private", "unlisted", "public"])
    args = ap.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")

    reel = db.get_reel(args.reel)
    if not reel:
        raise SystemExit(f"Reel no encontrado: {args.reel}")
    video = root / (reel.get("video") or "")
    if not reel.get("video") or not video.exists():
        raise SystemExit("El reel no tiene vídeo compuesto todavía.")
    channel = db.get_channel(args.channel)
    if not channel:
        raise SystemExit("Canal no encontrado.")

    # SEO desde el guion (reutiliza el motor de clips con un 'clip' mínimo).
    print("Generando SEO (título, descripción, tags)...", flush=True)
    fake_clip = {"transcript": reel.get("script") or reel.get("title") or "",
                 "title": reel.get("title") or "", "channelId": args.channel,
                 "videoPath": reel.get("video")}
    seo = generate_clip_seo(fake_clip, channel, root)
    # Respeta el título/descripción que el usuario ya generó/editó en la interfaz.
    title = strip_wrapping_quotes(reel.get("title") or seo["title"])
    description = (reel.get("seoDescription") or "").strip() or seo["description"]
    print(f"Título: {title}", flush=True)

    print(f"Subiendo a YouTube (canal {channel['name']})...", flush=True)
    service = YouTubeService(channel["id"], root / "youtube_creds")
    response = service.upload_video(video, {
        "title": title, "description": description, "tags": seo["tags"],
        "privacy_status": args.privacy,
    })
    url = f"https://www.youtube.com/watch?v={response['id']}"
    db.update_reel(args.reel, {"youtube_url": url, "channel_id": args.channel, "title": reel.get("title") or title})
    print(f"YOUTUBE_URL: {url}", flush=True)
    print("Subida completada.", flush=True)


if __name__ == "__main__":
    main()
