"""Generacion de SEO para un clip (titulo, descripcion, tags).

Compartido por el endpoint de previsualizacion y por el job de subida, para que
lo que ves sea exactamente lo que se publica.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .seo_engine import SEOEngine

LANG_HINT = {"es": "es (Spanish)", "en": "en (English)"}


def strip_markdown(text: str) -> str:
    """Convierte a texto plano: quita negritas, cabeceras, codigo y enlaces md."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"__(.*?)__", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"^\s{0,3}#{1,6}\s+", "", text, flags=re.MULTILINE)  # cabeceras "# " (no hashtags)
    text = re.sub(r"^\s{0,3}[-*]\s+", "- ", text, flags=re.MULTILINE)
    return text.strip()


def strip_wrapping_quotes(text: str) -> str:
    """Quita las comillas que envuelven el texto (rectas o tipograficas)."""
    text = text.strip()
    quotes = "\"'“”‘’«»"
    while len(text) >= 2 and text[0] in quotes and text[-1] in quotes:
        text = text[1:-1].strip()
    return text


def read_source_info(video_folder: Path) -> tuple[str, str]:
    """Devuelve (titulo_original, url_original) de source.json / source_url.txt."""
    title, url = "", ""
    source_json = video_folder / "source.json"
    if source_json.exists():
        try:
            data = json.loads(source_json.read_text(encoding="utf-8"))
            title = data.get("title", "") or ""
            url = data.get("url", "") or ""
        except Exception:
            pass
    if not url:
        source_url = video_folder / "source_url.txt"
        if source_url.exists():
            url = source_url.read_text(encoding="utf-8").strip()
    return title, url


def generate_clip_seo(clip: dict, channel: dict, root: Path, campaign_rules: dict | None = None) -> dict:
    """Genera {title, description, tags} para un clip segun las reglas del canal
    y, si se pasan, las reglas de compliance de la campana (caption obligatorio,
    hashtags). La descripcion incluye el titulo y enlace del video original.
    """
    lang = LANG_HINT.get(channel.get("language", ""), None)
    rules = channel.get("seoRules") or None
    snippet = clip.get("transcript") or clip.get("title") or ""

    engine = SEOEngine()
    title = strip_wrapping_quotes(strip_markdown(engine.generate_video_title(snippet, lang=lang, custom_rules=rules)))
    description = strip_markdown(engine.generate_description(snippet, lang=lang, custom_rules=rules))
    # El modelo a veces antepone etiquetas "(Video) Title:" / "(Video) Description:".
    description = re.sub(r"^\s*(video\s+)?title:.*(?:\n|$)", "", description, flags=re.IGNORECASE)
    description = re.sub(r"^\s*(video\s+)?description:\s*", "", description, flags=re.IGNORECASE).strip()
    tags = engine.generate_video_questions_tags(snippet, lang=lang, custom_rules=rules)

    # Bloque de compliance PRIMERO (arriba del todo), para que el revisor lo vea sin
    # bajar: caption obligatorio + handle de YouTube. (Un rejection típico es "tag
    # properly: @handle" cuando el handle iba enterrado al final de la descripcion.)
    header: list[str] = []
    if campaign_rules:
        required = (campaign_rules.get("captionRequired") or "").strip()
        if required:
            header.append(required)
        yt_handle = ((campaign_rules.get("handles") or {}).get("youtube") or "").strip()
        blob = (" ".join(header) + " " + description).lower()
        if yt_handle and yt_handle.lower() not in blob:
            header.append(yt_handle)

    parts = []
    if header:
        parts.append("\n".join(header))
    parts.append(description)

    # Titulo + enlace del video original (salvo si la fuente es WeTransfer:
    # es un enlace temporal/privado que no debe ir en la descripcion publica).
    video_rel = clip.get("videoPath") or ""
    if video_rel:
        orig_title, orig_url = read_source_info((root / video_rel).parent)
        is_wetransfer = "wetransfer.com" in orig_url or "we.tl/" in orig_url
        if not is_wetransfer:
            footer = [line for line in (orig_title, orig_url) if line]
            if footer:
                parts.append("\n".join(footer))

    # Hashtags obligatorios de la campana.
    if campaign_rules:
        hashtags = campaign_rules.get("hashtags") or []
        if hashtags:
            parts.append(" ".join(hashtags))

    return {"title": title, "description": "\n\n".join(parts), "tags": tags}
