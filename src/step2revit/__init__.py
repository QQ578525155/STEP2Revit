"""Convert STEP hardware parts into parametric Revit families.

``parse_step`` reads one STEP AP203, AP214, or AP242 part and writes the
schema-1 neutral document defined in
``.kiro/specs/step-to-rfa-pipeline/requirements.md``.
The Revit family builder is not part of this package.
"""

from step2revit.parse import StepParseError, parse_step

__all__ = ["StepParseError", "__version__", "parse_step"]

__version__ = "0.1.0"
