"""Generate the STEP fixtures the parser tests read.

The solids are created here, with Open CASCADE primitives, when a test runs.
See tests/NOTICE. Nothing in this module is a vendored CAD file.
"""

from __future__ import annotations

import os
from pathlib import Path

from OCP.BRep import BRep_Builder
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut
from OCP.BRepBuilderAPI import BRepBuilderAPI_Transform
from OCP.BRepPrimAPI import (
    BRepPrimAPI_MakeBox,
    BRepPrimAPI_MakeCylinder,
    BRepPrimAPI_MakeSphere,
)
from OCP.gp import gp_Ax2, gp_Dir, gp_Pnt, gp_Trsf, gp_Vec
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Controller, STEPControl_Writer
from OCP.TopoDS import TopoDS_Compound

from step2revit.parse import _quiet_stdio


def write_box(path: Path, *, unit: str = "MM", schema: str = "AP214IS") -> Path:
    """Axis-aligned box from the origin, 10 mm by 20 mm by 30 mm."""

    shape = BRepPrimAPI_MakeBox(10, 20, 30).Shape()
    return _export(shape, path, unit=unit, schema=schema)


def write_cube(path: Path) -> Path:
    """10 mm cube from the origin. All three prism axes are the same length."""

    return _export(BRepPrimAPI_MakeBox(10, 10, 10).Shape(), path)


def write_cylinder(path: Path) -> Path:
    """Radius 5 mm, length 40 mm, along +Z from the origin. The spec's shank."""

    return _export(BRepPrimAPI_MakeCylinder(5, 40).Shape(), path)


def write_cylinder_along_x(path: Path) -> Path:
    """Radius 5 mm, length 40 mm, along +X from the origin."""

    axis = gp_Ax2(gp_Pnt(0, 0, 0), gp_Dir(1, 0, 0))
    return _export(BRepPrimAPI_MakeCylinder(axis, 5, 40).Shape(), path)


def write_plate_with_hole(path: Path) -> Path:
    """40 mm by 30 mm by 5 mm plate with an 8 mm through hole at its center."""

    plate = BRepPrimAPI_MakeBox(40, 30, 5).Shape()
    drill = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(20, 15, -1), gp_Dir(0, 0, 1)), 4, 7
    ).Shape()
    return _export(BRepAlgoAPI_Cut(plate, drill).Shape(), path)


def write_blind_hole(path: Path) -> Path:
    """40 x 30 x 10 mm plate with a 6 mm hole, 6 mm deep, opening on the top face."""

    plate = BRepPrimAPI_MakeBox(40, 30, 10).Shape()
    drill = BRepPrimAPI_MakeCylinder(
        gp_Ax2(gp_Pnt(10, 10, 4), gp_Dir(0, 0, 1)), 3, 8
    ).Shape()
    return _export(BRepAlgoAPI_Cut(plate, drill).Shape(), path)


def write_two_boxes(path: Path) -> Path:
    """A 10 mm cube at the origin and a 5 mm cube translated by 20 mm on X."""

    first = BRepPrimAPI_MakeBox(10, 10, 10).Shape()
    second = BRepPrimAPI_MakeBox(5, 5, 5).Shape()
    transform = gp_Trsf()
    transform.SetTranslation(gp_Vec(20, 0, 0))
    moved = BRepBuilderAPI_Transform(second, transform, True).Shape()
    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    builder.Add(compound, first)
    builder.Add(compound, moved)
    return _export(compound, path)


def write_sphere(path: Path) -> Path:
    """A solid with no cylinder, hole, or extrusion."""

    return _export(BRepPrimAPI_MakeSphere(5).Shape(), path)


def _export(shape, path: Path, *, unit: str = "MM", schema: str = "AP214IS") -> Path:
    STEPControl_Controller.Init_s()
    Interface_Static.SetCVal_s("write.step.unit", unit)
    Interface_Static.SetCVal_s("write.step.schema", schema)
    writer = STEPControl_Writer()
    with _quiet_stdio():
        transferred = writer.Transfer(shape, STEPControl_AsIs)
        if int(transferred) != int(IFSelect_RetDone):
            raise RuntimeError(f"STEP transfer failed with status {int(transferred)}")
        written = writer.Write(os.fspath(path))
        if int(written) != int(IFSelect_RetDone):
            raise RuntimeError(f"STEP write failed with status {int(written)}")
    return path
