import os
import re
from typing import List, Optional
from openai import OpenAI


def detect_language(text: str) -> str:
    """Detects the dominant language of a script by inspecting unicode blocks.

    Returns an ISO 639-1 code with a human-readable name appended for the LLM
    (e.g. "ko (Korean)"). The format helps the LLM not confuse "ko" with other
    short codes. Falls back to Spanish.
    """
    if not text:
        return "es (Spanish)"
    sample = text[:2000]
    counts = {
        "ko": 0,  # Hangul syllables
        "ja_kana": 0,  # Hiragana + Katakana (Japanese-specific)
        "zh_or_ja_han": 0,  # CJK Unified Ideographs
        "ru": 0,  # Cyrillic
        "ar": 0,  # Arabic
        "latin": 0,
    }
    for c in sample:
        cp = ord(c)
        if 0xAC00 <= cp <= 0xD7AF:
            counts["ko"] += 1
        elif 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF:
            counts["ja_kana"] += 1
        elif 0x4E00 <= cp <= 0x9FFF:
            counts["zh_or_ja_han"] += 1
        elif 0x0400 <= cp <= 0x04FF:
            counts["ru"] += 1
        elif 0x0600 <= cp <= 0x06FF:
            counts["ar"] += 1
        elif c.isalpha():
            counts["latin"] += 1
    total = sum(counts.values()) or 1
    # Hangul wins as soon as it makes up >3% of the sample (Korean scripts
    # often have particles and numbers mixed in, so we don't require a
    # majority).
    if counts["ko"] / total > 0.03:
        return "ko (Korean)"
    if counts["ja_kana"] / total > 0.03:
        return "ja (Japanese)"
    if counts["zh_or_ja_han"] / total > 0.05:
        return "zh (Chinese)"
    if counts["ru"] / total > 0.10:
        return "ru (Russian)"
    if counts["ar"] / total > 0.10:
        return "ar (Arabic)"
    return "es (Spanish)"


