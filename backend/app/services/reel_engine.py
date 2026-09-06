"""Generación de guiones para reels (Avatar Reel). A partir de un disparador
(noticia, idea, tweet, tema) escribe un guion corto de vertical con gancho fuerte
y tono natural — pensado para leerse con TTS (solo el texto hablado, sin
acotaciones). Reutiliza OpenAI (ya configurado en el proyecto).
"""
from __future__ import annotations

import os
import re


SYSTEM = (
    "Eres un guionista experto en vídeo corto vertical (Reels/TikTok/Shorts). "
    "Escribes guiones para NARRAR con voz en off: solo el texto hablado, sin "
    "acotaciones, sin emojis, sin hashtags, sin indicaciones de cámara. Tono "
    "natural y cercano, como hablando a un amigo, NO genérico ni corporativo. "
    "Primera frase = gancho potente que pare el scroll. Luego desarrollas la idea "
    "con claridad y cierras con un remate o una llamada suave a seguir/ver más. "
    "Frases cortas, ritmo ágil. Escribe SIEMPRE en el mismo idioma del disparador."
)


def _target_words(seconds: int) -> int:
    # ~2.5 palabras/seg de locución natural.
    return max(30, int(seconds * 2.5))


def generate_script(trigger: str, angle: str = "", seconds: int = 40,
                    tone_examples: str = "", model: str | None = None) -> str:
    """Devuelve el guion (texto hablado). `trigger` = disparador; `angle` = ángulo
    opcional; `seconds` = duración objetivo; `tone_examples` = ejemplos de guiones
    propios para imitar el tono (opcional)."""
    from openai import OpenAI

    model = model or os.getenv("OPENAI_REEL_MODEL", "gpt-4o")
    words = _target_words(seconds)
    user = (
        f"Disparador (tema/noticia/idea):\n{trigger.strip()}\n\n"
        + (f"Ángulo o enfoque deseado: {angle.strip()}\n\n" if angle.strip() else "")
        + (f"Imita ESTE tono y estilo (ejemplos de guiones propios):\n{tone_examples.strip()[:2000]}\n\n" if tone_examples.strip() else "")
        + f"Escribe el guion hablado para un vídeo de ~{seconds} segundos "
          f"(aprox. {words} palabras). Solo el texto que se va a narrar."
    )
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model,
        temperature=0.8,
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
    )
    script = (resp.choices[0].message.content or "").strip()
    # Limpieza: quita comillas envolventes, encabezados tipo "Guion:", emojis/hashtags.
    script = re.sub(r"^\s*(gui[oó]n|script|texto)\s*:\s*", "", script, flags=re.IGNORECASE).strip()
    script = script.strip("“”\"'")
    script = re.sub(r"#\w+", "", script)
    script = re.sub(r"[ \t]+\n", "\n", script).strip()
    return script


def hook_text(script: str, model: str | None = None) -> str:
    """Gancho corto y potente para la miniatura (3-6 palabras, en el idioma del
    guion), estilo título de Short. Sin comillas ni emojis."""
    from openai import OpenAI

    model = model or os.getenv("OPENAI_REEL_MODEL", "gpt-4o")
    resp = OpenAI().chat.completions.create(
        model=model, temperature=0.8,
        messages=[
            {"role": "system", "content": "Escribe SOLO un gancho de 3-6 palabras para la portada "
             "de un Short, en MAYÚSCULAS, en el idioma del texto, muy llamativo, sin comillas ni emojis."},
            {"role": "user", "content": f"Texto:\n{script.strip()[:600]}\n\nGancho:"},
        ],
    )
    return (resp.choices[0].message.content or "").strip().strip("\"'“”").upper()[:60]


def broll_prompts(script: str, n: int, model: str | None = None) -> list[str]:
    """Convierte el guion en `n` prompts visuales EN INGLÉS (SDXL entiende inglés)
    para generar el b-roll: planos cinematográficos que ilustran cada tramo del
    guion, en orden. Sin texto ni marcas de agua."""
    from openai import OpenAI

    model = model or os.getenv("OPENAI_REEL_MODEL", "gpt-4o")
    sys_p = (
        "You turn a short-form video script into a sequence of b-roll IMAGE prompts "
        "for an SDXL text-to-image model. Return EXACTLY N prompts, in order, each a "
        "vivid, concrete, cinematic visual that illustrates that part of the script. "
        "Prompts in ENGLISH, photographic/cinematic, describe subject + setting + "
        "lighting + mood. No text, no logos, no watermarks, no captions. One line each."
    )
    user = f"N = {n}\n\nScript:\n{script.strip()}\n\nReturn JSON: {{\"prompts\": [\"...\", ...]}} with exactly {n} prompts."
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model, temperature=0.7, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": user}],
    )
    import json as _json
    data = _json.loads(resp.choices[0].message.content or "{}")
    prompts = [str(p).strip() for p in data.get("prompts", []) if str(p).strip()]
    # Estilo común para coherencia y calidad.
    suffix = ", cinematic, highly detailed, sharp focus, professional photography, 8k"
    return [(p + suffix) for p in prompts[:n]] or [f"cinematic establishing shot{suffix}"]


def broll_prompts_for(segments: list[str], model: str | None = None) -> list[str]:
    """Un prompt visual EN INGLÉS por cada SEGMENTO hablado (en orden), anclado a
    lo que se dice en ESE tramo — así la imagen SÍ tiene que ver con lo que se
    escucha. Devuelve exactamente len(segments) prompts."""
    from openai import OpenAI

    segs = [s.strip() for s in segments if s.strip()]
    if not segs:
        return []
    model = model or os.getenv("OPENAI_REEL_MODEL", "gpt-4o")
    sys_p = (
        "You create ONE b-roll IMAGE prompt (for SDXL) per numbered line of a video "
        "voiceover. Each prompt must VISUALLY ILLUSTRATE that exact line — concrete "
        "subject, setting, action that matches what is being said there. Prompts in "
        "ENGLISH, cinematic/photographic, describe subject + setting + lighting. No "
        "text, no logos, no watermarks. Return exactly one prompt per input line, in order."
    )
    numbered = "\n".join(f"{i + 1}. {s}" for i, s in enumerate(segs))
    user = (f"Voiceover lines:\n{numbered}\n\nReturn JSON {{\"prompts\": [\"...\"]}} with "
            f"exactly {len(segs)} prompts, one illustrating each line in order.")
    client = OpenAI()
    resp = client.chat.completions.create(
        model=model, temperature=0.6, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": sys_p}, {"role": "user", "content": user}],
    )
    import json as _json
    data = _json.loads(resp.choices[0].message.content or "{}")
    prompts = [str(p).strip() for p in data.get("prompts", []) if str(p).strip()]
    suffix = ", cinematic, highly detailed, sharp focus, professional photography, 8k"
    # Rellena si el modelo devolvió de menos (repite el último).
    while len(prompts) < len(segs):
        prompts.append(prompts[-1] if prompts else "cinematic establishing shot")
    return [(p + suffix) for p in prompts[:len(segs)]]
