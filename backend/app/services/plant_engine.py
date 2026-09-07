"""Motor de vídeos de crecimiento de plantas en time-lapse (estilo del PDF
plant_growth). Con un LLM produce el PLAN de un vídeo: bloque de escena bloqueada
+ prompt de la primera imagen (maceta vacía) + 3 prompts de animación encadenados
(semilla→brote, maduración, flor/fruto/cosecha). En INGLÉS (WAN/SDXL entienden inglés).
"""
from __future__ import annotations

import json
import os

IDEAS_FALLBACK = [
    "lemon", "strawberry", "mango", "apple", "sunflower", "rose", "tulip",
    "lavender", "tomato", "chilli pepper", "basil", "carrot",
]


def plant_ideas(model: str | None = None) -> list[dict]:
    """12 ideas de planta (nombre + por qué es satisfactoria de ver crecer), en 3
    categorías. Si el LLM falla, devuelve una lista básica."""
    from openai import OpenAI

    model = model or os.getenv("OPENAI_REEL_MODEL", "gpt-4o")
    try:
        resp = OpenAI().chat.completions.create(
            model=model, temperature=0.9, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": (
                "Devuelve JSON {\"ideas\":[{\"name\":..., \"note\":...}]} con EXACTAMENTE 12 "
                "plantas para vídeos de crecimiento en time-lapse: 4 frutales/frutos, 4 flores, "
                "4 verduras/hierbas. `name` en español, `note` una frase corta de por qué es "
                "visualmente satisfactoria (la floración, el fruto, la hoja).")},
                {"role": "user", "content": "Dame 12 ideas variadas."}],
        )
        data = json.loads(resp.choices[0].message.content or "{}")
        ideas = [{"name": str(i.get("name", "")).strip(), "note": str(i.get("note", "")).strip()}
                 for i in data.get("ideas", []) if str(i.get("name", "")).strip()]
        if ideas:
            return ideas[:12]
    except Exception:  # noqa: BLE001
        pass
    return [{"name": n, "note": ""} for n in IDEAS_FALLBACK]


_SYSTEM = (
    "You are the Plant Growth Time-Lapse Engine. You output the PLAN for one satisfying ASMR "
    "plant-growth time-lapse video as a single continuous locked-camera shot of one plant growing "
    "from seed to harvest inside a pot. The pot, surface, background and camera NEVER change. "
    "Time passes visibly: light cycles day↔night, shadows sweep, the sky shifts.\n"
    "Return STRICT JSON with keys: locked_scene, image_prompt, clips (array of exactly 3 strings).\n"
    "- locked_scene: one precise paragraph (English) describing the pot (material, colour, shape, "
    "size), the soil surface, the surface it sits on, the background, lighting direction and camera "
    "angle. Simple, uncluttered: one pot, one surface, softly blurred natural background.\n"
    "- image_prompt: photorealistic first frame = that exact scene, pot filled with fresh dark soil "
    "and NOTHING growing yet (completely empty pot, no seed, no sprout). Include the locked_scene, "
    "locked straight-on/slightly-low three-quarter framing, pot centred, soil surface clearly "
    "visible, soft daylight, shallow depth of field, ultra-detailed, no text, no watermark, no people.\n"
    "- clips: 3 standalone ~2-4 second animation prompts. Each COPIES the locked_scene verbatim, then "
    "describes ONLY what happens on screen in its own segment. NEVER reference a previous clip. "
    "Camera fully locked (no zoom/pan/tilt/cuts). PURE time-lapse GROWTH only — NO hands, NO people, "
    "NO tools, NO seed being placed, NO harvesting, nothing enters the frame. Growth smooth and "
    "organic (no morphing/flicker). Day↔night cycling visible in every clip.\n"
    "  CLIP 1 EMERGENCE: it STARTS from the bare empty dark soil surface with nothing growing (exactly "
    "like the first frame); then a tiny green sprout slowly pushes up through the centre of the soil, "
    "breaks the surface and unfurls its first two small leaves, growing into a little seedling.\n"
    "  CLIP 2 MATURING: the seedling thickens and rises, the stem strengthening, new leaves unfurl one "
    "after another, side branches extend, filling into a healthy mature specimen of the species.\n"
    "  CLIP 3 FLOWER & FRUIT: buds swell along the stems, flowers open fully, and (for fruiting plants) "
    "fruit forms and ripens to full rich colour on the plant; it ends holding on the beautiful ripe "
    "plant. For a flower species, end on the fully open blooms. No hands, nothing is picked.\n"
    "No prose outside the JSON."
)


