"""Read one STEP part and write the schema-1 neutral document.

The Revit family builder is a later step. It reads the JSON this module
writes and does not read STEP.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.IFSelect import IFSelect_RetDone
from OCP.Interface import Interface_Static
from OCP.STEPControl import STEPControl_Controller, STEPControl_Reader
from OCP.TColStd import TColStd_SequenceOfAsciiString
from OCP.TopAbs import TopAbs_SOLID
from OCP.TopExp import TopExp_Explorer
from OCP.TopoDS import TopoDS

from step2revit.document import DocumentError, assemble_document
from step2revit.features import recognize_solid
from step2revit.geom import round_mm
from step2revit.schema import SchemaError, step_schema_names

_STEP_SUFFIXES = {".step", ".stp"}
_OCC_READY = False


class StepParseError(Exception):
    """The STEP part could not be converted, and no neutral document was written."""

    def __init__(self, path: str | Path, reason: str) -> None:
        self.path = Path(path)
        self.reason = reason
        super().__init__(f"{self.path}: {reason}")


class _UnitError(Exception):
    pass


def parse_step(
    source: str | Path,
    output: str | Path | None = None,
) -> dict[str, Any]:
    """Load a STEP AP203, AP214, or AP242 part and return its neutral document.

    When ``output`` is given, also write that document as UTF-8 JSON. On
    failure, raise ``StepParseError`` and leave any existing output untouched.
    Lengths in the document are millimetres. Axes are the STEP file's own
    right-handed axes.
    """

    path = Path(source)
    _check_input(path)
    if output is not None and Path(output).resolve() == path.resolve():
        raise StepParseError(path, "output path is the STEP file")
    try:
        text = path.read_bytes()
    except OSError as exc:
        raise StepParseError(path, f"unreadable ({exc.strerror})") from exc
    if text.startswith(b"\xef\xbb\xbf"):
        text = text[3:]
    try:
        step_schema_names(text.decode("utf-8", errors="replace"))
    except SchemaError as exc:
        raise StepParseError(path, exc.reason) from exc

    reader, shape = _read_shape(path)
    solids = _solids(shape)
    if not solids:
        raise StepParseError(path, "no solids were found")
    try:
        length_unit = _length_unit(reader)
    except _UnitError:
        raise StepParseError(path, "the length unit is unknown") from None

    ordered = sorted(_measured(solids), key=_solid_sort_key)
    if not ordered:
        raise StepParseError(path, "no solids were found")
    solid_records = [{"bounding_box": box} for box, _solid in ordered]
    raw_features: list[dict[str, Any]] = []
    for index, (_box, solid) in enumerate(ordered):
        for feature in recognize_solid(solid):
            feature["solid_index"] = index
            raw_features.append(feature)
    if not raw_features:
        raise StepParseError(path, "no supported features were found")
    try:
        document = assemble_document(
            filename=path.name,
            length_unit=length_unit,
            solids=solid_records,
            features=raw_features,
        )
    except DocumentError as exc:
        raise StepParseError(path, exc.reason) from exc
    if output is not None:
        _write_document(document, Path(output))
    return document


def single_length_unit(names: Sequence[str]) -> str:
    """Return the only length-unit name, or raise ``_UnitError``."""

    unique: list[str] = []
    for name in names:
        if name and name not in unique:
            unique.append(name)
    if len(unique) != 1:
        raise _UnitError
    return unique[0]


def _check_input(path: Path) -> None:
    if path.suffix.lower() not in _STEP_SUFFIXES:
        raise StepParseError(path, "file name must end in .step or .stp")
    if not path.exists():
        raise StepParseError(path, "file does not exist")
    if not path.is_file():
        raise StepParseError(path, "path is not a file")


def _ensure_occ() -> None:
    global _OCC_READY
    if not _OCC_READY:
        STEPControl_Controller.Init_s()
        _OCC_READY = True


def _read_shape(path: Path) -> tuple[STEPControl_Reader, Any]:
    _ensure_occ()
    Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")
    reader = STEPControl_Reader()
    try:
        with _quiet_stdio():
            status = reader.ReadFile(os.fspath(path))
            if status != IFSelect_RetDone:
                raise StepParseError(
                    path, f"could not read STEP geometry (status {int(status)})"
                )
            reader.TransferRoots()
            shape = reader.OneShape()
    except StepParseError:
        raise
    except Exception as exc:
        raise StepParseError(path, f"could not read STEP geometry ({exc})") from exc
    return reader, shape


def _length_unit(reader: STEPControl_Reader) -> str:
    lengths = TColStd_SequenceOfAsciiString()
    angles = TColStd_SequenceOfAsciiString()
    solid_angles = TColStd_SequenceOfAsciiString()
    reader.FileUnits(lengths, angles, solid_angles)
    names = [
        lengths.Value(index).ToCString()
        for index in range(1, lengths.Length() + 1)
    ]
    return single_length_unit(names)


def _solids(shape: Any) -> list[Any]:
    if shape is None or shape.IsNull():
        return []
    found = []
    explorer = TopExp_Explorer(shape, TopAbs_SOLID)
    while explorer.More():
        found.append(TopoDS.Solid_s(explorer.Current()))
        explorer.Next()
    return found


def _measured(
    solids: Sequence[Any],
) -> list[tuple[dict[str, tuple[float, float, float]], Any]]:
    measured = []
    for solid in solids:
        box = Bnd_Box()
        BRepBndLib.AddOptimal_s(solid, box)
        if box.IsVoid():
            continue
        xmin, ymin, zmin, xmax, ymax, zmax = box.Get()
        measured.append(
            (
                {"min": (xmin, ymin, zmin), "max": (xmax, ymax, zmax)},
                solid,
            )
        )
    return measured


def _solid_sort_key(
    item: tuple[Mapping[str, Sequence[float]], Any],
) -> tuple[float, ...]:
    box = item[0]
    return tuple(round_mm(value) for value in (*box["min"], *box["max"]))


def _write_document(document: Mapping[str, Any], output: Path) -> None:
    if output.exists() and output.is_dir():
        raise StepParseError(output, "output path is a directory")
    if not output.parent.exists():
        raise StepParseError(output, "output directory does not exist")
    payload = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    temporary = output.with_name(f".{output.name}.tmp")
    try:
        temporary.write_text(payload, encoding="utf-8")
        temporary.replace(output)
    except OSError as exc:
        reason = exc.strerror or "write failed"
        raise StepParseError(
            output, f"could not write neutral document ({reason})"
        ) from exc
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def _quiet_stdio():
    """Hide Open CASCADE's transfer trace, which writes straight to the C stdout."""

    sys.stdout.flush()
    sys.stderr.flush()
    try:
        devnull = os.open(os.devnull, os.O_WRONLY)
        saved_out = os.dup(1)
        saved_err = os.dup(2)
    except OSError:
        yield
        return
    try:
        os.dup2(devnull, 1)
        os.dup2(devnull, 2)
        yield
    finally:
        os.dup2(saved_out, 1)
        os.dup2(saved_err, 2)
        os.close(saved_out)
        os.close(saved_err)
        os.close(devnull)
