"""Schema-1 naming, profile frame, and document checks. No STEP files."""

from __future__ import annotations

import pytest

from step2revit.document import DocumentError, parameter_name, validate_neutral_document
from step2revit.geom import profile_axes

SHANK = {
    "schema_version": "1",
    "units": {"length": "mm"},
    "source": {
        "filename": "shank.step",
        "format": "STEP",
        "length_unit": "millimetre",
    },
    "bounding_box": {"min": [-5.0, -5.0, 0.0], "max": [5.0, 5.0, 40.0]},
    "extents": {"x": 10.0, "y": 10.0, "z": 40.0},
    "solids": [
        {
            "id": "shank",
            "bounding_box": {"min": [-5.0, -5.0, 0.0], "max": [5.0, 5.0, 40.0]},
        }
    ],
    "parameters": [
        {"name": "ShankDiameter", "value": 10.0, "unit": "mm", "kind": "length"},
        {"name": "ShankLength", "value": 40.0, "unit": "mm", "kind": "length"},
    ],
    "features": [
        {
            "id": "shank",
            "type": "cylinder",
            "solid_id": "shank",
            "origin": [0.0, 0.0, 0.0],
            "axis": [0.0, 0.0, 1.0],
            "diameter": {"parameter": "ShankDiameter"},
            "length": {"parameter": "ShankLength"},
        }
    ],
}


def test_profile_frame_matches_the_spec() -> None:
    along_z, up_z = profile_axes((0.0, 0.0, 1.0))
    assert along_z == (1.0, 0.0, 0.0)
    assert up_z == (0.0, 1.0, 0.0)

    along_negative_z, up_negative_z = profile_axes((0.0, 0.0, -1.0))
    assert along_negative_z == (1.0, 0.0, 0.0)
    assert up_negative_z == (0.0, -1.0, 0.0)

    along_x, up_x = profile_axes((1.0, 0.0, 0.0))
    assert along_x == (0.0, 1.0, 0.0)
    assert up_x == (0.0, 0.0, 1.0)


def test_parameter_names_follow_the_spec() -> None:
    used: set[str] = set()
    assert parameter_name("shank", "Diameter", used) == "ShankDiameter"
    assert parameter_name("shank", "Length", used) == "ShankLength"
    assert parameter_name("plate_hole", "Depth", used) == "PlateHoleDepth"
    assert parameter_name("hole_1", "Diameter", used) == "Hole1Diameter"
    assert parameter_name("hole_1", "Diameter", used) == "Hole1Diameter2"
    assert parameter_name("hole_1", "Diameter", used) == "Hole1Diameter3"


def test_worked_example_is_valid_schema_1() -> None:
    validate_neutral_document(SHANK)


def test_validator_rejects_a_broken_document() -> None:
    wrong_version = {**SHANK, "schema_version": "2"}
    with pytest.raises(DocumentError, match="schema_version"):
        validate_neutral_document(wrong_version)

    bad_extents = {
        **SHANK,
        "extents": {"x": 10.0, "y": 10.0, "z": 1.0},
    }
    with pytest.raises(DocumentError, match="extents.z"):
        validate_neutral_document(bad_extents)

    bad_feature = {
        **SHANK,
        "features": [
            {
                **SHANK["features"][0],
                "id": "shank",
                "type": "cone",
            }
        ],
    }
    with pytest.raises(DocumentError, match="shank"):
        validate_neutral_document(bad_feature)
    with pytest.raises(DocumentError, match="cone"):
        validate_neutral_document(bad_feature)
