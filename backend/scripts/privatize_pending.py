#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Privatiza los videos ANTIGUOS pendientes de un canal (p.ej. los de Jesus del
canal renombrado a "The clipper 2026"), SIN tocar los clips de campana.

Doble salvaguarda para no privatizar por error un clip de campana:
  1) se CONSERVAN los video_id que estan en la BD como subidos por la app
     (clips.youtube_url del canal).
  2) se CONSERVAN los publicados a partir del cutoff (por defecto 2026-08-01),
     que es cuando empezaron las campanas.

Solo tocan videos public/unlisted. Por defecto hace DRY-RUN (solo lista);
con --apply los pasa a privado.
"""
from __future__ import annotations

import argparse
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # backend/

from googleapiclient.discovery import build  # noqa: E402

from app import db  # noqa: E402
from app.services.youtube_service import YouTubeService  # noqa: E402


def video_id_from_url(url: str) -> str:
    m = re.search(r"[?&]v=([A-Za-z0-9_-]+)", url or "")
    return m.group(1) if m else ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Privatiza videos antiguos pendientes de un canal")
    parser.add_argument("--channel", type=int, required=True, help="ID de canal en la BD")
    parser.add_argument("--cutoff", default="2026-08-01T00:00:00Z",
                        help="Se CONSERVAN los publicados en/despues de esta fecha ISO")
    parser.add_argument("--apply", action="store_true", help="Aplica los cambios (si no, dry-run)")
    args = parser.parse_args()

    root = Path.cwd()
    db.init(root / "backend" / "runs" / "jobs.db")

    # 1) keep-set desde la BD: lo que subimos nosotros por la app (cualquier canal,
    #    por si algun clip quedo con channel_id distinto). Todo youtube_url guardado.
    keep_ids = set()
    with db._connect() as conn:  # noqa: SLF001
        for row in conn.execute("SELECT youtube_url FROM clips WHERE youtube_url != ''"):
            vid = video_id_from_url(row[0])
            if vid:
                keep_ids.add(vid)

    service = YouTubeService(args.channel, root / "youtube_creds")
    creds = service.get_credentials()
    if not creds:
        raise SystemExit(f"El canal {args.channel} no esta autenticado con YouTube.")
    youtube = build("youtube", "v3", credentials=creds)

    # 2) playlist de subidas del canal.
    ch = youtube.channels().list(part="contentDetails,snippet", mine=True).execute()
    ch_item = (ch.get("items") or [None])[0]
    if not ch_item:
        raise SystemExit("No se pudo leer el canal autenticado.")
    ch_name = ch_item["snippet"]["title"]
    uploads = ch_item["contentDetails"]["relatedPlaylists"]["uploads"]
    print(f"Canal autenticado: {ch_name} | uploads playlist: {uploads}", flush=True)
    print(f"Conservados por BD (subidos por la app): {len(keep_ids)}", flush=True)

    # 3) recorre todos los videos y recoge id + fecha.
    video_ids: list[str] = []
    page = None
    while True:
        pl = youtube.playlistItems().list(
            part="contentDetails", playlistId=uploads, maxResults=50, pageToken=page
        ).execute()
        for it in pl.get("items", []):
            video_ids.append(it["contentDetails"]["videoId"])
        page = pl.get("nextPageToken")
        if not page:
            break

    # 4) estado + snippet en lotes de 50.
    candidates = []
    kept_recent = 0
    kept_db = 0
    already_private = 0
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        resp = youtube.videos().list(part="status,snippet", id=",".join(batch)).execute()
        for v in resp.get("items", []):
            vid = v["id"]
            privacy = v["status"]["privacyStatus"]
            published = v["snippet"]["publishedAt"]
            title = v["snippet"]["title"]
            if privacy == "private":
                already_private += 1
                continue
            if vid in keep_ids:
                kept_db += 1
                continue
            if published >= args.cutoff:
                kept_recent += 1
                continue
            candidates.append((published, vid, title, privacy))

    candidates.sort()
    print(f"\nTotal videos en el canal: {len(video_ids)}")
    print(f"Ya privados (se ignoran): {already_private}")
    print(f"Conservados por ser recientes (>= {args.cutoff}): {kept_recent}")
    print(f"Conservados por estar en la BD: {kept_db}")
    print(f"\n== A PRIVATIZAR: {len(candidates)} ==")
    for published, vid, title, privacy in candidates:
        print(f"  [{published[:10]}] {privacy:8} {vid}  {title[:70]}")

    if not args.apply:
        print("\n(DRY-RUN: no se ha cambiado nada. Anade --apply para privatizarlos.)")
        return

    print(f"\nAplicando: privatizando {len(candidates)} videos...", flush=True)
    done = 0
    for _, vid, title, _ in candidates:
        try:
            service.set_video_privacy(vid, "private")
            done += 1
            print(f"  OK {done}/{len(candidates)}  {vid}  {title[:50]}", flush=True)
            time.sleep(0.2)
        except Exception as exc:  # noqa: BLE001
            print(f"  FALLO {vid}: {exc}", flush=True)
            if "quotaExceeded" in str(exc):
                print("  Quota agotada; parando. Reanuda cuando resetee.", flush=True)
                break
    print(f"\nHecho: {done} privatizados.")


if __name__ == "__main__":
    main()
