"""
SubtitleEngine: Generates karaoke-style subtitles using AssemblyAI word timestamps.

Flow:
  1. transcribe_words() → send audio to AssemblyAI, get word-level timestamps
  2. generate_ass()     → group words into short phrases, generate ASS with karaoke \k tags
  3. burn_subtitles()   → overlay ASS file on video via FFmpeg
"""

import os
import time
import json
import subprocess
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import requests


class SubtitleEngine:
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.getenv("AAI_API_KEY") or os.getenv("ASSEMBLYAI_API_KEY")
        self.base_url = "https://api.assemblyai.com/v2"
    
    # ─── 1. Transcription ───────────────────────────────────────────

    def transcribe_words(self, audio_path: Path, language_code: str = "es") -> List[Dict]:
        """
        Send audio to AssemblyAI and get word-level timestamps.
        Returns list of: {"text": "word", "start": ms, "end": ms, "confidence": float}
        """
        if not self.api_key:
            raise RuntimeError("ASSEMBLYAI_API_KEY not configured")
        
        headers = {"authorization": self.api_key}
        
        # 1. Upload audio
        print(f"[subtitles] Uploading audio: {audio_path}", flush=True)
        with open(audio_path, "rb") as f:
            upload_resp = requests.post(
                f"{self.base_url}/upload",
                headers=headers,
                data=f
            )
        upload_resp.raise_for_status()
        audio_url = upload_resp.json()["upload_url"]
        
        # 2. Request transcription with word-level timestamps
        print("[subtitles] Requesting transcription...", flush=True)
        transcript_resp = requests.post(
            f"{self.base_url}/transcript",
            headers=headers,
            json={
                "audio_url": audio_url,
                "language_code": language_code,
                "word_boost": [],
            }
        )
        transcript_resp.raise_for_status()
        transcript_id = transcript_resp.json()["id"]
        
        # 3. Poll for completion
        print(f"[subtitles] Polling transcript {transcript_id}...", flush=True)
        while True:
            poll_resp = requests.get(
                f"{self.base_url}/transcript/{transcript_id}",
                headers=headers
            )
            poll_resp.raise_for_status()
            result = poll_resp.json()
            
            if result["status"] == "completed":
                words = result.get("words", [])
                print(f"[subtitles] Transcription complete: {len(words)} words", flush=True)
                return words
            elif result["status"] == "error":
                raise RuntimeError(f"AssemblyAI transcription failed: {result.get('error', 'unknown')}")
            
            time.sleep(3)
    
    # ─── 2. ASS Subtitle Generation ────────────────────────────────

    def _group_words_into_phrases(self, words: List[Dict], max_words: int = 4, max_gap_ms: int = 400) -> List[Dict]:
        """
        Group words into short phrases (2-4 words).
        Splits on:
          - max_words reached
          - gap between words > max_gap_ms
          - punctuation at end of word
        """
        phrases = []
        current_phrase = []
        
        for i, word in enumerate(words):
            current_phrase.append(word)
            
            # Decide whether to break here
            should_break = False
            
            # Max words reached
            if len(current_phrase) >= max_words:
                should_break = True
            
            # End of all words
            if i == len(words) - 1:
                should_break = True
            
            # Gap before next word is large (natural pause)
            if not should_break and i < len(words) - 1:
                gap = words[i + 1]["start"] - word["end"]
                if gap > max_gap_ms:
                    should_break = True
            
            # Word ends with punctuation
            if not should_break and word["text"].rstrip().endswith((".", ",", "!", "?", ":", ";")):
                should_break = True
            
            if should_break and current_phrase:
                phrases.append({
                    "words": current_phrase,
                    "start": current_phrase[0]["start"],
                    "end": current_phrase[-1]["end"],
                    "text": " ".join(w["text"] for w in current_phrase)
                })
                current_phrase = []
        
        return phrases

    def _ms_to_ass_time(self, ms: int) -> str:
        """Convert milliseconds to ASS time format: H:MM:SS.CC"""
        total_seconds = ms / 1000.0
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = total_seconds % 60
        return f"{hours}:{minutes:02d}:{seconds:05.2f}"

    def generate_ass(
        self,
        words: List[Dict],
        video_size: Tuple[int, int],
        output_path: Path,
        active_color: str = "&H00FF00&",    # Green (BGR format in ASS)
        inactive_color: str = "&HFFFFFF&",   # White
        outline_color: str = "&H000000&",    # Black outline
        max_words_per_phrase: int = 4
    ) -> Path:
        """
        Generate ASS subtitle file with karaoke highlighting.
        Active word = green, rest = white. Fixed position at bottom of screen.
        """
        W, H = video_size
        is_vertical = H > W
        
        # Font size: scale based on video width
        if is_vertical:
            font_size = int(W * 0.065)       # ~70px for 1080w
            margin_bottom = int(H * 0.22)    # 22% from bottom for vertical
        else:
            font_size = int(H * 0.065)       # ~66px for 1024h
            margin_bottom = int(H * 0.12)    # 12% from bottom for horizontal
        
        outline_size = max(3, font_size // 18)
        shadow_size = 1
        
        # ASS header with style
        ass_header = f"""[Script Info]
Title: Karaoke Subtitles
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Karaoke,Liberation Sans,{font_size},{inactive_color},&H000000FF,{outline_color},&H80000000,-1,0,0,0,100,100,0,0,1,{outline_size},{shadow_size},2,40,40,{margin_bottom},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        
        phrases = self._group_words_into_phrases(words, max_words=max_words_per_phrase)
        
        events = []
        for phrase in phrases:
            start_time = self._ms_to_ass_time(phrase["start"])
            end_time = self._ms_to_ass_time(phrase["end"])
            
            # Build karaoke text: each word gets a \k tag for timing
            # The active word changes color via \k (karaoke sweep)
            parts = []
            for w in phrase["words"]:
                # Duration of this word in centiseconds (ASS \k unit)
                word_dur_cs = max(1, int((w["end"] - w["start"]) / 10))
                
                # Before word starts (gap from phrase start or previous word end)
                word_text = w["text"].upper()
                
                # \kf = karaoke fill, changes color smoothly
                # \1c = primary color (active), but we use override per word
                parts.append(
                    "{" + f"\\kf{word_dur_cs}" + "}" + word_text
                )
            
            karaoke_line = " ".join(parts)
            
            # Override: set the "before" color to white and "after" (highlighted) to green
            # In ASS karaoke: PrimaryColour is the "filled" (active) color
            # SecondaryColour or karaoke fill uses the style's secondary→primary transition
            # We override at the line level to ensure correct colors
            color_override = "{" + f"\\1c{active_color}\\2c{inactive_color}" + "}"
            
            events.append(
                f"Dialogue: 0,{start_time},{end_time},Karaoke,,0,0,0,,{color_override}{karaoke_line}"
            )
        
        ass_content = ass_header + "\n".join(events) + "\n"
        
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(ass_content, encoding="utf-8")
        print(f"[subtitles] Generated ASS: {output_path} ({len(phrases)} phrases)", flush=True)
        
        return output_path

    # ─── 3. Burn Subtitles into Video ──────────────────────────────

    def burn_subtitles(self, video_path: Path, ass_path: Path, output_path: Path) -> Path:
        """
        Burn ASS subtitles into video using FFmpeg.
        """
        print(f"[subtitles] Burning subtitles into video...", flush=True)
        
        cmd = [
            "ffmpeg", "-y",
            "-i", str(video_path),
            "-vf", f"ass={str(ass_path)}",
            "-c:a", "copy",
            "-c:v", "libx264",
            "-crf", "22",
            "-preset", "medium",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            str(output_path)
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[subtitles] FFmpeg error: {result.stderr[-1000:]}", flush=True)
            raise RuntimeError(f"FFmpeg subtitle burn failed: {result.stderr[-500:]}")
        
        print(f"[subtitles] Done! {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)", flush=True)
        return output_path
    
    # ─── Convenience: Full Pipeline ────────────────────────────────

    def add_subtitles_to_video(
        self,
        video_path: Path,
        audio_path: Path,
        video_size: Tuple[int, int],
        cache_dir: Optional[Path] = None
    ) -> Path:
        """
        Full pipeline: transcribe → generate ASS → burn into video.
        Returns the path to the subtitled video.
        """
        cache_dir = cache_dir or video_path.parent
        
        # 1. Check for cached transcription
        words_cache = cache_dir / "subtitle_words.json"
        if words_cache.exists():
            print("[subtitles] Using cached transcription", flush=True)
            words = json.loads(words_cache.read_text())
        else:
            words = self.transcribe_words(audio_path)
            words_cache.write_text(json.dumps(words, indent=2), encoding="utf-8")
        
        if not words:
            print("[subtitles] No words found in transcription, skipping subtitles", flush=True)
            return video_path
        
        # 2. Generate ASS
        ass_path = cache_dir / "karaoke_subtitles.ass"
        self.generate_ass(words, video_size, ass_path)
        
        # 3. Burn subtitles
        subtitled_path = video_path.parent / f"{video_path.stem}_subtitled{video_path.suffix}"
        self.burn_subtitles(video_path, ass_path, subtitled_path)
        
        # 4. Replace original with subtitled version
        video_path.unlink()
        subtitled_path.rename(video_path)
        
        return video_path
