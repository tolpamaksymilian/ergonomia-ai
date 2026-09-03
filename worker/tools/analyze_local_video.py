"""Run the production Pose V6.8 core for a local video without Supabase."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import cv2


WORKER_DIRECTORY = Path(__file__).resolve().parents[1]
SOURCE_DIRECTORY = WORKER_DIRECTORY / "src"
if str(SOURCE_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SOURCE_DIRECTORY))

from ergonomics.processor import process_pose_file  # noqa: E402
from assessment.integration import process_assessment_files  # noqa: E402
from report.integration import build_report_file  # noqa: E402
from risk.processor import process_risk_file  # noqa: E402
from pose_v3.hand_pipeline import MediaPipeHandEngine  # noqa: E402
from pose_v6.quality_benchmark import (  # noqa: E402
    collect_quality_kpis,
    compare_quality_documents,
)
from pose_v6.provenance import create_pose_run_provenance  # noqa: E402
from pose_v6.worst_frame_export import export_worst_frames, load_pose_document  # noqa: E402
from pose_worker import (  # noqa: E402
    POSE_SCHEMA_VERSION,
    POSE_VERSION,
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
        description="Lokalny real-video benchmark Pose V6.8 bez Supabase i kolejki."
    )
    parser.add_argument("--input", required=True, help="Ścieżka do lokalnego filmu.")
    parser.add_argument(
        "--output",
        default=".runtime/pose-benchmark",
        help="Katalog wynikowy (domyślnie .runtime/pose-benchmark).",
    )
    parser.add_argument(
        "--profile", choices=("BALANCED", "ACCURATE", "ULTRA"),
        default="ACCURATE", help="Profil compute Pose V6.6.",
    )
    parser.add_argument(
        "--compare-profiles",
        action="store_true",
        help="Uruchom kolejno ACCURATE i ULTRA oraz zapisz comparison.json/md.",
    )
    parser.add_argument(
        "--pipeline-mode",
        choices=("RTMW_ONLY", "V66", "V67_TAR", "V67_TAR_TAPNEXT"),
        default="V67_TAR_TAPNEXT",
        help="Jawny wariant ablation benchmarku temporalnego.",
    )
    parser.add_argument(
        "--compare-temporal-modes",
        action="store_true",
        help="Uruchom cztery tryby RTMW_ONLY/V66/V67_TAR/V67_TAR_TAPNEXT.",
    )
    parser.add_argument("--debug-overlay", action="store_true")
    parser.add_argument("--refine", action=argparse.BooleanOptionalAction, default=None, help="Włącz lub wyłącz ograniczony Pass 2.")
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
    parser.add_argument("--report", action="store_true", help="Utwórz risk-assessment.json i analysis-report.json; wymaga --risk-profile.")
    parser.add_argument("--risk-profile", help="Jawny profil Risk Engine wymagany przez --report.")
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    input_path = Path(arguments.input).expanduser().resolve()
    output_directory = Path(arguments.output).expanduser().resolve()
    if not input_path.is_file() or input_path.stat().st_size <= 0:
        print(f"BŁĄD: wejściowy film nie istnieje albo jest pusty: {input_path}", file=sys.stderr)
        return 2
    if arguments.compare_profiles:
        return _run_profile_comparison(arguments, input_path, output_directory)
    if arguments.compare_temporal_modes:
        return _run_temporal_comparison(arguments, input_path, output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    os.environ["POSE_V6_PROFILE"] = arguments.profile
    _configure_pipeline_mode(arguments.pipeline_mode)
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
        pose_v5_refinement_enabled=(
            False
            if arguments.pipeline_mode == "RTMW_ONLY"
            else settings.pose_v5_refinement_enabled
            if arguments.refine is None
            else bool(arguments.refine)
        ),
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
    analysis["_run_provenance"] = create_pose_run_provenance(
        worker_version=WORKER_VERSION,
        pose_version=POSE_VERSION,
        pose_schema=POSE_SCHEMA_VERSION,
        quality_profile=settings.effective_quality_profile,
        requested_quality_profile=settings.requested_quality_profile,
        effective_quality_profile=settings.effective_quality_profile,
        worker_instance_id="local-pose-benchmark",
        worker_started_at=datetime.now(timezone.utc).isoformat(),
        repository_root=WORKER_DIRECTORY.parent,
    )
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
    if arguments.ergonomics or arguments.assessment or arguments.report:
        process_pose_file(
            result.json_path,
            metrics_path,
        )
    assessment_path = output_directory / "ergonomic-assessment.json"
    if arguments.assessment or arguments.report:
        process_assessment_files(
            result.json_path,
            metrics_path,
            assessment_path,
        )
    if arguments.report:
        if not arguments.risk_profile:
            print("BŁĄD: --report wymaga jawnego --risk-profile; brak ukrytego profilu.", file=sys.stderr)
            return 2
        risk_path = output_directory / "risk-assessment.json"
        process_risk_file(
            metrics_path,
            Path(arguments.risk_profile).expanduser().resolve(),
            risk_path,
        )
        build_report_file(
            analysis,
            metrics_path,
            risk_path,
            output_directory / "analysis-report.json",
            assessment_path=assessment_path,
        )
    diagnostics = json.loads(result.diagnostics_path.read_text(encoding="utf-8"))
    quality_summary_path = output_directory / "quality-summary.json"
    quality_summary_path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "generated_by": "Ergonomia AI local Pose benchmark",
                "worker_version": WORKER_VERSION,
                "profile": arguments.profile,
                "pipeline_mode": arguments.pipeline_mode,
                "input_file": input_path.name,
                "processed_frames": result.processed_frames,
                "accuracy_claimed": False,
                "queue_or_supabase_touched": False,
                "kpis": collect_quality_kpis({"summary": diagnostics}),
                "artifacts": {
                    "overlay": result.video_path.name,
                    "keypoints": result.json_path.name,
                    "diagnostics": result.diagnostics_path.name,
                },
            },
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ) + "\n",
        encoding="utf-8",
    )
    summary_path = output_directory / "validation-summary.txt"
    summary_path.write_text(
        _validation_summary(input_path, fps, frame_count, diagnostics),
        encoding="utf-8",
    )
    if arguments.save_frames:
        _save_selected_frames(result.video_path, output_directory, diagnostics)
    export_worst_frames(
        input_path,
        result.video_path,
        output_directory,
        load_pose_document(result.json_path),
        diagnostics,
        limit=30,
    )
    _print_summary(input_path, fps, frame_count, diagnostics)
    print(f"OUTPUT={output_directory}")
    print(f"QUALITY_SUMMARY={quality_summary_path}")
    print(f"PROFILE={arguments.profile}")
    print(f"PIPELINE_MODE={arguments.pipeline_mode}")
    print(f"WORKER_VERSION={WORKER_VERSION}")
    return 0


def _run_profile_comparison(
    arguments: argparse.Namespace,
    input_path: Path,
    output_directory: Path,
) -> int:
    output_directory.mkdir(parents=True, exist_ok=True)
    summaries: dict[str, dict[str, object]] = {}
    for profile in ("ACCURATE", "ULTRA"):
        profile_directory = output_directory / profile.lower()
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--input", str(input_path),
            "--output", str(profile_directory),
            "--profile", profile,
            "--pipeline-mode", arguments.pipeline_mode,
        ]
        if arguments.debug_overlay:
            command.append("--debug-overlay")
        if arguments.angles:
            command.append("--angles")
        if arguments.objects:
            command.append("--objects")
        if arguments.no_hands:
            command.append("--no-hands")
        if arguments.no_holding:
            command.append("--no-holding")
        if arguments.refine is not None:
            command.append("--refine" if arguments.refine else "--no-refine")
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            print(
                f"BŁĄD: profil {profile} zakończył się kodem {completed.returncode}.",
                file=sys.stderr,
            )
            return completed.returncode
        summary_path = profile_directory / "quality-summary.json"
        summaries[profile] = json.loads(summary_path.read_text(encoding="utf-8"))
    comparison = compare_quality_documents(
        summaries["ULTRA"], summaries["ACCURATE"],
    )
    comparison["comparison_mode"] = "accurate-vs-ultra"
    comparison["profiles"] = {
        "baseline": "ACCURATE",
        "candidate": "ULTRA",
    }
    comparison["queue_or_supabase_touched"] = False
    (output_directory / "comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    (output_directory / "comparison.md").write_text(
        _comparison_markdown(comparison),
        encoding="utf-8",
    )
    print(f"COMPARISON={output_directory / 'comparison.json'}")
    return 0


def _run_temporal_comparison(
    arguments: argparse.Namespace,
    input_path: Path,
    output_directory: Path,
) -> int:
    output_directory.mkdir(parents=True, exist_ok=True)
    modes = ("RTMW_ONLY", "V66", "V67_TAR", "V67_TAR_TAPNEXT")
    summaries: dict[str, dict[str, object]] = {}
    for mode in modes:
        destination = output_directory / mode.lower()
        command = [
            sys.executable, str(Path(__file__).resolve()),
            "--input", str(input_path), "--output", str(destination),
            "--profile", arguments.profile, "--pipeline-mode", mode,
        ]
        if arguments.debug_overlay:
            command.append("--debug-overlay")
        if arguments.no_hands:
            command.append("--no-hands")
        completed = subprocess.run(command, check=False)
        if completed.returncode != 0:
            return completed.returncode
        summaries[mode] = json.loads(
            (destination / "quality-summary.json").read_text(encoding="utf-8")
        )
    comparison = {
        "schema_version": "1.0",
        "comparison_mode": "temporal-expert-ablation",
        "baseline": "RTMW_ONLY",
        "accuracy_claimed": False,
        "modes": {
            mode: collect_quality_kpis(document) for mode, document in summaries.items()
        },
    }
    (output_directory / "temporal-comparison.json").write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return 0


def _configure_pipeline_mode(mode: str) -> None:
    if mode == "RTMW_ONLY":
        os.environ["POSE_ITERATIVE_REFINEMENT_ENABLED"] = "false"
        os.environ["POSE_HIGH_MOTION_RECOVERY_ENABLED"] = "false"
        os.environ["POSE_FLOW_ENABLED"] = "false"
        os.environ["POSE_TEMPORAL_EXPERT_ENABLED"] = "false"
        os.environ["POSE_TAPNEXT_ENABLED"] = "false"
    elif mode == "V66":
        os.environ["POSE_TEMPORAL_EXPERT_ENABLED"] = "false"
        os.environ["POSE_TAPNEXT_ENABLED"] = "false"
    elif mode == "V67_TAR":
        os.environ["POSE_TEMPORAL_EXPERT_ENABLED"] = "true"
        os.environ["POSE_TAPNEXT_ENABLED"] = "false"
    elif mode == "V67_TAR_TAPNEXT":
        os.environ["POSE_TEMPORAL_EXPERT_ENABLED"] = "true"
        os.environ["POSE_TAPNEXT_ENABLED"] = "true"
    else:
        raise ValueError(f"unsupported pipeline mode: {mode}")


def _comparison_markdown(comparison: dict[str, object]) -> str:
    candidate = comparison.get("candidate", {})
    baseline = comparison.get("baseline", {})
    delta = comparison.get("delta", {})
    names = sorted(candidate) if isinstance(candidate, dict) else []
    lines = [
        "# Pose V6.6 — ACCURATE vs ULTRA",
        "",
        "Wartości są technicznymi KPI jakości, nie pomiarem dokładności względem ground truth.",
        "",
        "| KPI | ACCURATE | ULTRA | Delta |",
        "|---|---:|---:|---:|",
    ]
    for name in names:
        lines.append(
            f"| {name} | {baseline.get(name)} | {candidate.get(name)} | "
            f"{delta.get(name) if isinstance(delta, dict) else None} |"
        )
    return "\n".join(lines) + "\n"


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
        "ERGONOMIA AI — LOCAL VALIDATION V0.5",
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
            "PASS 1\nstandard analysis completed",
            "PASS 2\n" + json.dumps(diagnostics.get("refinement", {}), ensure_ascii=False, indent=2),
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


def _save_worst_frames(
    source_path: Path,
    overlay_path: Path,
    output_directory: Path,
    diagnostics: dict[str, object],
    *,
    limit: int,
) -> None:
    ranked = diagnostics.get("temporal_worst_frames", [])
    if not isinstance(ranked, list):
        return
    items = [item for item in ranked if isinstance(item, dict)][:limit]
    if not items:
        return
    destination = output_directory / "worst-frames"
    destination.mkdir(parents=True, exist_ok=True)
    source_capture = cv2.VideoCapture(str(source_path))
    overlay_capture = cv2.VideoCapture(str(overlay_path))
    try:
        for rank, item in enumerate(items, start=1):
            analysis_index = item.get("frame_index")
            source_index = item.get("source_frame_index", analysis_index)
            if not isinstance(analysis_index, int) or not isinstance(source_index, int):
                continue
            source_capture.set(cv2.CAP_PROP_POS_FRAMES, source_index)
            overlay_capture.set(cv2.CAP_PROP_POS_FRAMES, analysis_index)
            source_ok, source_frame = source_capture.read()
            overlay_ok, overlay_frame = overlay_capture.read()
            if not source_ok or source_frame is None or not overlay_ok or overlay_frame is None:
                continue
            stem = f"{rank:02d}-frame-{analysis_index:06d}"
            cv2.imwrite(str(destination / f"{stem}-original.jpg"), source_frame)
            cv2.imwrite(str(destination / f"{stem}-overlay.jpg"), overlay_frame)
            debug = overlay_frame.copy()
            _draw_temporal_expert_candidates(debug, item)
            reasons = item.get("reasons", [])
            reason_text = ", ".join(str(value) for value in reasons) or "LOWEST_COMPOSITE_QUALITY"
            cv2.rectangle(debug, (0, 0), (debug.shape[1], 62), (5, 12, 20), -1)
            cv2.putText(
                debug,
                f"rank={rank} frame={analysis_index} score={item.get('score')}",
                (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.52, (230, 245, 255), 1, cv2.LINE_AA,
            )
            cv2.putText(
                debug,
                reason_text[:120],
                (12, 49), cv2.FONT_HERSHEY_SIMPLEX, 0.42, (80, 210, 255), 1, cv2.LINE_AA,
            )
            cv2.imwrite(str(destination / f"{stem}-debug.jpg"), debug)
            (destination / f"{stem}-reason.json").write_text(
                json.dumps(item, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                encoding="utf-8",
            )
    finally:
        source_capture.release()
        overlay_capture.release()


def _draw_temporal_expert_candidates(
    image: object,
    item: dict[str, object],
) -> None:
    if not hasattr(image, "shape"):
        return
    expert = item.get("temporal_expert_v67")
    if not isinstance(expert, dict):
        return
    sources = (
        ("rtmw_candidate", (255, 210, 30), "RTMW"),
        ("tar_candidate", (220, 60, 230), "TAR"),
    )
    for key, color, _ in sources:
        values = expert.get(key)
        if not isinstance(values, dict):
            continue
        for value in values.values():
            point = value.get("point") if isinstance(value, dict) else None
            if isinstance(point, list) and len(point) == 2:
                cv2.circle(image, (round(float(point[0])), round(float(point[1]))), 4, color, 1, cv2.LINE_AA)
    tracks = expert.get("tapnext_tracks")
    if isinstance(tracks, dict):
        for value in tracks.values():
            if not isinstance(value, dict):
                continue
            forward = value.get("forward_point")
            backward = value.get("backward_point")
            if isinstance(forward, list) and len(forward) == 2:
                cv2.drawMarker(image, (round(float(forward[0])), round(float(forward[1]))), (50, 230, 100), cv2.MARKER_CROSS, 8, 1)
            if isinstance(backward, list) and len(backward) == 2:
                cv2.drawMarker(image, (round(float(backward[0])), round(float(backward[1]))), (40, 150, 255), cv2.MARKER_TILTED_CROSS, 8, 1)


if __name__ == "__main__":
    raise SystemExit(main())
