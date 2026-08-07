#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Sube un clip renderizado a YouTube generando SEO con las reglas del canal.

Se ejecuta como job. Lee el clip y su canal de la BD, genera titulo/descripcion/
tags con SEOEngine y sube el MP4 con YouTubeService. Guarda la URL en la BD.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from app import db  # noqa: E402
from app.services.seo_engine import SEOEngine  # noqa: E402
from app.services.youtube_service import YouTubeService  # noqa: E402

LANG_HINT = {"es": "es (Spanish)", "en": "en (English)"}


def main() -> None:
    parser = argparse.ArgumentParser(description="Sube un clip a YouTube con SEO")
    parser.add_argument("--clip", required=True)
    parser.add_argument("--privacy", default="private", choices=["private", "unlisted", "public"])
    args = parser.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")

    clip = db.get_clip(args.clip)
    if not clip:
        raise SystemExit(f"Clip no encontrado: {args.clip}")
    if not clip.get("channelId"):
        raise SystemExit("El clip no tiene canal asociado.")

    channel = db.get_channel(clip["channelId"])
    if not channel:
        raise SystemExit("Canal no encontrado.")

    rendered = clip.get("renderedPath") or ""
    rendered_path = root / rendered
    if not rendered or not rendered_path.exists():
        raise SystemExit("El clip no esta renderizado todavia.")

    lang = LANG_HINT.get(channel["language"], None)
    rules = channel.get("seoRules") or None
    snippet = clip.get("transcript") or clip.get("title") or ""

    print("Generando SEO (titulo, descripcion, tags)...", flush=True)
    engine = SEOEngine()
    title = engine.generate_video_title(snippet, lang=lang, custom_rules=rules)
    description = engine.generate_description(snippet, lang=lang, custom_rules=rules)
    tags = engine.generate_video_questions_tags(snippet, lang=lang, custom_rules=rules)
    print(f"Titulo: {title}", flush=True)

    print("Subiendo a YouTube...", flush=True)
    service = YouTubeService(channel["id"], root / "youtube_creds")
    response = service.upload_video(
        rendered_path,
        {
            "title": title,
            "description": description,
            "tags": tags,
            "privacy_status": args.privacy,
        },
    )
    video_id = response["id"]
    url = f"https://www.youtube.com/watch?v={video_id}"
    db.update_clip(args.clip, {"youtube_url": url})
    print(f"YOUTUBE_URL: {url}", flush=True)
    print("Subida completada.", flush=True)


if __name__ == "__main__":
    main()
