"""Convert STEP hardware parts into parametric Revit families.

``parse_step`` reads one STEP part and writes the schema-1 document.
``plan_family`` reads that document and plans a Generic Model family.
``build_family`` runs inside Revit on Windows and is the only call that
can write an ``.rfa``. Importing this package does not import the STEP
kernel or the Revit API.
"""

__all__ = [
    "FamilyBuildError",
    "FamilyPlan",
    "StepParseError",
    "__version__",
    "build_family",
    "load_neutral_document",
    "parse_step",
    "plan_family",
]

__version__ = "0.1.0"

_PARSE = frozenset({"StepParseError", "parse_step"})
_PLAN = frozenset(
    {
        "FamilyBuildError",
        "FamilyPlan",
        "load_neutral_document",
        "plan_family",
    }
)


def __getattr__(name: str):
    if name in _PARSE:
        from step2revit.parse import StepParseError, parse_step

        values = {"StepParseError": StepParseError, "parse_step": parse_step}
        globals().update(values)
        return values[name]
    if name in _PLAN:
        from step2revit.family_plan import (
            FamilyBuildError,
            FamilyPlan,
            load_neutral_document,
            plan_family,
        )

        values = {
            "FamilyBuildError": FamilyBuildError,
            "FamilyPlan": FamilyPlan,
            "load_neutral_document": load_neutral_document,
            "plan_family": plan_family,
        }
        globals().update(values)
        return values[name]
    if name == "build_family":
        from step2revit.revit_host import build_family

        globals()["build_family"] = build_family
        return build_family
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(__all__))
