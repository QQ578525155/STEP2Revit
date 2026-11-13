"""Plan a parametric Revit family from a schema-1 neutral document.

This module does not import the STEP kernel or the Revit API. It checks the
document, chooses the Generic Model template, and turns each feature into an
extrusion sketch plus the length parameters that drive it. ``revit_host`` is
the only module that calls Revit, and only when that call runs inside Revit
on Windows.
"""

from __future__ import annotations

import json
import math
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from step2revit.document import DocumentError, validate_neutral_document
from step2revit.geom import add, cross, dist, profile_axes, scale, signed_area

# Revit internal length is the international foot. 304.8 mm, not the US survey foot.
MM_PER_FOOT = 304.8
GENERIC_MODEL_TEMPLATE_NAME = "Metric Generic Model.rft"
GENERIC_MODEL_CATEGORY = "Generic Model"

_TEMPLATE_VERSIONS = ("2027", "2026", "2025", "2024", "2023", "2022", "2021")
_TEMPLATE_LANGUAGES = ("English", "English-US", "English_I")


class FamilyBuildError(Exception):
    """The family was not written. The message names the path and the reason."""

    def __init__(self, path: str, reason: str) -> None:
        self.path = path
        self.reason = reason
        message = f"{path}: {reason}" if path else reason
        super().__init__(message)


@dataclass(frozen=True)
class LengthParameter:
    """One family type length, in millimetres and in Revit internal feet."""

    name: str
    value_mm: float
    value_feet: float


@dataclass(frozen=True)
class SketchLine:
    """A profile edge. Coordinates are millimetres on the family axes."""

    start_mm: tuple[float, float, float]
    end_mm: tuple[float, float, float]


@dataclass(frozen=True)
class SketchArc:
    """A semicircle on the sketch plane. Angles are radians from ``x_axis``."""

    center_mm: tuple[float, float, float]
    x_axis: tuple[float, float, float]
    y_axis: tuple[float, float, float]
    normal: tuple[float, float, float]
    radius_mm: float
    start_angle: float
    end_angle: float


@dataclass(frozen=True)
class PlannedExtrusion:
    """One solid or void extrusion the host creates in the family.

    ``length_parameter`` drives the extrusion distance. ``diameter_parameter``
    drives the circle when the feature is a cylinder or a hole. Profile
    coordinates of a prism stay literal numbers, matching schema 1.
    """

    feature_id: str
    feature_type: str
    solid: bool
    origin_mm: tuple[float, float, float]
    axis: tuple[float, float, float]
    plane_x: tuple[float, float, float]
    plane_y: tuple[float, float, float]
    length_mm: float
    length_parameter: str
    curves: tuple[SketchLine | SketchArc, ...]
    diameter_mm: float | None
    diameter_parameter: str | None
    through: bool | None


@dataclass(frozen=True)
class FamilyPlan:
    """Everything the host needs, with no Revit types in it.

    ``in_place`` is false: the host opens a family template and saves a
    loadable ``.rfa``. Solids are listed before voids so a hole cuts the
    body that was created first.
    """

    template_name: str
    category: str
    in_place: bool
    parameters: tuple[LengthParameter, ...]
    extrusions: tuple[PlannedExtrusion, ...]


def mm_to_feet(millimetres: float) -> float:
    """Convert a schema-1 millimetre length to Revit internal feet."""

    return millimetres / MM_PER_FOOT


def template_candidates(program_data: str | Path) -> tuple[str, ...]:
    """Return Metric Generic Model template paths under ``program_data``.

    Revit installs the English template at
    ``Autodesk/RVT <year>/Family Templates/<language>/Metric Generic Model.rft``.
    Localized template file names are not guessed; pass an explicit path for those.
    """

    root = Path(program_data)
    paths = []
    for version in _TEMPLATE_VERSIONS:
        for language in _TEMPLATE_LANGUAGES:
            paths.append(
                root
                / f"Autodesk/RVT {version}"
                / "Family Templates"
                / language
                / GENERIC_MODEL_TEMPLATE_NAME
            )
    return tuple(os.fspath(path) for path in paths)


def resolve_template(
    explicit: str | None,
    program_data: str | Path,
) -> str:
    """Return the template file to open, or raise ``FamilyBuildError``."""

    if explicit:
        if not os.path.isfile(explicit):
            raise FamilyBuildError(explicit, "family template was not found")
        return explicit
    for candidate in template_candidates(program_data):
        if os.path.isfile(candidate):
            return candidate
    raise FamilyBuildError(
        GENERIC_MODEL_TEMPLATE_NAME,
        "Metric Generic Model.rft was not found. "
        "Set STEP2REVIT_TEMPLATE to the family template.",
    )


def load_neutral_document(path: str | Path) -> dict[str, Any]:
    """Read one schema-1 document. Failures name ``path`` and write nothing."""

    document_path = os.fspath(path)
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        reason = exc.strerror or "unreadable"
        raise FamilyBuildError(
            document_path, f"cannot read the document ({reason})"
        ) from exc
    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        raise FamilyBuildError(document_path, f"is not JSON ({exc.msg})") from exc
    if not isinstance(document, dict):
        raise FamilyBuildError(document_path, "the document is not a JSON object")
    _require_valid(document, document_path)
    return document


