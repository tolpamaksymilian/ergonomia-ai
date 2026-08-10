"""Optional FFmpeg extraction for a bounded set of assessment keyframes."""

from __future__ import annotations

from collections.abc import Mapping
import json
from pathlib import Path
import subprocess
import time
from typing import Any


def extract_keyframes(
    assessment: dict[str, Any],
    overlay_path: Path,
    output_directory: Path,
    storage_prefix: str,
    ffmpeg_binary: str,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    if not overlay_path.is_file() or overlay_path.stat().st_size <= 0:
        return []
    selected = _selected_candidates(assessment, limit)
    output_directory.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    results: list[dict[str, Any]] = []
    for number, candidate in enumerate(selected, start=1):
        timestamp = candidate["timestamp_seconds"]
        method = candidate["method"].lower()
        side = candidate["side"]
        filename = f"assessment-{method}-{side}-{number:02d}.jpg"
        destination = output_directory / filename
        completed = subprocess.run(
            [ffmpeg_binary, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.6f}", "-i", str(overlay_path), "-frames:v", "1", "-q:v", "2", str(destination)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        if completed.returncode != 0 or not destination.is_file() or destination.stat().st_size <= 0:
            continue
        results.append({
            "method": candidate["method"], "side": side,
            "candidate_id": candidate["candidate_id"], "timestamp_seconds": timestamp,
            "storage_path": f"{storage_prefix}/{filename}", "filename": filename,
        })
    assessment["keyframes"] = results
    diagnostics = assessment.setdefault("diagnostics", {})
    if isinstance(diagnostics, dict):
        diagnostics["keyframe_count"] = len(results)
        diagnostics["keyframe_extraction_ms"] = round((time.perf_counter() - started) * 1000.0, 3)
    return results


def write_assessment(path: Path, assessment: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(assessment, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _selected_candidates(assessment: Mapping[str, Any], limit: int) -> list[dict[str, Any]]:
    candidates = assessment.get("candidate_postures")
    if not isinstance(candidates, list):
        return []
    by_id = {item.get("candidate_id"): item for item in candidates if isinstance(item, Mapping)}
    choices: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for method in ("RULA", "REBA"):
        summary = assessment.get(method.lower())
        representative = summary.get("representative") if isinstance(summary, Mapping) else None
        if not isinstance(representative, Mapping):
            continue
        candidate_id = representative.get("candidate_id"); side = representative.get("side")
        candidate = by_id.get(candidate_id)
        timestamp = candidate.get("timestamp_seconds") if isinstance(candidate, Mapping) else None
        if not isinstance(candidate_id, str) or side not in {"left", "right"} or not isinstance(timestamp, (int, float)):
            continue
        key = method, side, candidate_id
        if key not in seen:
            choices.append({"method": method, "side": side, "candidate_id": candidate_id, "timestamp_seconds": float(timestamp)})
            seen.add(key)
    for candidate in candidates:
        if len(choices) >= limit or not isinstance(candidate, Mapping):
            break
        candidate_id = candidate.get("candidate_id"); timestamp = candidate.get("timestamp_seconds")
        if isinstance(candidate_id, str) and isinstance(timestamp, (int, float)):
            key = "REBA", "bilateral", candidate_id
            if key not in seen:
                choices.append({"method": "REBA", "side": "bilateral", "candidate_id": candidate_id, "timestamp_seconds": float(timestamp)})
                seen.add(key)
    return choices[: max(0, limit)]
