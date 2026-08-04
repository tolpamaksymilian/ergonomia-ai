"""Command-line entry point for the Ergonomics Metrics Engine V1."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .processor import InputSchemaError, process_pose_file


def parse_arguments(arguments: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Oblicza surowe metryki ergonomiczne z pose-keypoints.json V3.0."
    )
    parser.add_argument("input_pose_json", type=Path, help="Wejściowy pose-keypoints.json")
    parser.add_argument("output_metrics_json", type=Path, help="Docelowy ergonomics-metrics.json")
    return parser.parse_args(arguments)


def main(arguments: list[str] | None = None) -> int:
    options = parse_arguments(arguments)
    try:
        result = process_pose_file(options.input_pose_json, options.output_metrics_json)
    except FileNotFoundError as error:
        print(f"Błąd: {error}", file=sys.stderr)
        return 2
    except IsADirectoryError as error:
        print(f"Błąd: {error}", file=sys.stderr)
        return 2
    except json.JSONDecodeError as error:
        print(
            f"Błąd: niepoprawny JSON w {options.input_pose_json} "
            f"(wiersz {error.lineno}, kolumna {error.colno}): {error.msg}",
            file=sys.stderr,
        )
        return 3
    except InputSchemaError as error:
        print(f"Błąd schematu: {error}", file=sys.stderr)
        return 4
    except (OSError, ValueError) as error:
        print(f"Błąd przetwarzania: {error}", file=sys.stderr)
        return 5

    print(
        f"Zapisano {len(result['frames'])} klatek metryk do: {options.output_metrics_json}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
