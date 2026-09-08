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


# Entorno del huevo según el animal (nido + fondo). Palabras clave ES/EN → (nido, fondo).
# El primer patrón que aparezca en el nombre gana; si no, el genérico acogedor.
_EGG_SETTINGS = [
    (("dino", "raptor", "rex", "trex", "brontosaur", "velo"),
     "a nest of leaves and twigs on the mossy prehistoric jungle floor",
     "a lush prehistoric jungle with giant ferns and misty tall trees, soft warm morning light"),
    (("dragon", "dragón", "dragon", "wyvern"),
     "a nest of dark stones and dry branches on a mossy boulder",
     "a moody medieval fantasy forest with mossy rocks, mist and ancient trees, Game of Thrones cinematic style, dramatic light"),
    (("pollit", "chick", "gallin", "hen", "pollo", "chicken", "rooster"),
     "a cozy straw nest inside a rustic wooden henhouse",
     "a warm rustic henhouse / farm coop with straw, wooden slats and soft hay, cozy golden light"),
    (("pingü", "pingu", "penguin"),
     "a little nest of pebbles on the snow",
     "a snowy Antarctic landscape with ice and soft blue-white light"),
    (("tortug", "turtle", "sea turtle"),
     "a shallow hollow in the warm sand",
     "a tropical sandy beach at the water's edge, gentle sea and warm sunset light"),
    (("serpi", "snake", "cobra", "lizard", "lagart", "gecko", "iguana", "crocod", "cocodril", "gator"),
     "a nest of leaves in the damp undergrowth",
     "a dense green tropical jungle with big leaves and dappled light"),
    (("owl", "búho", "buho", "eagle", "águila", "aguila", "hawk", "bird", "pájaro", "pajaro", "parrot", "loro"),
     "a twig nest high on a tree branch",
     "a lush treetop among green leaves and branches, soft dawn light"),
    (("fish", "pez", "shark", "tiburón", "tiburon", "octopus", "pulpo"),
     "a cluster of eggs on a coral rock underwater",
     "a colorful underwater coral reef with soft rays of light, clear blue water"),
]


def _egg_setting(animal: str) -> tuple[str, str]:
    a = animal.lower()
    for keys, nest, bg in _EGG_SETTINGS:
        if any(k in a for k in keys):
            return nest, bg
    return ("a cozy little straw nest on a rustic wooden table",
            "a softly blurred warm cozy home background")


def egg_plan(animal: str, aspect: str = "9:16") -> dict:
    """Plan (determinista, sin LLM → sin coste) para un vídeo de huevo que eclosiona:
    {locked_scene, image_prompt, clips}. `animal` = pollito, dinosaurio, dragón…
    El entorno (nido + fondo) se adapta al animal (dino→selva, dragón→bosque medieval…)."""
    animal = (animal or "chick").strip()
    ar = "vertical portrait 9:16" if aspect == "9:16" else "horizontal 16:9"
    nest, bg = _egg_setting(animal)
    scene = (f"A single {animal} egg in {nest}, set in {bg}, softly blurred background, locked static "
             f"camera, {ar}, photorealistic but cute and charming Pixar-like adorable style.")
    image_prompt = (f"photorealistic, {scene} The egg is whole and intact, sitting still in the nest, "
                    f"nothing hatching yet, no cracks, no animal visible, cute, ultra detailed, no text.")
    return {"locked_scene": scene, "image_prompt": image_prompt, "clips": []}


def butterfly_plan(subject: str, aspect: str = "9:16") -> dict:
    """Plan (sin LLM) para metamorfosis de mariposa: {locked_scene, image_prompt, clips}.
    `subject` = tipo/color de mariposa (monarca, azul, colorida…)."""
    subject = (subject or "butterfly").strip()
    ar = "vertical portrait 9:16" if aspect == "9:16" else "horizontal 16:9"
    scene = (f"Extreme macro close-up of a single green leaf that fills most of the frame, with a "
             f"heavily blurred green garden bokeh background, soft daylight, locked static camera, "
             f"{ar}, photorealistic, cute and charming, very shallow depth of field.")
    image_prompt = (f"photorealistic extreme macro, {scene} A single plump cute caterpillar rests on the "
                    f"leaf, filling a large part of the frame, its body and tiny legs in sharp crisp "
                    f"detail, subject very close to camera, nothing else, no chrysalis, no butterfly yet, "
                    f"ultra detailed, no text.")
    return {"locked_scene": scene, "image_prompt": image_prompt, "clips": []}


