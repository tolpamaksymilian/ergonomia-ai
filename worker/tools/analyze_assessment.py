"""Build ergonomic-assessment.json locally without Supabase or GPU."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from worker.src.assessment import process_assessment_files  # noqa: E402


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Evidence-aware RULA/REBA assessment")
    result.add_argument("--pose", required=True, type=Path)
    result.add_argument("--ergonomics", required=True, type=Path)
    result.add_argument("--output", required=True, type=Path)
    result.add_argument("--context", type=Path, help="Optional explicit user-provided method inputs")
    result.add_argument("--max-candidates", type=int, default=12)
    result.add_argument("--min-quality", type=float, default=0.55)
    return result


def main() -> int:
    options = parser().parse_args()
    try:
        result = process_assessment_files(
            options.pose, options.ergonomics, options.output,
            user_context_path=options.context,
            maximum_candidates=options.max_candidates,
            minimum_quality=options.min_quality,
        )
    except (OSError, ValueError) as error:
        print(f"Błąd Assessment Engine: {error}", file=sys.stderr)
        return 1
    print(f"analysis_id={result['analysis_id']}")
    for method in ("rula", "reba"):
        summary=result[method]; representative=summary.get("representative") or {}
        score=representative.get("final_score")
        score_range=representative.get("score_range")
        display=score if score is not None else f"{score_range.get('min')}–{score_range.get('max')}" if score_range else "brak"
        print(f"{method.upper()} status={summary['status']} score_or_range={display} missing={len(representative.get('missing_inputs', []))}")
    print(f"CANDIDATES count={len(result['candidate_postures'])}")
    print(f"QUALITY minimum={result['quality']['minimum_candidate_quality']}")
    print(f"output={options.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
