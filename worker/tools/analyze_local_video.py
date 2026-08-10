"""Run the real Pose V0.4 pipeline for a local video without Supabase."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import replace
from pathlib import Path

import cv2


WORKER_DIRECTORY = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = WORKER_DIRECTORY / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from ergonomics.processor import process_pose_file  # noqa: E402
from assessment.integration import process_assessment_files  # noqa: E402
from pose_v3.hand_pipeline import MediaPipeHandEngine  # noqa: E402
from pose_worker import (  # noqa: E402
    WORKER_VERSION,
    configure_logging,
    create_hand_pipeline_config,
    initialize_pose_model,
    load_settings,
    process_pose_video,
    scan_active_segment,
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Lokalna walidacja Ergonomia AI Worker V0.4 bez Supabase."
    )
    parser.add_argument("--input", required=True, help="Ścieżka do lokalnego filmu.")
    parser.add_argument("--output", required=True, help="Katalog wynikowy.")
    parser.add_argument("--debug-overlay", action="store_true")
    parser.add_argument("--angles", action="store_true", help="Pokaż kąty metryk na overlayu.")
    parser.add_argument("--objects", action="store_true", help="Pokaż śledzone obiekty w trybie QA.")
    parser.add_argument("--no-hands", action="store_true")
    parser.add_argument("--no-holding", action="store_true")
    parser.add_argument(
        "--save-frames",
        action="store_true",
        help="Zapisz do 20 automatycznie wybranych klatek QA.",
    )
    parser.add_argument("--ergonomics", action="store_true")
    parser.add_argument(
        "--assessment",
        action="store_true",
        help="Po metrykach utwórz ergonomic-assessment.json (RULA/REBA beta).",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    input_path = Path(arguments.input).expanduser().resolve()
    output_directory = Path(arguments.output).expanduser().resolve()
    if not input_path.is_file() or input_path.stat().st_size <= 0:
        print(f"BŁĄD: wejściowy film nie istnieje albo jest pusty: {input_path}", file=sys.stderr)
        return 2
    output_directory.mkdir(parents=True, exist_ok=True)

    settings = load_settings(require_supabase=False)
    settings = replace(
        settings,
        draw_hands=settings.draw_hands and not arguments.no_hands,
        holding_enabled=(
            settings.holding_enabled
            and not arguments.no_hands
            and not arguments.no_holding
        ),
        debug_overlay=bool(arguments.debug_overlay),
        draw_angles=settings.draw_angles or bool(arguments.angles),
        draw_objects=settings.draw_objects or bool(arguments.objects),
        keep_worker_files=True,
    )
    logger = configure_logging()
    model = initialize_pose_model(settings, logger)
    hand_engine = MediaPipeHandEngine(create_hand_pipeline_config(settings))

    capture = cv2.VideoCapture(str(input_path))
    try:
        fps = float(capture.get(cv2.CAP_PROP_FPS))
        frame_count = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT))
    finally:
        capture.release()
    if fps <= 0.0 or frame_count <= 0:
        print("BŁĄD: nieprawidłowe FPS lub liczba klatek.", file=sys.stderr)
        return 2

    analysis = {
        "id": "local-validation",
        "title": f"Local validation: {input_path.name}",
        "source_frame_count": frame_count,
        "source_duration_seconds": frame_count / fps,
        "source_width": width,
        "source_height": height,
    }
    try:
        active_segment = scan_active_segment(
            None,
            settings,
            model,
            str(analysis["id"]),
            input_path,
            logger,
        )
        result = process_pose_video(
            None,
            settings,
            model,
            hand_engine,
            analysis,
            input_path,
            output_directory,
            active_segment,
            logger,
        )
    finally:
        hand_engine.close()

    metrics_path = output_directory / "ergonomics-metrics.json"
    if arguments.ergonomics or arguments.assessment:
        process_pose_file(
            result.json_path,
            metrics_path,
        )
    if arguments.assessment:
        process_assessment_files(
            result.json_path,
            metrics_path,
            output_directory / "ergonomic-assessment.json",
        )
    diagnostics = json.loads(result.diagnostics_path.read_text(encoding="utf-8"))
    summary_path = output_directory / "validation-summary.txt"
    summary_path.write_text(
        _validation_summary(input_path, fps, frame_count, diagnostics),
        encoding="utf-8",
    )
    if arguments.save_frames:
        _save_selected_frames(result.video_path, output_directory, diagnostics)
    _print_summary(input_path, fps, frame_count, diagnostics)
    print(f"OUTPUT={output_directory}")
    print(f"WORKER_VERSION={WORKER_VERSION}")
    return 0


def _print_summary(
    video_path: Path,
    fps: float,
    frame_count: int,
    diagnostics: dict[str, object],
) -> None:
    tracking = diagnostics.get("tracking", {})
    hands = diagnostics.get("hands", {})
    holding = diagnostics.get("holding", {})
    quality = diagnostics.get("quality", {})
    print("VIDEO")
    print(f"file={video_path.name} duration={frame_count / fps:.3f}s fps={fps:.3f} frames={frame_count}")
    print("BODY")
    if isinstance(tracking, dict):
        print(
            f"valid_ratio={tracking.get('valid_body_frame_ratio')} "
            f"partial_ratio={tracking.get('partial_ratio')} "
            f"out_of_frame_ratio={tracking.get('out_of_frame_ratio')} "
            f"track_losses={tracking.get('track_loss_count')} "
            f"reacquisitions={tracking.get('reacquisition_count')}"
        )
    for side in ("left", "right"):
        print(f"{side.upper()} HAND")
        hand = hands.get(side, {}) if isinstance(hands, dict) else {}
        hold = holding.get(side, {}) if isinstance(holding, dict) else {}
        print(
            f"valid_ratio={hand.get('valid_ratio') if isinstance(hand, dict) else None} "
            f"holding_seconds={hold.get('likely_holding_seconds') if isinstance(hold, dict) else None} "
            f"episodes={hold.get('holding_episode_count') if isinstance(hold, dict) else None}"
        )
    bimanual = holding.get("bimanual", {}) if isinstance(holding, dict) else {}
    print("BIMANUAL")
    print(f"holding_seconds={bimanual.get('likely_holding_seconds') if isinstance(bimanual, dict) else None}")
    print("QUALITY")
    print(f"overall_quality={quality.get('mean_frame_quality') if isinstance(quality, dict) else None}")
    print("RUNTIME")
    runtime = diagnostics.get("runtime_seconds")
    processing_fps = (
        frame_count / float(runtime)
        if isinstance(runtime, (int, float)) and runtime > 0
        else None
    )
    print(f"total_seconds={runtime} processing_fps={processing_fps:.3f}" if processing_fps else f"total_seconds={runtime}")


def _validation_summary(
    video_path: Path,
    fps: float,
    frame_count: int,
    diagnostics: dict[str, object],
) -> str:
    tracking = diagnostics.get("tracking", {})
    body = diagnostics.get("body", {})
    hands = diagnostics.get("hands", {})
    holding = diagnostics.get("holding", {})
    quality = diagnostics.get("quality", {})
    runtime = diagnostics.get("runtime_breakdown_seconds", {})
    warnings = quality.get("warning_codes", []) if isinstance(quality, dict) else []
    lines = [
        "ERGONOMIA AI — LOCAL VALIDATION V0.4",
        f"VIDEO\nfile={video_path.name} fps={fps:.3f} frames={frame_count}",
        "TRACKING\n" + json.dumps(tracking, ensure_ascii=False, indent=2),
        "BODY\n" + json.dumps(body, ensure_ascii=False, indent=2),
    ]
    for side in ("left", "right"):
        value = hands.get(side, {}) if isinstance(hands, dict) else {}
        lines.append(f"{side.upper()} HAND\n" + json.dumps(value, ensure_ascii=False, indent=2))
    lines.extend(
        [
            "HOLDING\n" + json.dumps(holding, ensure_ascii=False, indent=2),
            "QUALITY\n" + json.dumps(quality, ensure_ascii=False, indent=2),
            "RUNTIME\n" + json.dumps(runtime, ensure_ascii=False, indent=2),
            "WARNINGS\n" + ("\n".join(str(item) for item in warnings) if warnings else "none"),
        ]
    )
    return "\n\n".join(lines) + "\n"


def _save_selected_frames(
    overlay_path: Path,
    output_directory: Path,
    diagnostics: dict[str, object],
) -> None:
    raw_indices = diagnostics.get("worst_frame_indices", [])
    indices = [
        value
        for value in raw_indices
        if isinstance(value, int) and not isinstance(value, bool) and value >= 0
    ][:20]
    if not indices:
        return
    selected = set(indices)
    frames_directory = output_directory / "qa-frames"
    frames_directory.mkdir(parents=True, exist_ok=True)
    capture = cv2.VideoCapture(str(overlay_path))
    try:
        index = 0
        while selected:
            success, frame = capture.read()
            if not success or frame is None:
                break
            if index in selected:
                cv2.imwrite(str(frames_directory / f"frame-{index:06d}.jpg"), frame)
                selected.remove(index)
            index += 1
    finally:
        capture.release()


if __name__ == "__main__":
    raise SystemExit(main())