def seo(subject: str, channel_rules: str | None = None, kind: str = "plant") -> dict:
    """SEO en INGLÉS: {title, description} con hashtags (#). Reutiliza SEOEngine.
    kind='plant' (time-lapse de crecimiento) o 'egg' (animal gracioso eclosionando)."""
    from .clip_seo import strip_markdown, strip_wrapping_quotes
    from .seo_engine import SEOEngine
    import re as _re

    subject = (subject or ("egg" if kind == "egg" else "plant")).strip()
    tag = _re.sub(r"[^a-zA-Z]", "", subject).lower() or ("egg" if kind == "egg" else "plant")
    if kind == "butterfly":
        snippet = (f"A satisfying, mesmerizing time-lapse of metamorphosis: a caterpillar turns into a "
                   f"chrysalis and then a beautiful {subject} butterfly emerges and spreads its colorful "
                   f"wings. Oddly satisfying, nature, transformation, wholesome. Vertical short video.")
        title_rules = ("Write the title in ENGLISH. Catchy, high-CTR, about a mesmerizing caterpillar to "
                       f"butterfly ({subject}) metamorphosis time-lapse. No hashtags in the title.")
        desc_rules = ("Write the description in ENGLISH. Short hook + a line about the satisfying "
                      f"caterpillar → chrysalis → {subject} butterfly transformation. END with a single "
                      "line of 10-14 relevant hashtags (e.g. #butterfly #metamorphosis #timelapse "
                      f"#satisfying #nature #asmr #shorts) including one for the butterfly (#{tag}).")
    elif kind == "egg":
        snippet = (f"A cute, funny, oddly satisfying video of a {subject} hatching out of an egg in a "
                   f"cozy nest — the egg cracks and an adorable {subject} pops out and does something "
                   f"funny. Wholesome, satisfying, animals, cute. Vertical short video.")
        title_rules = ("Write the title in ENGLISH. Catchy, high-CTR, fun and cute, about a funny "
                       f"{subject} hatching out of an egg. No hashtags in the title.")
        desc_rules = ("Write the description in ENGLISH. Short fun hook + a line about the cute/funny "
                      f"{subject} hatching from its egg. END with a single line of 10-14 relevant "
                      "hashtags (e.g. #hatching #cute #funny #animals #satisfying #asmr #shorts) "
                      f"including one for the animal (#{tag}).")
    else:
        snippet = (f"A satisfying, oddly satisfying ASMR time-lapse of a {subject} growing from a seed "
                   f"into a full plant with flowers and fruit inside a terracotta pot, day and night "
                   f"passing, relaxing plant growth, gardening, nature. Vertical short video.")
        title_rules = ("Write the title in ENGLISH. Catchy, high-CTR title about a satisfying "
                       f"plant-growth time-lapse of a {subject}. No hashtags in the title.")
        desc_rules = ("Write the description in ENGLISH. Short hook + one or two lines about the "
                      f"satisfying {subject} growth time-lapse. END with a single line of 10-14 "
                      "relevant hashtags (e.g. #timelapse #satisfying #plantgrowth #asmr #gardening "
                      f"#nature #shorts) including one for the plant (#{tag}).")
    plant = subject
    eng = SEOEngine()
    if channel_rules:
        title_rules += f"\n{channel_rules}"
        desc_rules += f"\n{channel_rules}"
    title = strip_wrapping_quotes(strip_markdown(eng.generate_video_title(snippet, lang="English", custom_rules=title_rules)))
    desc = strip_markdown(eng.generate_description(snippet, lang="English", custom_rules=desc_rules))
    desc = _re.sub(r"^\s*(video\s+)?(title|description)\s*:\s*", "", desc, flags=_re.IGNORECASE).strip()
    if "#" not in desc:  # respaldo: asegura hashtags
        if kind == "butterfly":
            desc += f"\n\n#butterfly #metamorphosis #timelapse #satisfying #nature #asmr #caterpillar #wholesome #{tag} #shorts"
        elif kind == "egg":
            desc += f"\n\n#hatching #cute #funny #animals #satisfying #asmr #egg #wholesome #{tag} #shorts"
        else:
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
