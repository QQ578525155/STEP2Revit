"""Pure geometry helpers for the schema-1 profile frame.

The frame rules are copied from
``.kiro/specs/step-to-rfa-pipeline/requirements.md``. Lengths are millimetres.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

MM_DECIMALS = 6
AXIS_DECIMALS = 8
PARALLEL_COMPONENT = 1e-8


def dot(a: Sequence[float], b: Sequence[float]) -> float:
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def cross(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (
        a[1] * b[2] - a[2] * b[1],
        a[2] * b[0] - a[0] * b[2],
        a[0] * b[1] - a[1] * b[0],
    )


def sub(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def add(a: Sequence[float], b: Sequence[float]) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def scale(a: Sequence[float], factor: float) -> tuple[float, float, float]:
    return (a[0] * factor, a[1] * factor, a[2] * factor)


def length(vector: Sequence[float]) -> float:
    return math.sqrt(dot(vector, vector))


def dist(a: Sequence[float], b: Sequence[float]) -> float:
    return length(sub(a, b))


def normalize(vector: Sequence[float]) -> tuple[float, float, float]:
    magnitude = length(vector)
    if magnitude < 1e-12:
        raise ValueError("cannot normalize a zero vector")
    return (vector[0] / magnitude, vector[1] / magnitude, vector[2] / magnitude)


def orient_positive(vector: Sequence[float]) -> tuple[float, float, float]:
    """Flip a unit-ish vector so its largest component is non-negative.

    Ties prefer Z, then Y, then X, matching the parser's stable axis choice.
    """

    unit = normalize(vector)
    index = max(range(3), key=lambda axis: (abs(unit[axis]), axis))
    if unit[index] < 0:
        return (-unit[0], -unit[1], -unit[2])
    return unit


def round_mm(value: float) -> float:
    rounded = round(float(value), MM_DECIMALS)
    if rounded == 0:
        return 0.0
    return rounded


def round_point(point: Sequence[float]) -> list[float]:
    return [round_mm(component) for component in point]


def round_axis(vector: Sequence[float]) -> list[float]:
    unit = normalize(vector)
    rounded = []
    for component in unit:
        value = round(component, AXIS_DECIMALS)
        rounded.append(0.0 if value == 0 else value)
    return rounded


def profile_axes(
    axis: Sequence[float],
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    """Return ``(U, V)`` for an extrusion axis, as the neutral document defines.

    A profile point ``(u, v)`` is the world point ``origin + u * U + v * V``.
    """

    unit = normalize(axis)
    if abs(unit[0]) <= PARALLEL_COMPONENT and abs(unit[1]) <= PARALLEL_COMPONENT:
        profile_u = (1.0, 0.0, 0.0)
        profile_v = (0.0, 1.0, 0.0) if unit[2] >= 0 else (0.0, -1.0, 0.0)
        return profile_u, profile_v
    profile_u = normalize(cross((0.0, 0.0, 1.0), unit))
    profile_v = cross(unit, profile_u)
    return profile_u, profile_v


def signed_area(points: Sequence[Sequence[float]]) -> float:
    area = 0.0
    count = len(points)
    for index in range(count):
        u_1, v_1 = points[index]
        u_2, v_2 = points[(index + 1) % count]
        area += u_1 * v_2 - u_2 * v_1
    return 0.5 * area


def area_centroid(points: Sequence[Sequence[float]]) -> tuple[float, float]:
    """Centroid of a simple polygon. ``points`` are not repeated at the end."""

    area = signed_area(points)
    if abs(area) < 1e-12:
        count = float(len(points))
        return (
            sum(point[0] for point in points) / count,
            sum(point[1] for point in points) / count,
        )
    centroid_u = 0.0
    centroid_v = 0.0
    count = len(points)
    for index in range(count):
        u_1, v_1 = points[index]
        u_2, v_2 = points[(index + 1) % count]
        cross_z = u_1 * v_2 - u_2 * v_1
        centroid_u += (u_1 + u_2) * cross_z
        centroid_v += (v_1 + v_2) * cross_z
    centroid_u /= 6.0 * area
    centroid_v /= 6.0 * area
    return centroid_u, centroid_v