def seo(plant: str, channel_rules: str | None = None) -> dict:
    """SEO en INGLÉS para el vídeo de crecimiento: {title, description}. La descripción
    termina con hashtags (#). Reutiliza SEOEngine (motor de clips)."""
    from .clip_seo import strip_markdown, strip_wrapping_quotes
    from .seo_engine import SEOEngine
    import re as _re

    plant = (plant or "plant").strip()
    snippet = (f"A satisfying, oddly satisfying ASMR time-lapse of a {plant} growing from a seed into "
               f"a full plant with flowers and fruit inside a terracotta pot, day and night passing, "
               f"relaxing plant growth, gardening, nature. Vertical short video.")
    eng = SEOEngine()
    title_rules = ("Write the title in ENGLISH. Make it a catchy, high-CTR title about a satisfying "
                   f"plant-growth time-lapse of a {plant}. No hashtags in the title.")
    desc_rules = ("Write the description in ENGLISH. Short hook + one or two lines about the satisfying "
                  f"{plant} growth time-lapse. END with a single line of 10-14 relevant hashtags "
                  "(e.g. #timelapse #satisfying #plantgrowth #asmr #gardening #nature #shorts) including "
                  f"one for the plant (#{_re.sub(r'[^a-zA-Z]', '', plant).lower() or 'plant'}).")
    if channel_rules:
        title_rules += f"\n{channel_rules}"
        desc_rules += f"\n{channel_rules}"
    title = strip_wrapping_quotes(strip_markdown(eng.generate_video_title(snippet, lang="English", custom_rules=title_rules)))
    desc = strip_markdown(eng.generate_description(snippet, lang="English", custom_rules=desc_rules))
    desc = _re.sub(r"^\s*(video\s+)?(title|description)\s*:\s*", "", desc, flags=_re.IGNORECASE).strip()
    if "#" not in desc:  # respaldo: asegura hashtags
        tag = _re.sub(r"[^a-zA-Z]", "", plant).lower() or "plant"
        desc += f"\n\n#timelapse #satisfying #plantgrowth #asmr #gardening #nature #plants #grow #{tag} #shorts"
    return {"title": title[:100], "description": desc[:4900]}


def plant_plan(plant: str, aspect: str = "9:16", model: str | None = None) -> dict:
    """Devuelve {locked_scene, image_prompt, clips:[3]} para la planta dada."""
    from openai import OpenAI

    plant = (plant or "").strip() or "lemon"
    aspect = aspect if aspect in ("9:16", "16:9") else "9:16"
    model = model or os.getenv("OPENAI_REEL_MODEL", "gpt-4o")
    resp = OpenAI().chat.completions.create(
        model=model, temperature=0.6, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": _SYSTEM},
                  {"role": "user", "content": f"Plant: {plant}\nAspect ratio: {aspect}\nProduce the JSON plan."}],
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    clips = [str(c).strip() for c in data.get("clips", []) if str(c).strip()]
    while len(clips) < 3:
        clips.append(clips[-1] if clips else "locked camera time-lapse of the plant growing")
    return {
        "locked_scene": str(data.get("locked_scene", "")).strip(),
        "image_prompt": str(data.get("image_prompt", "")).strip(),
        "clips": clips[:3],
    }
