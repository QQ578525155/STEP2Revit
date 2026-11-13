---
inclusion: always
---

# Technology

## Packaging

- Python 3.11 or newer.
- The importable package is `step2revit`, using the `src` layout declared in `pyproject.toml`.
- Development tools are the `dev` extra: pytest and ruff.
- Install with `python -m pip install -e ".[dev]"`.

## Free and open source

Code, libraries, and automation added to this repository are free and open source. GitHub Actions in this repo are free GitHub-hosted actions. Paid APIs, paid converters, and proprietary geometry kernels are out of bounds.

Revit is the host application for the family builder. The repository does not redistribute Revit and does not call a paid Autodesk web service. The builder, when it is added, is a pyRevit or Revit API script that runs inside the user's Revit on Windows.

## Where the pipeline runs

- The parser is cross-platform Python and runs on Windows, macOS, and Linux. It depends on `cadquery-ocp` (OCP, Apache-2.0), which binds Open CASCADE. CI installs that wheel; parser tests stay headless and do not open a display. pythonOCC and CadQuery remain allowed alternatives and are not required.
- The family builder runs inside Revit on Windows. It reads the neutral JSON and does not read STEP.

## Checks

pytest in CI must not call the network. `.github/workflows/ci.yml` installs the package and runs ruff and pytest on push and pull_request.
