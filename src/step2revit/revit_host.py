"""Revit API host for one schema-1 family plan.

Importing this module does not import the Revit API and does not write a
family. ``build_family`` calls Revit only after a plan exists, and only when
the caller passes a Revit application. That happens inside Revit on Windows.
GitHub Actions and this repository's cloud environment do not have Revit, so
they never reach ``NewFamilyDocument`` or ``SaveAs``.
"""

from __future__ import annotations

import os
from pathlib import Path

from step2revit.family_plan import FamilyBuildError, load_neutral_document, plan_family
from step2revit.family_session import execute_plan

# Tried in this order. The extrusion end is the offset NewExtrusion receives.
_LENGTH_PARAMETERS = (
    "EXTRUSION_END_PARAM",
    "EXTRUSION_DEPTH_PARAM",
    "EXTRUSION_LENGTH",
)


def build_family(
    document_path: str | os.PathLike[str],
    output_path: str | os.PathLike[str],
    template_path: str | os.PathLike[str],
    application: object,
) -> None:
    """Write one loadable ``.rfa`` from a schema-1 document.

    Raises ``FamilyBuildError`` without writing when the document, the output
    path, the template, or Revit itself cannot be used. ``application`` is a
    Revit ``Application`` or ``UIApplication``.
    """

    document_text = os.fspath(document_path)
    output_text = os.fspath(output_path)
    template_text = os.fspath(template_path)
    _check_output(output_text)
    document = load_neutral_document(document_text)
    plan = plan_family(document, document_path=document_text)
    if not os.path.isfile(template_text):
        raise FamilyBuildError(template_text, "family template was not found")
    try:
        app = _unwrap_application(application)
    except FamilyBuildError as exc:
        raise FamilyBuildError(document_text, exc.reason) from exc
    session = RevitFamilySession(app, document_text)
    try:
        execute_plan(
            plan,
            session,
            template_path=template_text,
            output_path=output_text,
        )
    except FamilyBuildError as exc:
        if exc.path:
            raise
        raise FamilyBuildError(document_text, exc.reason) from exc
    except Exception as exc:
        raise FamilyBuildError(
            document_text,
            f"Revit failed while building the family ({exc})",
        ) from exc


class RevitFamilySession:
    """``FamilySession`` implemented with the Revit API.

    The API modules are imported from the methods, not from this class body.
    """

    def __init__(self, application: object, document_path: str) -> None:
        self._app = application
        self._document_path = document_path
        self._doc = None
        self._transaction = None
        self._parameters: dict = {}

    def open_template(self, template_path: str) -> None:
        db = _db()
        document = self._app.NewFamilyDocument(template_path)
        if document is None:
            raise FamilyBuildError(
                template_path,
                "Revit did not open the family template",
            )
        self._doc = document
        try:
            category = document.OwnerFamily.FamilyCategory.BuiltInCategory
        except Exception as exc:
            self.close_without_saving()
            raise FamilyBuildError(
                template_path,
                f"template category could not be read ({exc})",
            ) from exc
        if category != db.BuiltInCategory.OST_GenericModel:
            self.close_without_saving()
            raise FamilyBuildError(
                template_path,
                "template is not a Generic Model family",
            )
        if not document.IsFamilyDocument:
            self.close_without_saving()
            raise FamilyBuildError(
                template_path,
                "Revit did not open a family document",
            )
        self._transaction = db.Transaction(document, "STEP2Revit family")
        self._transaction.Start()
        _ensure_current_type(document)

    def add_type_length_parameter(self, name: str, value_feet: float) -> None:
        db = _db()
        manager = self._doc.FamilyManager
        try:
            parameter = _add_length_parameter(manager, db, name)
            manager.Set(parameter, value_feet)
        except FamilyBuildError:
            raise
        except Exception as exc:
            raise FamilyBuildError(
                self._document_path,
                f"could not add type parameter {name} ({exc})",
            ) from exc
        self._parameters[name] = parameter

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
        db = _db()
        origin = db.XYZ(*origin_feet)
        try:
            plane = db.Plane.CreateByOriginAndBasis(
                origin,
                db.XYZ(*plane_x),
                db.XYZ(*plane_y),
            )
            sketch = db.SketchPlane.Create(self._doc, plane)
            loop = db.CurveArrArray()
            curve_array = db.CurveArray()
            for curve in curves:
                curve_array.Append(_revit_curve(db, plane, curve))
            loop.Append(curve_array)
            extrusion = self._doc.FamilyCreate.NewExtrusion(
                solid,
                loop,
                sketch,
                length_feet,
            )
            self._doc.Regenerate()
        except FamilyBuildError:
            raise
        except Exception as exc:
            raise FamilyBuildError(
                self._document_path,
                f"feature {feature_id} could not be extruded ({exc})",
            ) from exc
        self._bind_length(extrusion, length_parameter, feature_id)
        if diameter_parameter is not None:
            self._bind_diameter(
                extrusion,
                diameter_parameter,
                origin,
                axis,
                plane_x,
                plane_y,
                feature_id,
            )

    def save(self, output_path: str) -> None:
        db = _db()
        if self._transaction is not None and self._transaction.HasStarted():
            if not self._transaction.HasEnded():
                self._transaction.Commit()
        options = db.SaveAsOptions()
        options.OverwriteExistingFile = True
        self._doc.SaveAs(output_path, options)

    def close_without_saving(self) -> None:
        transaction = self._transaction
        document = self._doc
        self._transaction = None
        self._doc = None
        if transaction is not None:
            try:
                if transaction.HasStarted() and not transaction.HasEnded():
                    transaction.RollBack()
            except Exception:
                pass
        if document is not None:
            document.Close(False)


