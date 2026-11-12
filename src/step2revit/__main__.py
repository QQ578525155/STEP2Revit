"""Command line: ``python -m step2revit part.step part.json``."""

from __future__ import annotations

import argparse
import sys

from step2revit.parse import StepParseError, parse_step


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="step2revit",
        description=(
            "Read one STEP part and write the schema-1 neutral JSON document. "
            "Revit family generation is not done here."
        ),
    )
    parser.add_argument(
        "step_file",
        help="STEP file (.step or .stp), AP203, AP214, or AP242",
    )
    parser.add_argument("output", help="Path of the neutral JSON document to write")
    args = parser.parse_args(argv)
    try:
        parse_step(args.step_file, args.output)
    except StepParseError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
