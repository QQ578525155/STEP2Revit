"""Assemble and check a schema-1 neutral document.

The field rules live in
``.kiro/specs/step-to-rfa-pipeline/requirements.md``. This module does not
read STEP and does not write a Revit family.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from typing import Any

from step2revit.geom import round_mm

_FEATURE_ID = re.compile(r"^[a-z][a-z0-9_]*$")
_PARAMETER_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
_MM_TOLERANCE = 0.001
_AXIS_TOLERANCE = 1e-6

_SIZE_SUFFIX = {
    "diameter": "Diameter",
    "length": "Length",
    "depth": "Depth",
}
_SIZE_FIELDS = {
    "cylinder": ("diameter", "length"),
    "hole": ("diameter", "depth"),
    "extrusion": ("length",),
}


class DocumentError(Exception):
    """A neutral document is missing a required field or contradicts itself."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def parameter_name(feature_id: str, suffix: str, used: set[str]) -> str:
    """Build a unique length-parameter name from a feature id.

    Split ``feature_id`` on ``_``, uppercase the first character of each
    segment, leave the rest unchanged, and append ``suffix`` (``Diameter``,
    ``Length``, or ``Depth``). If that name is taken, append ``2``, ``3``,
    and so on.
    """

    parts = [part[:1].upper() + part[1:] for part in feature_id.split("_")]
    base = "".join(parts) + suffix
    if _PARAMETER_NAME.fullmatch(base) is None:
        raise DocumentError(
            f"feature id {feature_id!r} does not produce a legal parameter name"
        )
    name = base
    number = 2
    while name in used:
        name = f"{base}{number}"
        number += 1
    used.add(name)
    return name