def plan_family(
    document: Mapping[str, Any],
    *,
    document_path: str = "<document>",
) -> FamilyPlan:
    """Map a schema-1 document onto template, sketches, and type parameters.

    Unknown JSON keys are ignored. A missing field, a bad version, or a
    feature type other than cylinder, hole, or extrusion raises
    ``FamilyBuildError`` and does not produce a plan the host can save.
    """

    _require_valid(document, document_path)
    parameters = tuple(
        LengthParameter(
            name=item["name"],
            value_mm=float(item["value"]),
            value_feet=mm_to_feet(float(item["value"])),
        )
        for item in document["parameters"]
    )
    values = {item.name: item.value_mm for item in parameters}
    solids: list[PlannedExtrusion] = []
    voids: list[PlannedExtrusion] = []
    for feature in document["features"]:
        planned = _plan_feature(feature, values, document_path)
        if planned.solid:
            solids.append(planned)
        else:
            voids.append(planned)
    return FamilyPlan(
        template_name=GENERIC_MODEL_TEMPLATE_NAME,
        category=GENERIC_MODEL_CATEGORY,
        in_place=False,
        parameters=parameters,
        extrusions=tuple([*solids, *voids]),
    )


def with_parameter_values(
    plan: FamilyPlan,
    values: Mapping[str, float],
) -> FamilyPlan:
    """Return a plan whose named lengths use new millimetre values.

    Extrusion distances and circle radii that reference those parameters
    change with them. This is the headless stand-in for a Revit type edit.
    """

    known = {item.name for item in plan.parameters}
    unknown = [name for name in values if name not in known]
    if unknown:
        raise FamilyBuildError("", f"unknown parameter {unknown[0]}")
    updated: list[LengthParameter] = []
    lookup: dict[str, float] = {}
    for item in plan.parameters:
        if item.name in values:
            value = float(values[item.name])
            if value <= 0 or not math.isfinite(value):
                raise FamilyBuildError("", f"parameter {item.name} is not positive")
            item = replace(item, value_mm=value, value_feet=mm_to_feet(value))
        updated.append(item)
        lookup[item.name] = item.value_mm
    extrusions = tuple(_resized(item, lookup) for item in plan.extrusions)
    return replace(plan, parameters=tuple(updated), extrusions=extrusions)


def planned_bounding_box(plan: FamilyPlan) -> dict[str, list[float]] | None:
    """Axis-aligned box of the solid extrusions, in millimetres.

    Voids do not add material, so holes do not grow the box. Returns ``None``
    when the plan has no solid feature.
    """

    solids = [item for item in plan.extrusions if item.solid]
    if not solids:
        return None
    mins = [math.inf, math.inf, math.inf]
    maxs = [-math.inf, -math.inf, -math.inf]
    for extrusion in solids:
        box_min, box_max = _solid_corners(extrusion)
        for index in range(3):
            mins[index] = min(mins[index], box_min[index])
            maxs[index] = max(maxs[index], box_max[index])
    return {"min": mins, "max": maxs}


def _require_valid(document: Mapping[str, Any], document_path: str) -> None:
    try:
        validate_neutral_document(document)
    except DocumentError as exc:
        raise FamilyBuildError(document_path, exc.reason) from exc


def _plan_feature(
    feature: Mapping[str, Any],
    values: Mapping[str, float],
    document_path: str,
) -> PlannedExtrusion:
    feature_id = str(feature["id"])
    feature_type = str(feature["type"])
    origin = _xyz(feature["origin"])
    plane_x, plane_y = profile_axes(feature["axis"])
    normal = cross(plane_x, plane_y)
    if feature_type == "extrusion":
        length_name = str(feature["length"]["parameter"])
        length = _positive(values[length_name], document_path, feature_id, "length")
        curves = _profile_lines(
            feature["profile"],
            origin,
            plane_x,
            plane_y,
            document_path,
            feature_id,
        )
        return PlannedExtrusion(
            feature_id=feature_id,
            feature_type=feature_type,
            solid=True,
            origin_mm=origin,
            axis=normal,
            plane_x=plane_x,
            plane_y=plane_y,
            length_mm=length,
            length_parameter=length_name,
            curves=curves,
            diameter_mm=None,
            diameter_parameter=None,
            through=None,
        )

    diameter_name = str(feature["diameter"]["parameter"])
    if feature_type == "cylinder":
        length_name = str(feature["length"]["parameter"])
        length_field = "length"
        solid = True
        through = None
    else:
        length_name = str(feature["depth"]["parameter"])
        length_field = "depth"
        solid = False
        through = bool(feature["through"])
    diameter = _positive(values[diameter_name], document_path, feature_id, "diameter")
    length = _positive(values[length_name], document_path, feature_id, length_field)
    return PlannedExtrusion(
        feature_id=feature_id,
        feature_type=feature_type,
        solid=solid,
        origin_mm=origin,
        axis=normal,
        plane_x=plane_x,
        plane_y=plane_y,
        length_mm=length,
        length_parameter=length_name,
        curves=_circle(origin, plane_x, plane_y, normal, diameter / 2.0),
        diameter_mm=diameter,
        diameter_parameter=diameter_name,
        through=through,
    )


