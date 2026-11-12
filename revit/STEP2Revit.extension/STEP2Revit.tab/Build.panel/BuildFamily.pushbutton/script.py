# This script must run inside Revit on Windows (pyRevit, or Revit's Python
# shell on Revit 2025 or newer). Revit is not available in GitHub Actions or
# in this repository's cloud environment.
# Running this file outside Revit does not generate a .rfa.
"""Build one parametric Revit family from a schema-1 neutral JSON document.

The script loads Metric Generic Model.rft, extrudes each cylinder, prism, and
hole, and binds the JSON length parameters to family type parameters. It does
not read STEP and does not call a network service.

Set STEP2REVIT_JSON, STEP2REVIT_RFA, and optionally STEP2REVIT_TEMPLATE to
skip the file prompts. STEP2REVIT_TEMPLATE is the Metric Generic Model
template when it is not under %ProgramData%\\Autodesk.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _repo_src() -> Path | None:
    for parent in Path(__file__).resolve().parents:
        package = parent / "src" / "step2revit" / "__init__.py"
        if package.is_file():
            return parent / "src"
    return None


def _forms():
    try:
        from pyrevit import forms
    except ImportError:
        return None
    return forms


def _tell(message: str) -> None:
    forms = _forms()
    if forms is not None:
        try:
            forms.alert(message, title="STEP2Revit")
            return
        except Exception:
            pass
    print(message)


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _pick(forms, *, save: bool, extension: str, title: str) -> str | None:
    try:
        if save:
            picked = forms.save_file(file_ext=extension, title=title)
        else:
            picked = forms.pick_file(file_ext=extension, title=title)
    except TypeError:
        if save:
            picked = forms.save_file(file_ext=extension)
        else:
            picked = forms.pick_file(file_ext=extension)
    if not picked:
        return None
    return os.fspath(picked)


def _revit_application():
    revit = globals().get("__revit__")
    if revit is None:
        import __main__

        revit = getattr(__main__, "__revit__", None)
    return revit


def main() -> None:
    src = _repo_src()
    if src is not None and str(src) not in sys.path:
        sys.path.insert(0, str(src))
    try:
        from step2revit.family_plan import FamilyBuildError, resolve_template
        from step2revit.revit_host import build_family
    except ImportError:
        _tell(
            "step2revit is not importable. Install the package into Revit's "
            "Python, or run this script from the STEP2Revit repository."
        )
        return

    json_path = _env("STEP2REVIT_JSON")
    rfa_path = _env("STEP2REVIT_RFA")
    template = _env("STEP2REVIT_TEMPLATE")
    forms = _forms()
    if json_path is None and forms is not None:
        json_path = _pick(
            forms,
            save=False,
            extension="json",
            title="Schema-1 neutral JSON",
        )
    if rfa_path is None and forms is not None:
        rfa_path = _pick(forms, save=True, extension="rfa", title="Revit family")
    if not json_path or not rfa_path:
        _tell(
            "Choose a schema-1 JSON document and an .rfa path, "
            "or set STEP2REVIT_JSON and STEP2REVIT_RFA."
        )
        return
    if not rfa_path.lower().endswith(".rfa"):
        rfa_path = rfa_path + ".rfa"

    if template is None:
        program_data = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        try:
            template = resolve_template(None, program_data)
        except FamilyBuildError:
            template = None
            if forms is not None:
                template = _pick(
                    forms,
                    save=False,
                    extension="rft",
                    title="Metric Generic Model template",
                )
            if not template:
                _tell(
                    "Metric Generic Model.rft was not found. "
                    "Set STEP2REVIT_TEMPLATE to that family template."
                )
                return

    try:
        build_family(json_path, rfa_path, template, _revit_application())
    except FamilyBuildError as exc:
        _tell(str(exc))
        return
    _tell("Saved the family to " + rfa_path)


if __name__ == "__main__" or "__revit__" in globals():
    main()
