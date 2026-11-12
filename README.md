# STEP2Revit

STEP2Revit converts STEP and SolidWorks hardware parts — bolts, brackets, and fittings — into parametric Revit families (`.rfa`). It is free and open source, built for the Devpost Kiroween 2026 hackathon (Frankenstein category).

The pipeline is STEP in, a neutral JSON description (solids, bounding dimensions, key features and parameters), then a parametric `.rfa`. This package implements the STEP parser and the family builder. The builder reads only the JSON document and has to run inside Revit on Windows. GitHub Actions does not run Revit, and this repository does not contain a generated `.rfa`. The contract is [`.kiro/specs/step-to-rfa-pipeline/requirements.md`](.kiro/specs/step-to-rfa-pipeline/requirements.md). How the parser recognizes a cylinder, a hole, and an extrusion is [`.kiro/specs/step-to-rfa-pipeline/design.md`](.kiro/specs/step-to-rfa-pipeline/design.md). How the builder turns that JSON into a family is [`.kiro/specs/step-to-rfa-pipeline/builder.md`](.kiro/specs/step-to-rfa-pipeline/builder.md).

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

## Build a Revit family

This step runs inside Revit on Windows. Revit is not installed in GitHub Actions or in this project's cloud environment. The steps below do not produce a `.rfa` unless you run them inside Revit.

1. Install [pyRevit](https://github.com/pyrevitlabs/pyRevit) (free and open source) and use its CPython engine on Python 3.11 or newer. Revit's own Python shell on Revit 2025 or newer also works.
2. Install this package into that Python with `python -m pip install -e .`, or run the script from this clone. The script adds `src` to `sys.path`. The builder does not import the STEP kernel, so Revit's Python does not need `cadquery-ocp`.
3. In pyRevit, add the folder `revit/STEP2Revit.extension` as a custom extension and reload. The button is STEP2Revit, then Build, then Build Family.
4. The button asks for the schema-1 JSON file and the output `.rfa` path. It loads `Metric Generic Model.rft` from `%ProgramData%\Autodesk\RVT <year>\Family Templates\English\`. Set `STEP2REVIT_TEMPLATE` when that file lives somewhere else. `STEP2REVIT_JSON` and `STEP2REVIT_RFA` skip the file prompts.

The script creates one loadable Generic Model family, extrudes each cylinder, prism, and hole, and binds every JSON length to a type parameter. It does not read STEP and does not use the network. The comment at the top of `revit/STEP2Revit.extension/STEP2Revit.tab/Build.panel/BuildFamily.pushbutton/script.py` states the same limit.

## Tests

```bash
pytest
```

`ruff check src tests` runs the same lint check as CI. The geometry tests generate small solids in-process (box, cylinder, plate with a hole) and do not download STEP files. See [tests/NOTICE](tests/NOTICE).

## License

MIT. See [LICENSE](LICENSE).