def assemble_document(
    *,
    filename: str,
    length_unit: str,
    solids: Sequence[Mapping[str, Any]],
    features: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Return a schema-1 document and check it before the caller writes it.

    ``solids`` entries need ``bounding_box``. ``features`` entries need
    ``type``, ``solid_index``, and the geometry of that type. Parameter
    names and feature ids are assigned here.
    """

    if not solids:
        raise DocumentError("no solids were found")
    if not features:
        raise DocumentError("no supported features were found")

    solid_records = []
    for index, solid in enumerate(solids, start=1):
        box = _rounded_box(solid["bounding_box"])
        solid_records.append({"id": f"solid_{index}", "bounding_box": box})

    used_names: set[str] = set()
    counts = {"cylinder": 0, "hole": 0, "extrusion": 0}
    parameters: list[dict[str, Any]] = []
    feature_records: list[dict[str, Any]] = []
    for raw in features:
        feature_type = raw["type"]
        if feature_type not in _SIZE_FIELDS:
            raise DocumentError(
                f"feature type {feature_type!r} is not cylinder, hole, or extrusion"
            )
        counts[feature_type] += 1
        feature_id = f"{feature_type}_{counts[feature_type]}"
        solid_index = raw["solid_index"]
        record: dict[str, Any] = {
            "id": feature_id,
            "type": feature_type,
            "solid_id": solid_records[solid_index]["id"],
            "origin": [round_mm(value) for value in raw["origin"]],
            "axis": [round(float(value), 8) or 0.0 for value in raw["axis"]],
        }
        for field in _SIZE_FIELDS[feature_type]:
            name = parameter_name(feature_id, _SIZE_SUFFIX[field], used_names)
            value = round_mm(raw[field])
            parameters.append(
                {"name": name, "value": value, "unit": "mm", "kind": "length"}
            )
            record[field] = {"parameter": name}
        if feature_type == "hole":
            record["through"] = bool(raw["through"])
        if feature_type == "extrusion":
            record["profile"] = [
                [round_mm(point[0]), round_mm(point[1])] for point in raw["profile"]
            ]
        feature_records.append(record)

    part_min = [
        min(solid["bounding_box"]["min"][axis] for solid in solid_records)
        for axis in range(3)
    ]
    part_max = [
        max(solid["bounding_box"]["max"][axis] for solid in solid_records)
        for axis in range(3)
    ]
    document = {
        "schema_version": "1",
        "units": {"length": "mm"},
        "source": {
            "filename": filename,
            "format": "STEP",
            "length_unit": length_unit,
        },
        "bounding_box": {"min": part_min, "max": part_max},
        "extents": {
            "x": round_mm(part_max[0] - part_min[0]),
            "y": round_mm(part_max[1] - part_min[1]),
            "z": round_mm(part_max[2] - part_min[2]),
        },
        "solids": solid_records,
        "parameters": parameters,
        "features": feature_records,
    }
    validate_neutral_document(document)
    return document


def validate_neutral_document(document: Mapping[str, Any]) -> None:
    """Raise ``DocumentError`` when ``document`` breaks the schema-1 contract.

    Unknown keys are ignored. A missing required field, a bad feature type,
    or a bounding box that disagrees with itself is an error.
    """

    if document.get("schema_version") != "1":
        raise DocumentError(
            f"schema_version {document.get('schema_version')!r} is not '1'"
        )
    units = _mapping(document, "units")
    if units.get("length") != "mm":
        raise DocumentError("units.length is not 'mm'")
    source = _mapping(document, "source")
    for key in ("filename", "format", "length_unit"):
        if not isinstance(source.get(key), str) or not source[key]:
            raise DocumentError(f"source.{key} is missing")
    if source["format"] != "STEP":
        raise DocumentError("source.format is not 'STEP'")

    part_box = _box(_mapping(document, "bounding_box"), "bounding_box")
    extents = _mapping(document, "extents")
    for index, axis_name in enumerate(("x", "y", "z")):
        size = _number(extents.get(axis_name), f"extents.{axis_name}")
        span = part_box["max"][index] - part_box["min"][index]
        if abs(size - span) > _MM_TOLERANCE:
            raise DocumentError(
                f"extents.{axis_name} does not match the part bounding box"
            )

    solids = _list(document, "solids")
    if not solids:
        raise DocumentError("solids is empty")
    solid_ids: set[str] = set()
    union_min = [math.inf, math.inf, math.inf]
    union_max = [-math.inf, -math.inf, -math.inf]
    for solid in solids:
        record = _mapping_value(solid, "solid")
        solid_id = record.get("id")
        if not isinstance(solid_id, str) or not solid_id or solid_id in solid_ids:
            raise DocumentError(f"solid id {solid_id!r} is missing or duplicated")
        solid_ids.add(solid_id)
        box = _box(_mapping_value(record.get("bounding_box"), "bounding_box"), solid_id)
        for index in range(3):
            union_min[index] = min(union_min[index], box["min"][index])
            union_max[index] = max(union_max[index], box["max"][index])
            if box["min"][index] < part_box["min"][index] - _MM_TOLERANCE:
                raise DocumentError(f"solid {solid_id} extends outside the part")
            if box["max"][index] > part_box["max"][index] + _MM_TOLERANCE:
                raise DocumentError(f"solid {solid_id} extends outside the part")
    for index in range(3):
        if abs(union_min[index] - part_box["min"][index]) > _MM_TOLERANCE:
            raise DocumentError("part bounding box is not the union of the solids")
        if abs(union_max[index] - part_box["max"][index]) > _MM_TOLERANCE:
            raise DocumentError("part bounding box is not the union of the solids")

    parameters = _list(document, "parameters")
    names: set[str] = set()
    for parameter in parameters:
        record = _mapping_value(parameter, "parameter")
        name = record.get("name")
        if not isinstance(name, str) or _PARAMETER_NAME.fullmatch(name) is None:
            raise DocumentError(f"parameter name {name!r} is not legal")
        if name in names:
            raise DocumentError(f"parameter name {name!r} is duplicated")
        names.add(name)
        _number(record.get("value"), f"parameter {name} value")
        if record.get("unit") != "mm" or record.get("kind") != "length":
            raise DocumentError(f"parameter {name} is not a length in mm")

    features = _list(document, "features")
    if not features:
        raise DocumentError("features is empty")
    feature_ids: set[str] = set()
    for feature in features:
        _check_feature(feature, solid_ids, names, feature_ids)


def _check_feature(
    feature: Any,
    solid_ids: set[str],
    parameter_names: set[str],
    feature_ids: set[str],
) -> None:
    record = _mapping_value(feature, "feature")
    feature_id = record.get("id")
    feature_type = record.get("type")
    if not isinstance(feature_id, str) or _FEATURE_ID.fullmatch(feature_id) is None:
        raise DocumentError(f"feature id {feature_id!r} is not legal")
    if feature_id in feature_ids:
        raise DocumentError(f"feature id {feature_id!r} is duplicated")
    feature_ids.add(feature_id)
    if feature_type not in _SIZE_FIELDS:
        raise DocumentError(
            f"feature {feature_id} has type {feature_type!r}, "
            "not cylinder, hole, or extrusion"
        )
    solid_id = record.get("solid_id")
    if solid_id not in solid_ids:
        raise DocumentError(f"feature {feature_id} solid_id {solid_id!r} is unknown")
    _point(record.get("origin"), f"feature {feature_id} origin")
    axis = _point(record.get("axis"), f"feature {feature_id} axis")
    if abs(math.sqrt(sum(component * component for component in axis)) - 1.0) > (
        _AXIS_TOLERANCE
    ):
        raise DocumentError(f"feature {feature_id} axis is not a unit vector")
    for field in _SIZE_FIELDS[feature_type]:
        _parameter_ref(
            record.get(field),
            parameter_names,
            f"feature {feature_id} {field}",
        )
    if feature_type == "hole" and not isinstance(record.get("through"), bool):
        raise DocumentError(f"feature {feature_id} through is not a boolean")
    if feature_type == "extrusion":
        profile = record.get("profile")
        if not isinstance(profile, list) or len(profile) < 3:
            raise DocumentError(f"feature {feature_id} profile needs at least 3 points")
        for point in profile:
            if not isinstance(point, list) or len(point) != 2:
                raise DocumentError(f"feature {feature_id} profile point is not [u, v]")
            for item in point:
                if isinstance(item, bool) or not isinstance(item, (int, float)):
                    raise DocumentError(
                        f"feature {feature_id} profile point is not [u, v]"
                    )


def _parameter_ref(value: Any, names: set[str], label: str) -> None:
    if not isinstance(value, Mapping) or not isinstance(value.get("parameter"), str):
        raise DocumentError(f"{label} is not a parameter reference")
    if value["parameter"] not in names:
        raise DocumentError(f"{label} names an unknown parameter")


def _rounded_box(box: Mapping[str, Any]) -> dict[str, list[float]]:
    return {
        "min": [round_mm(value) for value in box["min"]],
        "max": [round_mm(value) for value in box["max"]],
    }


def _box(box: Mapping[str, Any], label: str) -> dict[str, list[float]]:
    return {
        "min": _point(box.get("min"), f"{label}.min"),
        "max": _point(box.get("max"), f"{label}.max"),
    }


def _point(value: Any, label: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise DocumentError(f"{label} is not a point")
    return [_number(component, label) for component in value]


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise DocumentError(f"{label} is not a number")
    number = float(value)
    if not math.isfinite(number):
        raise DocumentError(f"{label} is not finite")
    return number


def _mapping(document: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = document.get(key)
    if not isinstance(value, Mapping):
        raise DocumentError(f"{key} is missing")
    return value


def _mapping_value(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise DocumentError(f"{label} is missing")
    return value


def _list(document: Mapping[str, Any], key: str) -> list[Any]:
    value = document.get(key)
    if not isinstance(value, list):
        raise DocumentError(f"{key} is missing")
    return value
