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
    text = re.sub(r"^\s{0,3}#{1,6}\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s{0,3}[-*]\s+", "- ", text, flags=re.MULTILINE)
    return text.strip()


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


def generate_clip_seo(clip: dict, channel: dict, root: Path) -> dict:
    """Genera {title, description, tags} para un clip segun las reglas del canal.

    La descripcion incluye el titulo y el enlace del video original, en texto plano.
    """
    lang = LANG_HINT.get(channel.get("language", ""), None)
    rules = channel.get("seoRules") or None
    snippet = clip.get("transcript") or clip.get("title") or ""

    engine = SEOEngine()
    title = strip_markdown(engine.generate_video_title(snippet, lang=lang, custom_rules=rules))
    description = strip_markdown(engine.generate_description(snippet, lang=lang, custom_rules=rules))
    # El modelo a veces antepone etiquetas "TITLE:" / "DESCRIPTION:"; se quitan.
    description = re.sub(r"^\s*TITLE:.*(?:\n|$)", "", description, flags=re.IGNORECASE)
    description = re.sub(r"^\s*DESCRIPTION:\s*", "", description, flags=re.IGNORECASE).strip()
    tags = engine.generate_video_questions_tags(snippet, lang=lang, custom_rules=rules)

    video_rel = clip.get("videoPath") or ""
    if video_rel:
        orig_title, orig_url = read_source_info((root / video_rel).parent)
        footer = [line for line in (orig_title, orig_url) if line]
        if footer:
            description = f"{description}\n\n---\n" + "\n".join(footer)

    return {"title": title, "description": description, "tags": tags}