class SEOEngine:
    def __init__(self, api_key: Optional[str] = None, provider: str = "openai"):
        self.provider = provider.lower()
        base_url = None
        
        if self.provider == "grok":
            base_url = "https://api.x.ai/v1"
            api_key = api_key or os.getenv("GROK_API_KEY")
            self.model = "grok-4.20-beta"
        else:
            api_key = api_key or os.getenv("OPENAI_API_KEY")
            self.model = "gpt-4o-mini"
            
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def generate_description(self, script_snippet: str, lang: Optional[str] = None, custom_rules: Optional[str] = None) -> str:
        """Generates a rich video description."""
        if lang is None:
            lang = detect_language(script_snippet)
        rules_text = f"\nFOLLOW THESE CHANNEL-SPECIFIC DESCRIPTION RULES AND STRUCTURE:\n{custom_rules}\n" if custom_rules else ""
        system_msg = (
            "You are a YouTube SEO expert. Generate a long, high-quality video description. "
            f"{rules_text}"
            "Include a hook, a detailed summary, and key takeaways. "
            f"The description MUST be written entirely in the same language as the script: {lang}. "
            "The total length MUST NOT exceed 5000 characters. No emojis unless rules specify them."
        )
        user_msg = f"Language: {lang}\nScript snippet:\n{script_snippet}\n\nWrite an SEO description with key points, in {lang}."
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.7
        )
        response_txt = response.choices[0].message.content or ""
        return response_txt.strip()[:5000]

    def generate_video_title(self, script_snippet: str, lang: Optional[str] = None, custom_rules: Optional[str] = None) -> str:
        """Generates a high-CTR video title."""
        if lang is None:
            lang = detect_language(script_snippet)
        rules_text = f"\nAPPLY THESE CHANNEL-SPECIFIC TITLE FORMULAS AND RULES:\n{custom_rules}\n" if custom_rules else ""
        system_msg = (
            "You are a YouTube SEO expert specializing in high-click-through-rate (CTR) titles. "
            f"{rules_text}"
            "Generate one single compelling video title. "
            "Use psychological triggers (curiosity, fear of missing out, direct benefit). "
            f"The title MUST be written entirely in the same language as the script: {lang}. "
            "Max 100 characters. Output ONLY the text, no quotes or emojis."
        )
        user_msg = f"Language: {lang}\nScript snippet:\n{script_snippet}\n\nWrite an optimized YouTube title in {lang}."
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.8
        )
        return (response.choices[0].message.content or "").strip()[:100]

    def generate_video_questions_tags(self, script_snippet: str, count: int = 10, lang: Optional[str] = None, custom_rules: Optional[str] = None) -> str:
        """Generates question-based tags for YouTube."""
        if lang is None:
            lang = detect_language(script_snippet)
        rules_text = f"\nFOLLOW THESE CHANNEL-SPECIFIC TAG RULES:\n{custom_rules}\n" if custom_rules else ""
        system_msg = (
            "You are a YouTube SEO expert. Generate a long string of tags separated by commas. "
            f"{rules_text}"
            "The tags should be the 15 most common questions people ask that this video answers. "
            f"All questions MUST be written entirely in the same language as the script: {lang}. "
            "Separate questions with commas. Total length MUST be under 500 characters. "
            "Output ONLY the comma-separated questions."
        )
        user_msg = f"Language: {lang}\nCount: {count}\nContext:\n{script_snippet}\n\nWrite the questions in {lang}."
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.6
        )
        return (response.choices[0].message.content or "").strip()[:500]

    def generate_hashtags(self, script_snippet: str, count: int = 5, lang: Optional[str] = None, custom_rules: Optional[str] = None) -> List[str]:
        """Generates a list of hashtags."""
        if lang is None:
            lang = detect_language(script_snippet)
        rules_text = f"\nFOLLOW THESE CHANNEL-SPECIFIC HASHTAG RULES:\n{custom_rules}\n" if custom_rules else ""
        system_msg = (
            "You are a YouTube expert. Generate relevant hashtags for a YouTube video. "
            f"{rules_text}"
            f"Hashtags MUST be written in the same language as the script: {lang}. "
            "Output ONLY the hashtags separated by spaces."
        )
        user_msg = f"Language: {lang}\nCount: {count}\nContext:\n{script_snippet}\n\nWrite the hashtags in {lang}."
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.5
        )
        response_txt = response.choices[0].message.content or ""
        raw = response_txt.strip()
        tags = re.split(r"[,\s]+", raw)
        clean_tags = []
        for t in tags:
            t = t.strip()
            if not t: continue
            if not t.startswith("#"): t = "#" + t
            clean_tags.append(t)
        return clean_tags[:count]

    def generate_thumbnail_hook(self, script_snippet: str, lang: Optional[str] = None, custom_rules: Optional[str] = None, channel_name: Optional[str] = None) -> str:
        """Generates a catchy short hook for a YouTube thumbnail."""
        if lang is None:
            lang = detect_language(script_snippet)

        # Determine niche/style based on channel name
        is_jesus = channel_name and ("jesus" in channel_name.lower() or "jesús" in channel_name.lower())

        if is_jesus:
            niche_desc = "Christian/Spiritual channel. The hook tone must be DIVINE, SOLEMN and PROFOUND."
        else:
            niche_desc = "Mystery / curiosity channel. The hook tone must be SHOCKING, AGGRESSIVE and IRRESISTIBLE."

        # Unified format for ALL channels: VERY short, punchy, at most ONE '...'.
        # (The old 3-part format produced cramped, wordy thumbnails that read as
        # three full sentences on top of the image.)
        format_desc = (
            "FORMAT (mandatory): the hook must be VERY SHORT — 2 to 4 words TOTAL, "
            "in ALL CAPS (use the script's native uppercase; Korean/Japanese/Chinese "
            "have no separate caps, use them as-is, big and bold). "
            "Optionally use a SINGLE '...' to split it into two short parts for a "
            "two-line layout. NEVER use more than one '...'. NEVER write full sentences "
            "or questions — just a punchy phrase. "
            "Examples (Spanish): 'TU ÁNGEL... TE VIGILA', 'NO MIRES... ATRÁS', "
            "'EL SECRETO PROHIBIDO', 'LA LUNA... OCULTA EL SOL'. "
            "Examples (Korean): '그는 사라졌다... 영원히', '보지 마라... 뒤를'. "
            "Translate the FORMAT to the script language."
        )

        system_msg = (
            f"You are an expert YouTube CLICKBAIT strategist for a {niche_desc}. "
            "Your goal is to create an IRRESISTIBLE hook. "
            "Use psychological triggers like 'THE FORBIDDEN', 'THE UNKNOWN', 'LETHAL', 'TERRIFYING', 'SECRET' (adapted to the niche AND to the target language). "
            f"{format_desc} "
            f"{f'Additional brand rules: {custom_rules}' if custom_rules else ''} "
            f"The hook MUST be written entirely in: {lang}. Do NOT mix languages. "
            "Output ONLY the text, no quotes or emojis."
        )
        user_msg = f"Script snippet:\n{script_snippet}\n\nWrite a short thumbnail hook."
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.8
        )
        return (response.choices[0].message.content or "").strip()[:80]

    def generate_thumbnail_visual_prompt(self, script_snippet: str, style_desc: str, thumbnail_hook: str = "", custom_rules: Optional[str] = None, include_text_in_prompt: bool = False) -> str:
        """Generates a highly descriptive visual prompt for AI image generators."""
        rules_text = f"\nFOLLOW THESE SPECIFIC STYLE RULES:\n{custom_rules}\n" if custom_rules else ""
        
        text_instruction = ""
        if include_text_in_prompt:
            text_instruction = (
                f"IMPORTANT: Explicitly describe the EXACT text to be included as 'The text \"{thumbnail_hook}\" is written in...'. "
                "Use double quotes for the text itself. Mention it should be 'large, bold, and modern font'. "
                "Describe the font color, outline, and placement based on the provided style rules if available. "
            )
        else:
            text_instruction = (
                "IMPORTANT: Do NOT describe any text or letters in the image. "
                "COMPOSITION RULE (mandatory): place the main character/subject on the RIGHT half of the frame, "
                "occupying roughly the right 35-50% width. Their head and face MUST sit in the lower two thirds — "
                "the upper third of the image (top to ~33%) MUST be empty of any subject's face, hat or head, "
                "because that area is reserved for a large text overlay. "
                "The left half should contain only environment, atmosphere or supporting elements (props, scenery, "
                "background actors at small scale) — never the main subject's face. "
                "Use rule-of-thirds framing with the subject anchored on the right vertical third. "
                "Explicitly include phrases like 'subject framed on the right side of the composition', "
                "'upper third of the frame intentionally empty', 'character's head positioned in the lower-right', "
                "'left side filled with atmospheric environment only' so the image generator follows it."
            )

        system_msg = (
            "You are a creative visual director for high-impact YouTube thumbnails. "
            "Generate a highly descriptive visual prompt in English for an AI image generator. "
            "The prompt should describe a cinematic, professional composition. "
            "Describe central characters with specific emotions, dramatic lighting, and vibrant colors. "
            f"{rules_text}"
            f"{text_instruction}"
            "CRITICAL RULES: Output ONLY the final AI visual prompt. Do NOT use any line breaks or paragraphs (single block of text). "
            "POSE RESTRICTION: Keep character poses simple and natural. AVOID complex limb positions like lifting legs or crossing legs, as they often lead to AI artifacts. "
            "The prompt MUST BE UNDER 1000 CHARACTERS in total length."
        )
        user_msg = (
            f"Style/Niche: {style_desc}\n"
            f"Thumbnail Hook (MUST INCLUDE THIS TEXT): {thumbnail_hook}\n"
            f"Context Snippet:\n{script_snippet}\n"
            f"Generate an expert visual prompt for a professional thumbnail."
        )
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": user_msg}
            ],
            temperature=0.7
        )
        return (response.choices[0].message.content or "").strip()[:2000]
