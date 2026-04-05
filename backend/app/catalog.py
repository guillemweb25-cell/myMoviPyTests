from __future__ import annotations

from pathlib import Path

SCRIPT_DESCRIPTIONS = {
    "download_mp3.py": "Descarga audio desde YouTube y genera MP3.",
    "download_video.py": "Descarga video desde YouTube y lo fusiona en MP4.",
    "download_thumbnail.py": "Descarga la miniatura de YouTube en PNG.",
    "process_video_content.py": "Pipeline web: URL a MP3, TXT y subtitulos.",
    "transcribe_assemblai.py": "Transcribe un MP3 con AssemblyAI y genera TXT/LANG.",
    "transcribe_sutitles.py": "Transcribe y genera subtitulos VTT/SRT.",
    "normalize_output.py": "Normaliza nombres de carpetas y ficheros en output.",
    "make_simple_video.py": "Genera slideshow con FFmpeg desde imagenes.",
    "make_simple_with_moviepy.py": "Generador de video con transiciones en MoviePy.",
    "make_video.py": "Concatena imagenes en video sencillo.",
    "make_kenburns.py": "Crea video Ken Burns basico.",
    "make_kenburns2.py": "Ken Burns con duraciones desde JSON.",
    "make_kenburs_durations.py": "Ken Burns con modos linear/pingpong.",
    "make_kenburs_tiktok.py": "Ken Burns estilo vertical/TikTok.",
    "make_overlay.py": "Combina Ken Burns con un overlay de video.",
    "extract_frames.py": "Extrae todos los frames de un video.",
    "extract_inserted_frames.py": "Detecta clips cortos incrustados en un video.",
    "flip_horizontal.py": "Voltea una imagen horizontalmente.",
    "convert_image_to_png.py": "Convierte imagenes a PNG.",
    "avi_2_mp4.py": "Convierte AVI a MP4.",
    "mkv_2_mp4.py": "Convierte MKV a MP4.",
    "webm2mp4.py": "Convierte todos los WEBM de una carpeta a MP4.",
    "m4a_2_mp3.py": "Convierte M4A a MP3.",
    "m4a_2_wav.py": "Convierte M4A a WAV.",
    "rotar_pdf.py": "Rota paginas impares/pares de un PDF.",
    "cross_fade_demo.py": "Demo de crossfade con MoviePy.",
}

SCRIPT_ARGS_SCHEMA = {
    "download_mp3.py": ["--url", "--browser", "--ffmpeg"],
    "download_video.py": ["--url", "--browser", "--ffmpeg"],
    "download_thumbnail.py": ["--url", "--browser"],
    "process_video_content.py": ["--url", "--browser", "--ffmpeg", "--lang", "--format"],
    "transcribe_assemblai.py": ["--file", "--lang"],
    "transcribe_sutitles.py": ["--file", "--lang", "--format"],
    "make_simple_video.py": ["--folder", "--out", "--time", "--fps", "--w", "--h", "--sort"],
    "make_simple_with_moviepy.py": ["--folder", "--out", "--time", "--fps", "--w", "--h", "--transition", "--motion"],
    "make_overlay.py": ["--folder", "--overlay", "--out", "--width", "--height", "--fps", "--duration"],
    "extract_frames.py": ["--video", "--output"],
    "extract_inserted_frames.py": ["--video", "--output", "--min-frames", "--max-frames", "--min-boundary", "--max-context-diff"],
    "flip_horizontal.py": ["--file"],
    "convert_image_to_png.py": ["--file"],
    "avi_2_mp4.py": ["--file", "--output"],
    "mkv_2_mp4.py": ["--file", "--output"],
    "webm2mp4.py": ["--folder"],
    "m4a_2_mp3.py": ["--file"],
    "m4a_2_wav.py": ["--file"],
    "rotar_pdf.py": ["--pdf", "--out"],
}


def infer_category(script_name: str) -> str:
    if script_name == "process_video_content.py":
        return "Content"
    if script_name.startswith("download_"):
        return "Download"
    if script_name.startswith("transcribe_"):
        return "Transcription"
    if script_name.startswith("make_") or script_name == "cross_fade_demo.py":
        return "Video"
    if script_name in {"avi_2_mp4.py", "mkv_2_mp4.py", "webm2mp4.py", "m4a_2_mp3.py", "m4a_2_wav.py"}:
        return "Conversion"
    if script_name in {"extract_frames.py", "extract_inserted_frames.py", "flip_horizontal.py", "convert_image_to_png.py"}:
        return "Image"
    if script_name in {"normalize_output.py", "rotar_pdf.py"}:
        return "Utility"
    return "Other"


def build_script_entry(path: Path) -> dict:
    name = path.name
    return {
        "name": name,
        "description": SCRIPT_DESCRIPTIONS.get(name, "Script utilitario"),
        "category": infer_category(name),
        "suggestedArgs": SCRIPT_ARGS_SCHEMA.get(name, []),
    }
