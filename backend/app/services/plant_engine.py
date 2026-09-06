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
    "- clips: 3 standalone ~4-second animation prompts. Each COPIES the locked_scene verbatim, then "
    "describes ONLY what happens on screen in its own segment. NEVER reference a previous clip. "
    "Camera fully locked (no zoom/pan/tilt/cuts). Growth smooth and organic (no morphing/flicker). "
    "Day↔night cycling visible in every clip.\n"
    "  CLIP 1 SEED & SPROUT: a hand presses a single seed into the soil centre and covers it, exits, "
    "returns to mist it with a spray bottle, exits; then time-lapse: a pale green shoot pushes up, "
    "unfurls its first two leaves, grows into a small seedling.\n"
    "  CLIP 2 MATURING: no hands; pure time-lapse; the seedling thickens and rises, new leaves unfurl "
    "in sequence, side branches extend, filling into a healthy mature specimen of the species.\n"
    "  CLIP 3 FLOWER/FRUIT/HARVEST: time-lapse continues, buds swell, flowers open, fruit forms and "
    "ripens to full colour; slows to real time; a hand plucks the ripest fruit, sets it down, slices "
    "it in half to reveal the interior, then a clear thumbs up to camera. (If a flower species, cut "
    "one full bloom at the stem instead, lay it down, thumbs up.)\n"
    "No prose outside the JSON."
)


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
