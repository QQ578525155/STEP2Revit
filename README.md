# STEP2Revit

STEP2Revit converts STEP and SolidWorks hardware parts — bolts, brackets, and fittings — into parametric Revit families (`.rfa`). It is free and open source, built for the Devpost Kiroween 2026 hackathon (Frankenstein category).

The pipeline is STEP in, a neutral JSON description (solids, bounding dimensions, key features and parameters), then a parametric `.rfa`. This package implements the STEP parser. The `.rfa` builder is not included: it has to run inside Revit on Windows and reads only the JSON document. The contract is [`.kiro/specs/step-to-rfa-pipeline/requirements.md`](.kiro/specs/step-to-rfa-pipeline/requirements.md). How the parser recognizes a cylinder, a hole, and an extrusion is [`.kiro/specs/step-to-rfa-pipeline/design.md`](.kiro/specs/step-to-rfa-pipeline/design.md).

## Install

Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

The package depends on `cadquery-ocp` (Open CASCADE bindings, Apache-2.0). The `[dev]` extra installs pytest and ruff.

## Parse a STEP part

```bash
python -m step2revit part.step part.json
```

```python
from step2revit import parse_step

document = parse_step("part.step", "part.json")
```

`part.step` must be STEP AP203, AP214, or AP242 (`.step` or `.stp`). `part.json` is schema 1. Lengths are millimetres. `source.length_unit` is the unit name from the STEP file before that conversion.

## Tests

```bash
pytest
```

`ruff check src tests` runs the same lint check as CI. The geometry tests generate small solids in-process (box, cylinder, plate with a hole) and do not download STEP files. See [tests/NOTICE](tests/NOTICE).

## License

MIT. See [LICENSE](LICENSE).
