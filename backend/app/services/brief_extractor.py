"""Extrae las reglas de compliance de un brief de campana con un LLM.

Lee el brief (Google Docs, texto pegado o URL de texto) y devuelve una
estructura con lo que la app necesita aplicar: caption obligatorio, texto en
pantalla, handles por plataforma, hashtags, etc.
"""
from __future__ import annotations

import json
import os
import re

import requests

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

_GOOGLE_DOC_RE = re.compile(r"docs\.google\.com/document/d/([a-zA-Z0-9_-]+)")


def fetch_brief_text(url: str) -> str:
    """Descarga el texto del brief. Soporta Google Docs (export a txt)."""
    match = _GOOGLE_DOC_RE.search(url)
    if match:
        export = f"https://docs.google.com/document/d/{match.group(1)}/export?format=txt"
        resp = requests.get(export, headers={"User-Agent": UA}, timeout=30)
        resp.raise_for_status()
        return resp.text
    resp = requests.get(url, headers={"User-Agent": UA}, timeout=30)
    resp.raise_for_status()
    return resp.text


SYSTEM = (
    "Eres un asistente que lee briefs de campanas de clipping (ClipFarm, Whop) y "
    "extrae los requisitos de cumplimiento en JSON. No inventes: si algo no esta en "
    "el brief, dejalo VACIO. Nunca uses el nombre del programa/podcast como "
    "captionRequired ni como onScreenText."
)

SCHEMA_HINT = (
    '{'
    '"captionRequired": "SOLO una frase literal OBLIGATORIA que deba ir en el caption/texto '
    'del post (sin el envoltorio tipo \'every post must contain\' y sin comillas). '
    'Si el requisito del caption son solo hashtags o menciones (no una frase fija), dejalo VACIO. '
    'Ej: Subscribe to @thetrailblazerspod on YouTube for the full episode",'
    '"onScreenText": "SOLO si el brief exige una frase, handle o marca FIJA quemada en pantalla '
    'en todos los clips. Si solo pide subtitulos que coincidan con el dialogo (karaoke normal), '
    'dejalo VACIO. No copies el captionRequired ni el nombre del programa.",'
    '"handles": {"youtube": "@...", "tiktok": "@...", "instagram": "@..."},'
    '"hashtags": ["#..."],'
    '"mentions": ["marcas o nombres que hay que mencionar/taggear"],'
    '"keepWatermark": true,'
    '"audience": "resumen de la audiencia requerida",'
    '"payout": "resumen del pago (CPM, min, max)",'
    '"sourceUrl": "link del metraje oficial o episodio si aparece",'
    '"notes": "otras reglas importantes; incluye SIEMPRE los tramos o segmentos que NO se '
    'pueden clipear si el brief los menciona (ej: no clipear 14:32-14:43, nada de anuncios/outro)"'
    '}'
)


def extract_rules(brief_text: str, model: str | None = None) -> dict:
    from openai import OpenAI

    model = model or os.getenv("OPENAI_BRIEF_MODEL", "gpt-4o")
    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        temperature=0.1,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": SYSTEM},
            {
                "role": "user",
                "content": (
                    f"Brief:\n\n{brief_text[:12000]}\n\n"
                    f"Devuelve SOLO JSON con esta forma exacta:\n{SCHEMA_HINT}"
                ),
            },
        ],
    )
    data = json.loads(response.choices[0].message.content or "{}")

    def clean_phrase(text: str) -> str:
        text = str(text or "").strip()
        # quita comillas envolventes y prefijos de instruccion comunes
        text = text.strip('“”"\'')
        text = re.sub(r"^(every\s+post[s]?\s+caption\s+must\s+contain|must\s+contain|caption\s+must\s+contain)\s*[:\-]?\s*",
                      "", text, flags=re.IGNORECASE).strip()
        return text.strip('“”"\'')

    # Normaliza tipos.
    handles = data.get("handles") or {}
    return {
        "onScreenText": clean_phrase(data.get("onScreenText", "")),
        "captionRequired": clean_phrase(data.get("captionRequired", "")),
        "handles": {
            "youtube": str(handles.get("youtube", "")).strip(),
            "tiktok": str(handles.get("tiktok", "")).strip(),
            "instagram": str(handles.get("instagram", "")).strip(),
        },
        "hashtags": [str(h).strip() for h in (data.get("hashtags") or []) if str(h).strip()],
        "mentions": [str(m).strip() for m in (data.get("mentions") or []) if str(m).strip()],
        "keepWatermark": bool(data.get("keepWatermark", False)),
        "audience": str(data.get("audience", "")).strip(),
        "payout": str(data.get("payout", "")).strip(),
        "sourceUrl": str(data.get("sourceUrl", "")).strip(),
        "notes": str(data.get("notes", "")).strip(),
    }
