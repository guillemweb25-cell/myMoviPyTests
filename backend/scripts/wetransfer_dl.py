#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Resolucion y descarga de enlaces de WeTransfer (no soportado por yt-dlp).

Convierte un enlace de WeTransfer (previews/downloads o we.tl) en el enlace
directo al fichero y permite descargarlo.
"""
from __future__ import annotations

import urllib.parse
from typing import Optional

import requests

WT_UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def is_wetransfer(url: str) -> bool:
    return "wetransfer.com" in url or "we.tl/" in url


def _parse_ids(url: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Devuelve (transfer_id, security_hash, recipient_id) del enlace."""
    parts = [p for p in urllib.parse.urlparse(url).path.split("/") if p]
    if "previews" in parts:
        i = parts.index("previews")
        if len(parts) >= i + 3:
            return parts[i + 1], parts[i + 2], None
    if "downloads" in parts:
        rest = parts[parts.index("downloads") + 1:]
        if len(rest) == 3:  # downloads/{id}/{recipient}/{hash}
            return rest[0], rest[2], rest[1]
        if len(rest) == 2:  # downloads/{id}/{hash}
            return rest[0], rest[1], None
    return None, None, None


def resolve_wetransfer(url: str) -> tuple[str, str]:
    """Devuelve (direct_url, filename) para un enlace de WeTransfer."""
    session = requests.Session()
    session.headers.update({"User-Agent": WT_UA})

    if "we.tl/" in url:  # enlace corto -> seguir redireccion
        url = session.get(url, allow_redirects=True, timeout=30).url

    transfer_id, security_hash, recipient_id = _parse_ids(url)
    if not transfer_id or not security_hash:
        raise ValueError("No se pudo interpretar el enlace de WeTransfer.")

    session.get(url, timeout=30)  # cookies de sesion
    api = f"https://wetransfer.com/api/v4/transfers/{transfer_id}/download"
    body: dict[str, object] = {"security_hash": security_hash, "intent": "entire_transfer"}
    if recipient_id:
        body["recipient_id"] = recipient_id

    response = session.post(api, json=body, headers={"x-requested-with": "XMLHttpRequest"}, timeout=30)
    response.raise_for_status()
    direct = response.json().get("direct_link")
    if not direct:
        raise ValueError("WeTransfer no devolvio enlace directo (¿expirado o protegido?).")

    filename = urllib.parse.unquote(urllib.parse.urlparse(direct).path.split("/")[-1]) or "wetransfer_video.mp4"
    return direct, filename
