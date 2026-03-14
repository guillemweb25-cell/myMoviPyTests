#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np


@dataclass
class Signature:
    thumb: np.ndarray
    hist: np.ndarray


@dataclass
class SegmentCandidate:
    start: int
    end: int
    entry_score: float
    exit_score: float
    context_score: float


def build_signature(frame: np.ndarray) -> Signature:
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    thumb = cv2.resize(gray, (64, 36), interpolation=cv2.INTER_AREA).astype(np.float32)

    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    hist = cv2.calcHist([hsv], [0, 1], None, [24, 24], [0, 180, 0, 256])
    hist = cv2.normalize(hist, hist).flatten().astype(np.float32)
    return Signature(thumb=thumb, hist=hist)


def signature_diff(a: Signature, b: Signature) -> float:
    thumb_diff = float(np.mean(np.abs(a.thumb - b.thumb)))
    hist_diff = float(cv2.compareHist(a.hist, b.hist, cv2.HISTCMP_BHATTACHARYYA)) * 100.0
    return thumb_diff * 0.65 + hist_diff * 0.35


def load_video(video_path: Path) -> tuple[list[np.ndarray], list[Signature], float]:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise SystemExit(f"No se puede abrir el video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
    frames: list[np.ndarray] = []
    signatures: list[Signature] = []

    while True:
        ok, frame = cap.read()
        if not ok:
            break
        frames.append(frame)
        signatures.append(build_signature(frame))

    cap.release()
    return frames, signatures, float(fps)


def representative_signature(signatures: list[Signature], start: int, end: int) -> Signature:
    middle = start + (end - start) // 2
    return signatures[middle]


def find_boundaries(diffs: list[float], min_threshold: float) -> list[int]:
    if not diffs:
        return []

    mean_diff = float(np.mean(diffs))
    std_diff = float(np.std(diffs))
    adaptive_threshold = max(min_threshold, mean_diff + std_diff * 1.75)

    boundaries = [idx + 1 for idx, score in enumerate(diffs) if score >= adaptive_threshold]
    return sorted(set(boundaries))


def build_segments(frame_count: int, boundaries: list[int]) -> list[tuple[int, int]]:
    points = [0, *boundaries, frame_count]
    segments: list[tuple[int, int]] = []
    for idx in range(len(points) - 1):
        start = points[idx]
        end = points[idx + 1] - 1
        if start <= end:
            segments.append((start, end))
    return segments


def detect_inserted_segments(
    signatures: list[Signature],
    fps: float,
    min_frames: int,
    max_frames: int,
    min_boundary: float,
    max_context_diff: float,
) -> list[SegmentCandidate]:
    if len(signatures) < 4:
        return []

    diffs = [signature_diff(signatures[idx], signatures[idx + 1]) for idx in range(len(signatures) - 1)]
    boundaries = find_boundaries(diffs, min_boundary)
    segments = build_segments(len(signatures), boundaries)

    candidates: list[SegmentCandidate] = []
    for segment_index in range(1, len(segments) - 1):
        start, end = segments[segment_index]
        length = end - start + 1
        if length < min_frames or length > max_frames:
            continue

        prev_start, prev_end = segments[segment_index - 1]
        next_start, next_end = segments[segment_index + 1]

        entry_score = diffs[start - 1] if start - 1 < len(diffs) else 0.0
        exit_score = diffs[end] if end < len(diffs) else 0.0

        prev_sig = representative_signature(signatures, prev_start, prev_end)
        next_sig = representative_signature(signatures, next_start, next_end)
        context_score = signature_diff(prev_sig, next_sig)

        if entry_score < min_boundary or exit_score < min_boundary:
            continue
        if context_score > max_context_diff:
            continue

        candidates.append(
            SegmentCandidate(
                start=start,
                end=end,
                entry_score=entry_score,
                exit_score=exit_score,
                context_score=context_score,
            )
        )

    if candidates:
        return candidates

    # Fallback: if no candidate matches the "return to same context" rule,
    # keep the strongest short segments so the user still gets something to review.
    fallback: list[SegmentCandidate] = []
    for segment_index in range(1, len(segments) - 1):
        start, end = segments[segment_index]
        length = end - start + 1
        if length < min_frames or length > max_frames:
            continue

        entry_score = diffs[start - 1] if start - 1 < len(diffs) else 0.0
        exit_score = diffs[end] if end < len(diffs) else 0.0
        fallback.append(
            SegmentCandidate(
                start=start,
                end=end,
                entry_score=entry_score,
                exit_score=exit_score,
                context_score=999.0,
            )
        )

    fallback.sort(key=lambda item: (item.entry_score + item.exit_score), reverse=True)
    return fallback[:5]


def save_detected_segments(
    frames: list[np.ndarray],
    video_path: Path,
    out_dir: Path,
    candidates: list[SegmentCandidate],
    fps: float,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: list[dict[str, object]] = []

    for idx, candidate in enumerate(candidates, start=1):
        segment_dir = out_dir / f"segment_{idx:03d}_{candidate.start:06d}_{candidate.end:06d}"
        segment_dir.mkdir(parents=True, exist_ok=True)

        for frame_idx in range(candidate.start, candidate.end + 1):
            frame_path = segment_dir / f"frame_{frame_idx:06d}.jpg"
            cv2.imwrite(str(frame_path), frames[frame_idx])

        manifest.append(
            {
                "segment": idx,
                "start_frame": candidate.start,
                "end_frame": candidate.end,
                "start_seconds": round(candidate.start / fps, 3),
                "end_seconds": round(candidate.end / fps, 3),
                "frame_count": candidate.end - candidate.start + 1,
                "entry_score": round(candidate.entry_score, 3),
                "exit_score": round(candidate.exit_score, 3),
                "context_score": round(candidate.context_score, 3),
            }
        )

    (out_dir / "segments.json").write_text(
        json.dumps(
            {
                "video": str(video_path),
                "fps": fps,
                "detected_segments": manifest,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", required=True, help="Ruta del video")
    parser.add_argument("--output", required=True, help="Carpeta de salida")
    parser.add_argument("--min-frames", type=int, default=2, help="Duracion minima del clip incrustado")
    parser.add_argument("--max-frames", type=int, default=18, help="Duracion maxima del clip incrustado")
    parser.add_argument("--min-boundary", type=float, default=20.0, help="Corte minimo para entrada/salida")
    parser.add_argument("--max-context-diff", type=float, default=18.0, help="Diferencia maxima entre contexto anterior y posterior")
    args = parser.parse_args()

    video_path = Path(args.video)
    out_dir = Path(args.output)

    frames, signatures, fps = load_video(video_path)
    candidates = detect_inserted_segments(
        signatures=signatures,
        fps=fps,
        min_frames=args.min_frames,
        max_frames=args.max_frames,
        min_boundary=args.min_boundary,
        max_context_diff=args.max_context_diff,
    )
    save_detected_segments(frames, video_path, out_dir, candidates, fps)

    print(f"Clips incrustados detectados: {len(candidates)}")
    print(f"Salida: {out_dir}")


if __name__ == "__main__":
    main()