def _circle(
    origin: tuple[float, float, float],
    plane_x: tuple[float, float, float],
    plane_y: tuple[float, float, float],
    normal: tuple[float, float, float],
    radius: float,
) -> tuple[SketchArc, SketchArc]:
    # Two semicircles. A single arc from 0 to 2π has the same start and end,
    # which the Revit curve constructor rejects.
    return (
        SketchArc(origin, plane_x, plane_y, normal, radius, 0.0, math.pi),
        SketchArc(origin, plane_x, plane_y, normal, radius, math.pi, 2.0 * math.pi),
    )


def _profile_lines(
    profile: Sequence[Sequence[float]],
    origin: tuple[float, float, float],
    plane_x: tuple[float, float, float],
    plane_y: tuple[float, float, float],
    document_path: str,
    feature_id: str,
) -> tuple[SketchLine, ...]:
    points = [(float(point[0]), float(point[1])) for point in profile]
    if len(points) >= 2 and points[0] == points[-1]:
        points = points[:-1]
    area = signed_area(points)
    if abs(area) < 1e-8:
        raise FamilyBuildError(
            document_path,
            f"feature {feature_id} profile is degenerate",
        )
    if area < 0:
        points.reverse()
    world = [
        _placed(origin, plane_x, plane_y, u_coord, v_coord)
        for u_coord, v_coord in points
    ]
    lines: list[SketchLine] = []
    for index, start in enumerate(world):
        end = world[(index + 1) % len(world)]
        if dist(start, end) <= 1e-9:
            continue
        lines.append(SketchLine(start, end))
    if len(lines) < 3:
        raise FamilyBuildError(
            document_path,
            f"feature {feature_id} profile needs at least 3 points",
        )
    return tuple(lines)


def _placed(
    origin: tuple[float, float, float],
    plane_x: tuple[float, float, float],
    plane_y: tuple[float, float, float],
    u_coord: float,
    v_coord: float,
) -> tuple[float, float, float]:
    return add(origin, add(scale(plane_x, u_coord), scale(plane_y, v_coord)))


def _resized(
    extrusion: PlannedExtrusion,
    lookup: Mapping[str, float],
) -> PlannedExtrusion:
    length = lookup[extrusion.length_parameter]
    diameter = (
        None
        if extrusion.diameter_parameter is None
        else lookup[extrusion.diameter_parameter]
    )
    curves: tuple[SketchLine | SketchArc, ...] = extrusion.curves
    if diameter is not None:
        radius = diameter / 2.0
        curves = tuple(
            replace(curve, radius_mm=radius) if isinstance(curve, SketchArc) else curve
            for curve in curves
        )
    return replace(
        extrusion,
        length_mm=length,
        diameter_mm=diameter,
        curves=curves,
    )


def _solid_corners(
    extrusion: PlannedExtrusion,
) -> tuple[list[float], list[float]]:
    if extrusion.diameter_mm is not None:
        return _round_box(
            extrusion.origin_mm,
            extrusion.axis,
            extrusion.diameter_mm / 2.0,
            extrusion.length_mm,
        )
    starts = [
        curve.start_mm
        for curve in extrusion.curves
        if isinstance(curve, SketchLine)
    ]
    ends = [
        tuple(
            start[index] + extrusion.length_mm * extrusion.axis[index]
            for index in range(3)
        )
        for start in starts
    ]
    points = [*starts, *ends]
    mins = [min(point[index] for point in points) for index in range(3)]
    maxs = [max(point[index] for point in points) for index in range(3)]
    return mins, maxs


def _round_box(
    origin: tuple[float, float, float],
    axis: tuple[float, float, float],
    radius: float,
    length: float,
) -> tuple[list[float], list[float]]:
    end = tuple(origin[index] + length * axis[index] for index in range(3))
    mins: list[float] = []
    maxs: list[float] = []
    for index in range(3):
        radial = radius * math.sqrt(max(0.0, 1.0 - axis[index] * axis[index]))
        mins.append(min(origin[index], end[index]) - radial)
        maxs.append(max(origin[index], end[index]) + radial)
    return mins, maxs


def _positive(
    value: float,
    document_path: str,
    feature_id: str,
    field: str,
) -> float:
    if value <= 0 or not math.isfinite(value):
        raise FamilyBuildError(
            document_path,
            f"feature {feature_id} {field} is not positive",
        )
    return value


def _xyz(values: Sequence[Any]) -> tuple[float, float, float]:
    return (float(values[0]), float(values[1]), float(values[2]))
