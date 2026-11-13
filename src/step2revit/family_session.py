"""Apply a family plan through a session boundary.

The session protocol is the line between the pure plan and Revit. This module
does not import the Revit API. Tests pass a recording session. ``revit_host``
passes a session that calls Revit, and only from inside Revit on Windows.
Curve coordinates handed to the session are Revit internal feet.
"""

from __future__ import annotations

from typing import Protocol

from step2revit.family_plan import (
    FamilyPlan,
    SketchArc,
    SketchLine,
    mm_to_feet,
)


class FamilySession(Protocol):
    """The calls that create one loadable family. Units are internal feet."""

    def open_template(self, template_path: str) -> None:
        """Open the Generic Model family template. Do not save it."""

    def add_type_length_parameter(self, name: str, value_feet: float) -> None:
        """Add one type length on the template's current type and set its value."""

    def add_extrusion(
        self,
        *,
        feature_id: str,
        solid: bool,
        origin_feet: tuple[float, float, float],
        axis: tuple[float, float, float],
        plane_x: tuple[float, float, float],
        plane_y: tuple[float, float, float],
        curves: tuple[tuple, ...],
        length_feet: float,
        length_parameter: str,
        diameter_parameter: str | None,
    ) -> None:
        """Create one extrusion and bind it to the named type parameters.

        ``curves`` entries are ``("line", start_feet, end_feet)`` or
        ``("arc", center_feet, x_axis, y_axis, normal, radius_feet,
        start_angle, end_angle)``. ``solid`` is false for a hole.
        """

    def save(self, output_path: str) -> None:
        """Write the family to ``output_path``."""

    def close_without_saving(self) -> None:
        """Drop the open family. Must be safe when nothing is open."""


def execute_plan(
    plan: FamilyPlan,
    session: FamilySession,
    *,
    template_path: str,
    output_path: str,
) -> None:
    """Run ``plan`` against ``session``.

    Any failure closes the session without saving, including a failure while
    opening the template, and the exception propagates. ``save`` runs only
    after every parameter and extrusion call returns.
    """

    try:
        session.open_template(template_path)
        for parameter in plan.parameters:
            session.add_type_length_parameter(parameter.name, parameter.value_feet)
        for extrusion in plan.extrusions:
            session.add_extrusion(
                feature_id=extrusion.feature_id,
                solid=extrusion.solid,
                origin_feet=_feet(extrusion.origin_mm),
                axis=extrusion.axis,
                plane_x=extrusion.plane_x,
                plane_y=extrusion.plane_y,
                curves=tuple(_curve_feet(curve) for curve in extrusion.curves),
                length_feet=mm_to_feet(extrusion.length_mm),
                length_parameter=extrusion.length_parameter,
                diameter_parameter=extrusion.diameter_parameter,
            )
        session.save(output_path)
    except Exception:
        session.close_without_saving()
        raise


def _curve_feet(curve: SketchLine | SketchArc) -> tuple:
    if isinstance(curve, SketchLine):
        return ("line", _feet(curve.start_mm), _feet(curve.end_mm))
    return (
        "arc",
        _feet(curve.center_mm),
        curve.x_axis,
        curve.y_axis,
        curve.normal,
        mm_to_feet(curve.radius_mm),
        curve.start_angle,
        curve.end_angle,
    )


def _feet(point: tuple[float, float, float]) -> tuple[float, float, float]:
    return (mm_to_feet(point[0]), mm_to_feet(point[1]), mm_to_feet(point[2]))
