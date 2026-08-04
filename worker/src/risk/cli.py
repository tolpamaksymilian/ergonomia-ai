"""Command-line interface for the independent Risk Engine V1."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from .processor import process_risk_file
from .schemas import RiskEngineError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build risk-assessment.json from metrics and an explicit profile."
    )
    parser.add_argument("metrics_path", type=Path)
    parser.add_argument("profile_path", type=Path)
    parser.add_argument("output_path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = process_risk_file(
            args.metrics_path,
            args.profile_path,
            args.output_path,
        )
    except (RiskEngineError, OSError) as error:
        print(f"Risk Engine error: {error}", file=sys.stderr)
        return 1

    print(
        "Risk assessment zapisany: "
        f"analysis_id={result['analysis_id']}, "
        f"profile={result['profile']['profile_id']}@{result['profile']['profile_version']}, "
        f"metrics={result['data_quality']['enabled_metric_count']}, "
        f"coverage={result['data_quality']['valid_metric_coverage']:.2%}, "
        f"overall_level={result['overall']['overall_level']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
