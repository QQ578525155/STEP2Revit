"""Recognize cylinders, holes, and right-prism extrusions on one solid.

The rules are the ones recorded in
``.kiro/specs/step-to-rfa-pipeline/design.md``. A face is a hole when the
material lies outside its cylindrical radius, and a boss when the material
lies inside. That test uses the solid classifier rather than a file's face
orientation, which STEP writers do not agree on.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Curve, BRepAdaptor_Surface
from OCP.BRepClass3d import BRepClass3d_SolidClassifier
from OCP.BRepTools import BRepTools, BRepTools_WireExplorer
from OCP.GeomAbs import GeomAbs_Circle, GeomAbs_Cylinder, GeomAbs_Line, GeomAbs_Plane
from OCP.gp import gp_Pnt
from OCP.TopAbs import (
    TopAbs_FACE,
    TopAbs_IN,
    TopAbs_OUT,
    TopAbs_REVERSED,
    TopAbs_VERTEX,
)
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from step2revit.geom import (
    add,
    area_centroid,
    cross,
    dist,
    dot,
    normalize,
    orient_positive,
    profile_axes,
    round_axis,
    scale,
    signed_area,
    sub,
)

_ANGLE = 1e-6
_DISTANCE = 1e-3
_RADIUS = 1e-4
_FULL_TURN = 1e-2
_MIN_SPAN = 1e-4


def recognize_solid(solid: Any) -> list[dict[str, Any]]:
    """Return body and hole features for ``solid``, without ids.

    Each feature dict has ``type`` and the geometric fields the document
    assembler turns into parameters. ``solid_index`` is filled in by the caller.
    """

    faces = _collect_faces(solid)
    cylindrical = [face for face in faces if face["kind"] == "cylinder"]
    holes = []
    externals = []
    for cluster in _cluster(cylindrical):
        kind = _material_inside(solid, cluster)
        if kind == "hole":
            holes.append(cluster)
        elif kind == "external":
            externals.append(cluster)
    hole_face_ids = {id(face) for cluster in holes for face in cluster["faces"]}

    body = _cylinder_body(faces, externals, hole_face_ids)
    if body is None:
        body = _extrusion_body(faces, hole_face_ids)
    features: list[dict[str, Any]] = []
    if body is not None:
        features.append(body)
    hole_features = []
    for cluster in holes:
        feature = _hole_feature(cluster, faces)
        if feature is not None:
            hole_features.append(feature)
    hole_features.sort(key=lambda feature: (*feature["origin"], feature["diameter"]))
    features.extend(hole_features)
    return features


def _collect_faces(solid: Any) -> list[dict[str, Any]]:
    faces = []
    explorer = TopExp_Explorer(solid, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face_s(explorer.Current())
        record = _describe_face(face)
        if record is not None:
            faces.append(record)
        explorer.Next()
    return faces


def _describe_face(face: Any) -> dict[str, Any] | None:
    adaptor = BRepAdaptor_Surface(face)
    kind = adaptor.GetType()
    if kind == GeomAbs_Plane:
        direction = adaptor.Plane().Axis().Direction()
        geometric = (direction.X(), direction.Y(), direction.Z())
        if face.Orientation() == TopAbs_REVERSED:
            outward = scale(geometric, -1.0)
        else:
            outward = geometric
        location = adaptor.Plane().Location()
        return {
            "shape": face,
            "kind": "plane",
            "outward": normalize(outward),
            "point": (location.X(), location.Y(), location.Z()),
        }
    if kind == GeomAbs_Cylinder:
        cylinder = adaptor.Cylinder()
        direction = cylinder.Axis().Direction()
        location = cylinder.Axis().Location()
        axis = normalize((direction.X(), direction.Y(), direction.Z()))
        origin = (location.X(), location.Y(), location.Z())
        span = abs(adaptor.LastUParameter() - adaptor.FirstUParameter())
        return {
            "shape": face,
            "kind": "cylinder",
            "axis": axis,
            "origin": origin,
            "radius": cylinder.Radius(),
            "span": span,
            "extent": _axial_extent(face, origin, axis),
        }
    return {"shape": face, "kind": "other"}


def _axial_extent(
    face: Any, origin: Sequence[float], axis: Sequence[float]
) -> tuple[float, float]:
    explorer = TopExp_Explorer(face, TopAbs_VERTEX)
    parameters: list[float] = []
    while explorer.More():
        point = BRep_Tool.Pnt_s(TopoDS.Vertex_s(explorer.Current()))
        parameters.append(
            dot(sub((point.X(), point.Y(), point.Z()), origin), axis)
        )
        explorer.Next()
    if parameters:
        return min(parameters), max(parameters)
    adaptor = BRepAdaptor_Surface(face)
    return adaptor.FirstVParameter(), adaptor.LastVParameter()


def _cluster(faces: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for face in faces:
        span = face["extent"][1] - face["extent"][0]
        if face["radius"] <= _RADIUS or span <= _MIN_SPAN:
            continue
        for cluster in clusters:
            if _same_cylinder(cluster, face):
                projected = _axial_extent(
                    face["shape"], cluster["origin"], cluster["axis"]
                )
                cluster["faces"].append(face)
                cluster["span"] += face["span"]
                cluster["extent"] = (
                    min(cluster["extent"][0], projected[0]),
                    max(cluster["extent"][1], projected[1]),
                )
                break
        else:
            clusters.append(
                {
                    "faces": [face],
                    "axis": face["axis"],
                    "origin": face["origin"],
                    "radius": face["radius"],
                    "span": face["span"],
                    "extent": face["extent"],
                }
            )
    return [cluster for cluster in clusters if _full_turn(cluster["span"])]


def _same_cylinder(cluster: dict[str, Any], face: dict[str, Any]) -> bool:
    if abs(face["radius"] - cluster["radius"]) > _RADIUS:
        return False
    if abs(abs(dot(face["axis"], cluster["axis"])) - 1.0) > _ANGLE:
        return False
    gap = cross(cluster["axis"], sub(face["origin"], cluster["origin"]))
    return math.sqrt(dot(gap, gap)) <= _DISTANCE


def _full_turn(span: float) -> bool:
    return abs(span - 2.0 * math.pi) <= _FULL_TURN


def _point_on_axis(
    cluster: dict[str, Any], parameter: float
) -> tuple[float, float, float]:
    return add(cluster["origin"], scale(cluster["axis"], parameter))


def _radial(axis: Sequence[float]) -> tuple[float, float, float]:
    helper = (1.0, 0.0, 0.0) if abs(axis[0]) < 0.9 else (0.0, 1.0, 0.0)
    return normalize(cross(axis, helper))


def _material_inside(solid: Any, cluster: dict[str, Any]) -> str | None:
    """Return ``hole`` or ``external`` from which side of the radius is material."""

    mid = (cluster["extent"][0] + cluster["extent"][1]) / 2.0
    center = _point_on_axis(cluster, mid)
    radial = _radial(cluster["axis"])
    inner = add(center, scale(radial, cluster["radius"] * 0.5))
    outer = add(center, scale(radial, cluster["radius"] * 1.5))
    inner_state = _classify(solid, inner)
    outer_state = _classify(solid, outer)
    if inner_state == TopAbs_OUT and outer_state == TopAbs_IN:
        return "hole"
    if inner_state == TopAbs_IN and outer_state == TopAbs_OUT:
        return "external"
    return None


def _classify(solid: Any, point: Sequence[float]) -> Any:
    classifier = BRepClass3d_SolidClassifier(solid)
    classifier.Perform(gp_Pnt(point[0], point[1], point[2]), 1e-6)
    return classifier.State()


def _cylinder_body(
    faces: Sequence[dict[str, Any]],
    externals: Sequence[dict[str, Any]],
    hole_face_ids: set[int],
) -> dict[str, Any] | None:
    if len(externals) != 1:
        return None
    cluster = externals[0]
    external_ids = {id(face) for face in cluster["faces"]}
    axis = orient_positive(cluster["axis"])
    for face in faces:
        if id(face) in external_ids or id(face) in hole_face_ids:
            continue
        aligned = abs(abs(dot(face["outward"], axis)) - 1.0) <= _ANGLE
        if face["kind"] != "plane" or not aligned:
            return None
    length = cluster["extent"][1] - cluster["extent"][0]
    if length <= _MIN_SPAN:
        return None
    origin = _tail_point(cluster, axis)
    return {
        "type": "cylinder",
        "origin": origin,
        "axis": round_axis(axis),
        "diameter": 2.0 * cluster["radius"],
        "length": length,
    }


def _tail_point(
    cluster: dict[str, Any], axis: Sequence[float]
) -> tuple[float, float, float]:
    start = _point_on_axis(cluster, cluster["extent"][0])
    end = _point_on_axis(cluster, cluster["extent"][1])
    if dot(axis, cluster["axis"]) >= 0:
        return start
    return end


def _extrusion_body(
    faces: Sequence[dict[str, Any]],
    hole_face_ids: set[int],
) -> dict[str, Any] | None:
    planes = [
        face
        for face in faces
        if face["kind"] == "plane" and id(face) not in hole_face_ids
    ]
    candidates = []
    for negative in planes:
        for positive in planes:
            if positive is negative:
                continue
            if dot(negative["outward"], positive["outward"]) > -1.0 + _ANGLE:
                continue
            axis = orient_positive(positive["outward"])
            length = dot(sub(positive["point"], negative["point"]), axis)
            if length <= _MIN_SPAN:
                continue
            if not _prism_along(faces, hole_face_ids, axis, negative, positive, length):
                continue
            candidates.append((length, axis, negative))
    candidates.sort(key=_extrusion_rank)
    for length, axis, start in candidates:
        published = round_axis(axis)
        profile = _profile(start["shape"], published)
        if profile is None:
            continue
        origin, points = profile
        return {
            "type": "extrusion",
            "origin": origin,
            "axis": published,
            "length": length,
            "profile": points,
        }
    return None


def _extrusion_rank(
    candidate: tuple[float, Sequence[float], dict[str, Any]],
) -> tuple[float, float, float, float]:
    length, axis, _start = candidate
    return (round(length, 6), -axis[2], -axis[1], -axis[0])


def _prism_along(
    faces: Sequence[dict[str, Any]],
    hole_face_ids: set[int],
    axis: Sequence[float],
    negative: dict[str, Any],
    positive: dict[str, Any],
    length: float,
) -> bool:
    negative_offset = dot(negative["point"], axis)
    positive_offset = dot(positive["point"], axis)
    start_faces = 0
    end_faces = 0
    for face in faces:
        if id(face) in hole_face_ids:
            continue
        if face["kind"] != "plane":
            return False
        alignment = dot(face["outward"], axis)
        if abs(abs(alignment) - 1.0) <= _ANGLE:
            offset = dot(face["point"], axis)
            if alignment < 0 and abs(offset - negative_offset) <= _DISTANCE:
                start_faces += 1
            elif alignment > 0 and abs(offset - positive_offset) <= _DISTANCE:
                end_faces += 1
            else:
                return False
        elif abs(alignment) > _ANGLE:
            return False
    if start_faces != 1 or end_faces != 1:
        return False
    return abs((positive_offset - negative_offset) - length) <= _DISTANCE


def _profile(
    face: Any, axis: Sequence[float]
) -> tuple[tuple[float, float, float], list[list[float]]] | None:
    wire = BRepTools.OuterWire_s(face)
    if wire.IsNull():
        return None
    points: list[tuple[float, float, float]] = []
    explorer = BRepTools_WireExplorer(wire, face)
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        curve = BRepAdaptor_Curve(edge)
        if curve.GetType() != GeomAbs_Line:
            return None
        vertex = explorer.CurrentVertex()
        point = BRep_Tool.Pnt_s(vertex)
        points.append((point.X(), point.Y(), point.Z()))
        explorer.Next()
    points = _dedupe(points)
    if len(points) < 3:
        return None
    profile_u, profile_v = profile_axes(axis)
    origin = points[0]
    uv = [_project(point, origin, profile_u, profile_v) for point in points]
    if signed_area(uv) < 0:
        points.reverse()
        uv.reverse()
    centroid_u, centroid_v = area_centroid(uv)
    world = add(add(origin, scale(profile_u, centroid_u)), scale(profile_v, centroid_v))
    profile = [
        [point[0] - centroid_u, point[1] - centroid_v] for point in uv
    ]
    return world, profile


def _project(
    point: Sequence[float],
    origin: Sequence[float],
    profile_u: Sequence[float],
    profile_v: Sequence[float],
) -> tuple[float, float]:
    delta = sub(point, origin)
    return dot(delta, profile_u), dot(delta, profile_v)


def _dedupe(
    points: Sequence[tuple[float, float, float]],
) -> list[tuple[float, float, float]]:
    unique: list[tuple[float, float, float]] = []
    for point in points:
        if unique and dist(unique[-1], point) <= _DISTANCE:
            continue
        unique.append(point)
    if len(unique) > 1 and dist(unique[0], unique[-1]) <= _DISTANCE:
        unique.pop()
    return unique


def _hole_feature(
    cluster: dict[str, Any], faces: Sequence[dict[str, Any]]
) -> dict[str, Any] | None:
    start = _point_on_axis(cluster, cluster["extent"][0])
    end = _point_on_axis(cluster, cluster["extent"][1])
    start_closed = _disk_at(faces, start, cluster["radius"], cluster["axis"])
    end_closed = _disk_at(faces, end, cluster["radius"], cluster["axis"])
    depth = dist(start, end)
    if depth <= _MIN_SPAN:
        return None
    if start_closed and end_closed:
        return None
    if start_closed and not end_closed:
        origin = end
        axis = normalize(sub(start, end))
        through = False
    elif end_closed and not start_closed:
        origin = start
        axis = normalize(sub(end, start))
        through = False
    else:
        through = True
        axis = orient_positive(cluster["axis"])
        origin = start if dot(axis, cluster["axis"]) >= 0 else end
    return {
        "type": "hole",
        "origin": origin,
        "axis": round_axis(axis),
        "diameter": 2.0 * cluster["radius"],
        "depth": depth,
        "through": through,
    }


def _disk_at(
    faces: Sequence[dict[str, Any]],
    center: Sequence[float],
    radius: float,
    axis: Sequence[float],
) -> bool:
    for face in faces:
        if face["kind"] != "plane":
            continue
        circle = _outer_circle(face["shape"])
        if circle is None:
            continue
        circle_center, circle_radius, circle_axis = circle
        if abs(circle_radius - radius) > _DISTANCE:
            continue
        if dist(circle_center, center) > _DISTANCE:
            continue
        if abs(abs(dot(circle_axis, axis)) - 1.0) > _ANGLE:
            continue
        return True
    return False


def _outer_circle(
    face: Any,
) -> tuple[tuple[float, float, float], float, tuple[float, float, float]] | None:
    wire = BRepTools.OuterWire_s(face)
    if wire.IsNull():
        return None
    center = None
    radius = None
    circle_axis = None
    span = 0.0
    found = False
    explorer = BRepTools_WireExplorer(wire, face)
    while explorer.More():
        edge = TopoDS.Edge_s(explorer.Current())
        curve = BRepAdaptor_Curve(edge)
        if curve.GetType() != GeomAbs_Circle:
            return None
        circle = curve.Circle()
        point = circle.Location()
        this_center = (point.X(), point.Y(), point.Z())
        this_radius = circle.Radius()
        direction = circle.Axis().Direction()
        this_axis = (direction.X(), direction.Y(), direction.Z())
        if center is None:
            center = this_center
            radius = this_radius
            circle_axis = this_axis
        elif (
            radius is None
            or abs(this_radius - radius) > _RADIUS
            or dist(this_center, center) > _DISTANCE
        ):
            return None
        span += abs(curve.LastParameter() - curve.FirstParameter())
        found = True
        explorer.Next()
    if not found or center is None or radius is None or circle_axis is None:
        return None
    if abs(span - 2.0 * math.pi) > _FULL_TURN:
        return None
    return center, radius, circle_axis