def _bind_length(
    self: RevitFamilySession,
    extrusion: object,
    name: str,
    feature_id: str,
) -> None:
    db = _db()
    manager = self._doc.FamilyManager
    chosen = None
    for built_in_name in _LENGTH_PARAMETERS:
        built_in = getattr(db.BuiltInParameter, built_in_name, None)
        if built_in is None:
            continue
        candidate = _element_parameter(extrusion, built_in)
        if candidate is None:
            continue
        try:
            allowed = manager.CanElementParameterBeAssociated(candidate)
        except Exception:
            allowed = True
        if allowed:
            chosen = candidate
            break
    if chosen is None:
        raise FamilyBuildError(
            self._document_path,
            f"feature {feature_id} has no extrusion length to bind to {name}",
        )
    try:
        manager.AssociateElementParameterToFamilyParameter(
            chosen,
            self._parameters[name],
        )
    except Exception as exc:
        raise FamilyBuildError(
            self._document_path,
            f"feature {feature_id} could not bind {name} ({exc})",
        ) from exc


def _bind_diameter(
    self: RevitFamilySession,
    extrusion: object,
    name: str,
    origin: object,
    axis: tuple[float, float, float],
    plane_x: tuple[float, float, float],
    plane_y: tuple[float, float, float],
    feature_id: str,
) -> None:
    """Label a diameter dimension with the JSON parameter.

    Revit rejects a diameter dimension on some sketch arcs. The fallback adds
    ``<Name>_Radius`` with the formula ``<Name> / 2`` and labels a radial
    dimension, so editing the JSON parameter still changes the circle.
    """

    db = _db()
    reference = _arc_reference(self._doc, db, extrusion)
    if reference is None:
        raise FamilyBuildError(
            self._document_path,
            f"feature {feature_id} has no arc to bind {name}",
        )
    view = _view_for_axis(self._doc, db, axis, origin, plane_x, plane_y, feature_id)
    try:
        dimension = self._doc.FamilyCreate.NewDiameterDimension(view, reference, origin)
        dimension.FamilyLabel = self._parameters[name]
        return
    except Exception as diameter_error:
        diameter_failure = diameter_error
    radius_name = f"{name}_Radius"
    try:
        manager = self._doc.FamilyManager
        radius_parameter = _add_length_parameter(manager, db, radius_name)
        manager.SetFormula(radius_parameter, f"{name} / 2")
        dimension = self._doc.FamilyCreate.NewRadialDimension(view, reference, origin)
        dimension.FamilyLabel = radius_parameter
    except Exception as radial_error:
        raise FamilyBuildError(
            self._document_path,
            f"feature {feature_id} could not bind {name} "
            f"({diameter_failure}; {radial_error})",
        ) from radial_error


def _view_for_axis(document, db, axis, origin, plane_x, plane_y, feature_id: str):
    best = None
    best_score = -1.0
    skipped = _skipped_view_types(db)
    for view in db.FilteredElementCollector(document).OfClass(db.View):
        if getattr(view, "IsTemplate", False):
            continue
        if view.ViewType in skipped:
            continue
        direction = getattr(view, "ViewDirection", None)
        if direction is None:
            continue
        alignment = abs(
            direction.X * axis[0] + direction.Y * axis[1] + direction.Z * axis[2]
        )
        score = alignment
        if view.ViewType == db.ViewType.ThreeD:
            score -= 0.05
        if score > best_score:
            best = view
            best_score = score
    if best is not None and best_score >= 0.99:
        return best
    created = _section_view(document, db, axis, origin, plane_x, plane_y)
    if created is not None:
        return created
    if best is not None:
        return best
    raise FamilyBuildError(
        "",
        f"feature {feature_id} has no view parallel to its axis",
    )


def _section_view(document, db, axis, origin, plane_x, plane_y):
    view_type_id = None
    for view_type in db.FilteredElementCollector(document).OfClass(db.ViewFamilyType):
        if view_type.ViewFamily == db.ViewFamily.Section:
            view_type_id = view_type.Id
            break
    if view_type_id is None:
        return None
    transform = db.Transform.Identity
    transform.Origin = origin
    transform.BasisX = db.XYZ(*plane_x)
    transform.BasisY = db.XYZ(*plane_y)
    transform.BasisZ = db.XYZ(*axis)
    box = db.BoundingBoxXYZ()
    box.Transform = transform
    box.Min = db.XYZ(-1000, -1000, -10)
    box.Max = db.XYZ(1000, 1000, 10)
    try:
        return db.ViewSection.CreateSection(document, view_type_id, box)
    except Exception:
        return None


