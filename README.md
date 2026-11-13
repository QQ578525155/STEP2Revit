# STEP2Revit

STEP2Revit converts STEP and SolidWorks hardware parts — bolts, brackets, and fittings — into parametric Revit families (`.rfa`). It is free and open source, built for the Devpost Kiroween 2026 hackathon (Frankenstein category).

The pipeline is STEP in, a neutral JSON description (solids, bounding dimensions, key features and parameters), then a parametric `.rfa`. Parsing and family generation are not in this scaffold. The contract for later work is [`.kiro/specs/step-to-rfa-pipeline/requirements.md`](.kiro/specs/step-to-rfa-pipeline/requirements.md).

## Install

Python 3.11 or newer. From the repository root:

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

The `[dev]` extra installs pytest and ruff.

## Tests

```bash
pytest
```

`ruff check src tests` runs the same lint check as CI.

## License

MIT. See [LICENSE](LICENSE).