def _arc_reference(document, db, extrusion):
    sketch = extrusion.Sketch
    for curve_array in _items(sketch.Profile):
        for curve in _items(curve_array):
            if not _is_arc(db, curve):
                continue
            reference = _curve_reference(document, curve)
            if reference is not None:
                return reference
    return None


def _curve_reference(document, curve):
    direct = getattr(curve, "Reference", None)
    if direct is not None:
        return direct
    try:
        end_ref = curve.GetEndPointReference(0)
    except Exception:
        return None
    element = document.GetElement(end_ref.ElementId)
    if element is None:
        return None
    geometry = getattr(element, "GeometryCurve", None)
    if geometry is None:
        return None
    return getattr(geometry, "Reference", None)


def _revit_curve(db, plane, curve: tuple):
    kind = curve[0]
    if kind == "line":
        return db.Line.CreateBound(db.XYZ(*curve[1]), db.XYZ(*curve[2]))
    center, _x_axis, _y_axis, _normal, radius, start_angle, end_angle = curve[1:]
    # The plane already carries the arc's X and Y axes.
    del center
    return db.Arc.Create(plane, radius, start_angle, end_angle)


def _add_length_parameter(manager, db, name: str):
    if hasattr(db, "GroupTypeId") and hasattr(db, "SpecTypeId"):
        group = getattr(db.GroupTypeId, "Geometry", None)
        if group is None:
            group = db.GroupTypeId.General
        return manager.AddParameter(name, group, db.SpecTypeId.Length, False)
    return manager.AddParameter(
        name,
        db.BuiltInParameterGroup.PG_GEOMETRY,
        db.ParameterType.Length,
        False,
    )


def _ensure_current_type(document) -> None:
    manager = document.FamilyManager
    if manager.CurrentType is not None:
        return
    try:
        types = list(manager.Types)
    except Exception:
        types = []
    if types:
        manager.CurrentType = types[0]
        return
    manager.NewType("STEP2Revit")


def _element_parameter(element, built_in):
    getter = getattr(element, "get_Parameter", None)
    if getter is not None:
        try:
            return getter(built_in)
        except Exception:
            return None
    try:
        return element.Parameter[built_in]
    except Exception:
        return None


def _items(collection):
    size = getattr(collection, "Size", None)
    if isinstance(size, int):
        items = []
        for index in range(size):
            try:
                items.append(collection.get_Item(index))
            except Exception:
                items.append(collection[index])
        return items
    return list(collection)


def _is_arc(db, curve) -> bool:
    if isinstance(curve, db.Arc):
        return True
    return type(curve).__name__ == "Arc"


def _skipped_view_types(db):
    names = (
        "ProjectBrowser",
        "SystemBrowser",
        "DrawingSheet",
        "Legend",
        "Schedule",
        "PanelSchedule",
        "ColumnSchedule",
        "Internal",
        "LoadsReport",
        "CostReport",
        "Report",
    )
    skipped = set()
    for name in names:
        value = getattr(db.ViewType, name, None)
        if value is not None:
            skipped.add(value)
    return skipped


def _db():
    try:
        from Autodesk.Revit import DB

        return DB
    except ImportError:
        pass
    try:
        import clr

        clr.AddReference("RevitAPI")
        from Autodesk.Revit import DB

        return DB
    except Exception as exc:
        raise FamilyBuildError(
            "",
            "Revit API is not available. "
            "Run the family script inside Revit on Windows.",
        ) from exc


def _unwrap_application(application: object):
    if application is None:
        raise FamilyBuildError(
            "",
            "Revit is not running. Run the family script inside Revit on Windows.",
        )
    if hasattr(application, "NewFamilyDocument"):
        return application
    inner = getattr(application, "Application", None)
    if inner is not None and hasattr(inner, "NewFamilyDocument"):
        return inner
    raise FamilyBuildError(
        "",
        "Revit is not running. Run the family script inside Revit on Windows.",
    )


def _check_output(output_path: str) -> None:
    path = Path(output_path)
    if path.suffix.lower() != ".rfa":
        raise FamilyBuildError(output_path, "output path must end in .rfa")
    if path.exists() and path.is_dir():
        raise FamilyBuildError(output_path, "output path is a directory")
    if not path.parent.is_dir():
        raise FamilyBuildError(output_path, "output directory does not exist")


# Bound after the class body so the methods can live next to the helpers
# they use without a second copy of the Revit call sequence.
RevitFamilySession._bind_length = _bind_length
RevitFamilySession._bind_diameter = _bind_diameter
