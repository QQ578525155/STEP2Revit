"""Family builder tests. They plan schema-1 JSON and never launch Revit."""

from __future__ import annotations

import copy
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.step_samples import (
    write_blind_hole,
    write_box,
    write_cylinder,
    write_cylinder_along_x,
    write_plate_with_hole,
    write_two_boxes,
)
from tests.test_document import SHANK
from tests.test_scaffold import _is_ignored

from step2revit import FamilyBuildError, plan_family
from step2revit.family_plan import (
    SketchArc,
    SketchLine,
    load_neutral_document,
    mm_to_feet,
    planned_bounding_box,
    resolve_template,
    template_candidates,
    with_parameter_values,
)
from step2revit.family_session import execute_plan
from step2revit.parse import parse_step
from step2revit.revit_host import RevitFamilySession, build_family

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "revit"
    / "STEP2Revit.extension"
    / "STEP2Revit.tab"
    / "Build.panel"
    / "BuildFamily.pushbutton"
    / "script.py"
)


class RecordingSession:
    def __init__(self, fail_at: str | None = None) -> None:
        self.events: list[tuple] = []
        self.fail_at = fail_at

    def open_template(self, template_path: str) -> None:
        self.events.append(("open", template_path))
        if self.fail_at == "open":
            raise RuntimeError("open failed")

    def add_type_length_parameter(self, name: str, value_feet: float) -> None:
        self.events.append(("parameter", name, value_feet))

    def add_extrusion(self, **kwargs) -> None:
        if self.fail_at == "extrusion":
            raise RuntimeError("extrusion failed")
        self.events.append(("extrusion", kwargs))

    def save(self, output_path: str) -> None:
        self.events.append(("save", output_path))

    def close_without_saving(self) -> None:
        self.events.append(("close",))


def test_internal_feet_use_the_international_foot() -> None:
    assert mm_to_feet(304.8) == 1
    assert mm_to_feet(10) == pytest.approx(10 / 304.8)


def test_shank_plan_is_a_parametric_cylinder() -> None:
    plan = plan_family(SHANK, document_path="shank.json")
    assert plan.template_name == "Metric Generic Model.rft"
    assert plan.category == "Generic Model"
    assert plan.in_place is False
    assert [item.name for item in plan.parameters] == ["ShankDiameter", "ShankLength"]
    assert plan.parameters[0].value_mm == 10
    assert plan.parameters[0].value_feet == pytest.approx(mm_to_feet(10))
    assert plan.parameters[1].value_mm == 40

    assert len(plan.extrusions) == 1
    extrusion = plan.extrusions[0]
    assert extrusion.feature_id == "shank"
    assert extrusion.feature_type == "cylinder"
    assert extrusion.solid is True
    assert extrusion.origin_mm == (0.0, 0.0, 0.0)
    assert extrusion.axis == pytest.approx((0.0, 0.0, 1.0))
    assert extrusion.plane_x == pytest.approx((1.0, 0.0, 0.0))
    assert extrusion.plane_y == pytest.approx((0.0, 1.0, 0.0))
    assert extrusion.length_mm == 40
    assert extrusion.length_parameter == "ShankLength"
    assert extrusion.diameter_mm == 10
    assert extrusion.diameter_parameter == "ShankDiameter"
    assert len(extrusion.curves) == 2
    assert all(isinstance(curve, SketchArc) for curve in extrusion.curves)
    assert extrusion.curves[0].radius_mm == 5
    assert extrusion.curves[0].start_angle == 0
    assert extrusion.curves[0].end_angle == pytest.approx(math.pi)
    assert extrusion.curves[1].start_angle == pytest.approx(math.pi)
    assert extrusion.curves[1].end_angle == pytest.approx(2 * math.pi)

    box = planned_bounding_box(plan)
    assert box is not None
    assert box["min"] == pytest.approx([-5, -5, 0])
    assert box["max"] == pytest.approx([5, 5, 40])


def test_parameter_edits_resize_the_plan() -> None:
    plan = plan_family(SHANK)
    longer = with_parameter_values(plan, {"ShankLength": 80})
    assert longer.extrusions[0].length_mm == 80
    assert longer.parameters[1].value_feet == pytest.approx(mm_to_feet(80))
    assert longer.extrusions[0].curves[0].radius_mm == 5
    assert planned_bounding_box(longer)["max"][2] == pytest.approx(80)

    wider = with_parameter_values(plan, {"ShankDiameter": 20})
    assert wider.extrusions[0].diameter_mm == 20
    assert wider.extrusions[0].curves[0].radius_mm == 10
    assert wider.extrusions[0].curves[1].radius_mm == 10
    assert planned_bounding_box(wider)["min"][0] == pytest.approx(-10)
    assert planned_bounding_box(wider)["max"][2] == pytest.approx(40)

    with pytest.raises(FamilyBuildError, match="unknown parameter Nope"):
        with_parameter_values(plan, {"Nope": 1})
    with pytest.raises(FamilyBuildError, match="ShankDiameter is not positive"):
        with_parameter_values(plan, {"ShankDiameter": 0})


def test_plate_puts_the_solid_before_the_hole() -> None:
    document = _part(
        filename="plate.step",
        box_min=(0.0, 0.0, 0.0),
        box_max=(40.0, 30.0, 5.0),
        parameters=[
            {"name": "Hole1Diameter", "value": 8.0, "unit": "mm", "kind": "length"},
            {"name": "Hole1Depth", "value": 5.0, "unit": "mm", "kind": "length"},
            {"name": "Extrusion1Length", "value": 5.0, "unit": "mm", "kind": "length"},
        ],
        features=[
            {
                "id": "hole_1",
                "type": "hole",
                "solid_id": "solid_1",
                "origin": [20.0, 15.0, 0.0],
                "axis": [0.0, 0.0, 1.0],
                "diameter": {"parameter": "Hole1Diameter"},
                "depth": {"parameter": "Hole1Depth"},
                "through": True,
            },
            {
                "id": "extrusion_1",
                "type": "extrusion",
                "solid_id": "solid_1",
                "origin": [20.0, 15.0, 0.0],
                "axis": [0.0, 0.0, 1.0],
                "length": {"parameter": "Extrusion1Length"},
                "profile": [[-20.0, -15.0], [20.0, -15.0], [20.0, 15.0], [-20.0, 15.0]],
            },
        ],
    )
    plan = plan_family(document, document_path="plate.json")
    assert [item.feature_type for item in plan.extrusions] == ["extrusion", "hole"]
    solid, hole = plan.extrusions
    assert solid.solid is True
    assert hole.solid is False
    assert hole.through is True
    assert hole.diameter_parameter == "Hole1Diameter"
    assert hole.length_parameter == "Hole1Depth"
    assert hole.curves[0].radius_mm == 4
    assert all(isinstance(curve, SketchLine) for curve in solid.curves)
    assert solid.curves[0].start_mm == pytest.approx((0.0, 0.0, 0.0))
    assert solid.curves[0].end_mm == pytest.approx((40.0, 0.0, 0.0))
    assert solid.curves[-1].end_mm == pytest.approx(solid.curves[0].start_mm)
    box = planned_bounding_box(plan)
    assert box["min"] == pytest.approx([0, 0, 0])
    assert box["max"] == pytest.approx([40, 30, 5])


def test_profile_along_x_uses_the_spec_frame() -> None:
    document = _part(
        filename="rib.step",
        box_min=(0.0, 0.0, 0.0),
        box_max=(8.0, 10.0, 5.0),
        parameters=[
            {"name": "Extrusion1Length", "value": 8.0, "unit": "mm", "kind": "length"},
        ],
        features=[
            {
                "id": "extrusion_1",
                "type": "extrusion",
                "solid_id": "solid_1",
                "origin": [0.0, 0.0, 0.0],
                "axis": [1.0, 0.0, 0.0],
                "length": {"parameter": "Extrusion1Length"},
                "profile": [[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]],
            }
        ],
    )
    extrusion = plan_family(document).extrusions[0]
    assert extrusion.plane_x == pytest.approx((0.0, 1.0, 0.0))
    assert extrusion.plane_y == pytest.approx((0.0, 0.0, 1.0))
    assert extrusion.axis == pytest.approx((1.0, 0.0, 0.0))
    assert extrusion.curves[0].start_mm == pytest.approx((0.0, 0.0, 0.0))
    assert extrusion.curves[0].end_mm == pytest.approx((0.0, 10.0, 0.0))
    assert extrusion.curves[1].end_mm == pytest.approx((0.0, 10.0, 5.0))
    box = planned_bounding_box(plan_family(document))
    assert box["min"] == pytest.approx([0, 0, 0])
    assert box["max"] == pytest.approx([8, 10, 5])


def test_clockwise_profile_is_wound_with_the_axis() -> None:
    document = _part(
        filename="cw.step",
        box_min=(-5.0, -5.0, 0.0),
        box_max=(5.0, 5.0, 4.0),
        parameters=[
            {"name": "Extrusion1Length", "value": 4.0, "unit": "mm", "kind": "length"},
        ],
        features=[
            {
                "id": "extrusion_1",
                "type": "extrusion",
                "solid_id": "solid_1",
                "origin": [0.0, 0.0, 0.0],
                "axis": [0.0, 0.0, 1.0],
                "length": {"parameter": "Extrusion1Length"},
                "profile": [[-5.0, -5.0], [-5.0, 5.0], [5.0, 5.0], [5.0, -5.0]],
            }
        ],
    )
    extrusion = plan_family(document).extrusions[0]
    assert extrusion.curves[0].start_mm == pytest.approx((5.0, -5.0, 0.0))


def test_pin_along_x_keeps_the_step_axes() -> None:
    document = _part(
        filename="pin.step",
        box_min=(0.0, -5.0, -5.0),
        box_max=(40.0, 5.0, 5.0),
        parameters=[
            {
                "name": "Cylinder1Diameter",
                "value": 10.0,
                "unit": "mm",
                "kind": "length",
            },
            {"name": "Cylinder1Length", "value": 40.0, "unit": "mm", "kind": "length"},
        ],
        features=[
            {
                "id": "cylinder_1",
                "type": "cylinder",
                "solid_id": "solid_1",
                "origin": [0.0, 0.0, 0.0],
                "axis": [1.0, 0.0, 0.0],
                "diameter": {"parameter": "Cylinder1Diameter"},
                "length": {"parameter": "Cylinder1Length"},
            }
        ],
    )
    extrusion = plan_family(document).extrusions[0]
    assert extrusion.plane_x == pytest.approx((0.0, 1.0, 0.0))
    assert extrusion.plane_y == pytest.approx((0.0, 0.0, 1.0))
    assert extrusion.axis == pytest.approx((1.0, 0.0, 0.0))
    box = planned_bounding_box(plan_family(document))
    assert box["min"] == pytest.approx([0, -5, -5])
    assert box["max"] == pytest.approx([40, 5, 5])


def test_bad_documents_name_the_path(tmp_path: Path) -> None:
    extra = {**SHANK, "vendor": "ignored"}
    extra["units"] = {**SHANK["units"], "angle": "rad"}
    assert plan_family(extra).parameters[0].name == "ShankDiameter"

    cone = copy.deepcopy(SHANK)
    cone["features"][0]["type"] = "cone"
    with pytest.raises(FamilyBuildError, match="part.json") as error:
        plan_family(cone, document_path="part.json")
    assert error.value.reason
    assert "shank" in error.value.reason
    assert "cone" in error.value.reason

    zero = copy.deepcopy(SHANK)
    zero["parameters"][1]["value"] = 0
    with pytest.raises(FamilyBuildError, match="not positive"):
        plan_family(zero, document_path="shank.json")

    missing = tmp_path / "missing.json"
    with pytest.raises(FamilyBuildError, match="missing.json") as missing_error:
        load_neutral_document(missing)
    assert "cannot read" in missing_error.value.reason

    broken = tmp_path / "broken.json"
    broken.write_text("{", encoding="utf-8")
    with pytest.raises(FamilyBuildError, match="broken.json") as broken_error:
        load_neutral_document(broken)
    assert "not JSON" in broken_error.value.reason

    array = tmp_path / "array.json"
    array.write_text("[]", encoding="utf-8")
    with pytest.raises(FamilyBuildError, match="not a JSON object"):
        load_neutral_document(array)

    degenerate = _part(
        filename="flat.step",
        box_min=(0.0, 0.0, 0.0),
        box_max=(2.0, 1.0, 1.0),
        parameters=[
            {"name": "Extrusion1Length", "value": 1.0, "unit": "mm", "kind": "length"},
        ],
        features=[
            {
                "id": "extrusion_1",
                "type": "extrusion",
                "solid_id": "solid_1",
                "origin": [0.0, 0.0, 0.0],
                "axis": [0.0, 0.0, 1.0],
                "length": {"parameter": "Extrusion1Length"},
                "profile": [[0.0, 0.0], [1.0, 0.0], [2.0, 0.0]],
            }
        ],
    )
    with pytest.raises(FamilyBuildError, match="extrusion_1") as degenerate_error:
        plan_family(degenerate, document_path="flat.json")
    assert "degenerate" in degenerate_error.value.reason


def test_execute_plan_binds_parameters(tmp_path: Path) -> None:
    plan = plan_family(SHANK)
    session = RecordingSession()
    execute_plan(
        plan,
        session,
        template_path="C:/Templates/Metric Generic Model.rft",
        output_path="shank.rfa",
    )
    kinds = [event[0] for event in session.events]
    assert kinds == ["open", "parameter", "parameter", "extrusion", "save"]
    assert session.events[1][1:] == ("ShankDiameter", pytest.approx(mm_to_feet(10)))
    assert session.events[2][1:] == ("ShankLength", pytest.approx(mm_to_feet(40)))
    extrusion = session.events[3][1]
    assert extrusion["solid"] is True
    assert extrusion["length_parameter"] == "ShankLength"
    assert extrusion["diameter_parameter"] == "ShankDiameter"
    assert extrusion["length_feet"] == pytest.approx(mm_to_feet(40))
    assert extrusion["curves"][0][0] == "arc"
    assert extrusion["curves"][0][5] == pytest.approx(mm_to_feet(5))
    assert "close" not in kinds

    resized = with_parameter_values(plan, {"ShankLength": 80, "ShankDiameter": 20})
    resized_session = RecordingSession()
    execute_plan(
        resized,
        resized_session,
        template_path="template.rft",
        output_path="resized.rfa",
    )
    resized_extrusion = resized_session.events[3][1]
    assert resized_extrusion["length_feet"] == pytest.approx(mm_to_feet(80))
    assert resized_extrusion["curves"][0][5] == pytest.approx(mm_to_feet(10))

    failed = RecordingSession(fail_at="extrusion")
    with pytest.raises(RuntimeError, match="extrusion failed"):
        execute_plan(
            plan,
            failed,
            template_path="template.rft",
            output_path=str(tmp_path / "missed.rfa"),
        )
    assert [event[0] for event in failed.events] == [
        "open",
        "parameter",
        "parameter",
        "close",
    ]
    assert not (tmp_path / "missed.rfa").exists()


def test_template_search_prefers_a_newer_metric_generic_model(tmp_path: Path) -> None:
    older = _template(tmp_path, "2024")
    newer = _template(tmp_path, "2026")
    older.write_text("old", encoding="utf-8")
    newer.write_text("new", encoding="utf-8")
    assert resolve_template(None, tmp_path) == os.fspath(newer)
    explicit = tmp_path / "custom.rft"
    explicit.write_text("custom", encoding="utf-8")
    assert resolve_template(os.fspath(explicit), tmp_path) == os.fspath(explicit)
    with pytest.raises(FamilyBuildError, match="missing.rft"):
        resolve_template(os.fspath(tmp_path / "missing.rft"), tmp_path)
    assert template_candidates(tmp_path)
    names = template_candidates(tmp_path)
    assert all(path.endswith("Metric Generic Model.rft") for path in names)


def test_build_family_does_not_write_without_revit(tmp_path: Path) -> None:
    document = tmp_path / "shank.json"
    document.write_text(json.dumps(SHANK), encoding="utf-8")
    output = tmp_path / "shank.rfa"
    output.write_bytes(b"keep")
    template = tmp_path / "Metric Generic Model.rft"
    template.write_text("not a revit template", encoding="utf-8")

    with pytest.raises(FamilyBuildError, match="Revit is not running"):
        build_family(document, output, template, None)
    assert output.read_bytes() == b"keep"

    class FakeApp:
        def NewFamilyDocument(self, _path: str):
            raise AssertionError("the Revit API is not installed here")

    with pytest.raises(FamilyBuildError, match="Revit API is not available"):
        build_family(document, output, template, FakeApp())
    assert output.read_bytes() == b"keep"

    bad = tmp_path / "bad.json"
    bad.write_text('{"schema_version": "2"}', encoding="utf-8")
    with pytest.raises(FamilyBuildError, match="bad.json") as error:
        build_family(bad, output, template, FakeApp())
    assert "schema_version" in error.value.reason
    assert output.read_bytes() == b"keep"

    with pytest.raises(FamilyBuildError, match="family template was not found"):
        build_family(document, output, tmp_path / "missing.rft", None)
    assert output.read_bytes() == b"keep"

    wrong_suffix = tmp_path / "out.txt"
    with pytest.raises(FamilyBuildError, match="must end in .rfa"):
        build_family(document, wrong_suffix, template, None)
    assert not wrong_suffix.exists()

    with pytest.raises(FamilyBuildError, match="output directory"):
        build_family(document, tmp_path / "missing" / "out.rfa", template, None)


def test_revit_session_refuses_to_open_without_the_api(tmp_path: Path) -> None:
    session = RevitFamilySession(object(), "part.json")
    with pytest.raises(FamilyBuildError, match="Revit API is not available"):
        session.open_template(str(tmp_path / "template.rft"))
    assert list(tmp_path.iterdir()) == []


def test_parser_documents_plan_to_the_part_box(tmp_path: Path) -> None:
    samples = [
        write_cylinder(tmp_path / "shank.step"),
        write_cylinder_along_x(tmp_path / "pin.step"),
        write_box(tmp_path / "box.step"),
        write_plate_with_hole(tmp_path / "plate.step"),
        write_blind_hole(tmp_path / "blind.step"),
        write_two_boxes(tmp_path / "pair.step"),
    ]
    for step in samples:
        document = parse_step(step)
        plan = plan_family(document, document_path=step.name)
        box = planned_bounding_box(plan)
        assert box is not None
        assert box["min"] == pytest.approx(document["bounding_box"]["min"], abs=0.1)
        assert box["max"] == pytest.approx(document["bounding_box"]["max"], abs=0.1)
        assert [item.name for item in plan.parameters] == [
            item["name"] for item in document["parameters"]
        ]
        assert [item.value_mm for item in plan.parameters] == pytest.approx(
            [item["value"] for item in document["parameters"]]
        )
        assert plan.template_name == "Metric Generic Model.rft"
        assert plan.in_place is False
        seen_hole = False
        for extrusion in plan.extrusions:
            if extrusion.feature_type == "hole":
                seen_hole = True
                assert extrusion.solid is False
                assert len(extrusion.curves) == 2
                assert all(isinstance(curve, SketchArc) for curve in extrusion.curves)
            else:
                assert seen_hole is False
                assert extrusion.solid is True
            if extrusion.feature_type == "extrusion":
                assert len(extrusion.curves) >= 3
                assert all(isinstance(curve, SketchLine) for curve in extrusion.curves)
            if extrusion.feature_type == "cylinder":
                assert len(extrusion.curves) == 2
                assert all(isinstance(curve, SketchArc) for curve in extrusion.curves)


def test_builder_import_does_not_load_the_step_kernel() -> None:
    code = (
        "import sys\n"
        "import step2revit\n"
        "assert 'OCP' not in sys.modules\n"
        "from step2revit import plan_family, FamilyBuildError, build_family\n"
        "assert 'OCP' not in sys.modules\n"
        "assert 'Autodesk' not in sys.modules\n"
        "assert plan_family.__name__ == 'plan_family'\n"
        "assert FamilyBuildError.__name__ == 'FamilyBuildError'\n"
        "assert build_family.__name__ == 'build_family'\n"
        "from step2revit import parse_step\n"
        "assert 'OCP' in sys.modules\n"
        "assert callable(parse_step)\n"
    )
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + env.get("PYTHONPATH", "")
    completed = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr


def test_script_says_it_must_run_inside_revit() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    head = "\n".join(text.splitlines()[:12])
    assert "inside Revit" in head
    assert "Windows" in head
    assert "GitHub Actions" in head
    assert "does not generate a .rfa" in head
    assert "parse_step" not in text
    assert "OCP" not in text
    assert "urllib" not in text
    assert "requests" not in text
    assert _is_ignored(
        "revit/STEP2Revit.extension/STEP2Revit.tab/Build.panel/"
        "BuildFamily.pushbutton/script.py"
    ) is False
    for name in ("family_plan.py", "family_session.py", "revit_host.py"):
        source = (ROOT / "src" / "step2revit" / name).read_text(encoding="utf-8")
        assert "urllib" not in source
        assert "requests" not in source
        assert "httpx" not in source
        assert "STEPControl" not in source


def _part(*, filename, box_min, box_max, parameters, features) -> dict:
    return {
        "schema_version": "1",
        "units": {"length": "mm"},
        "source": {
            "filename": filename,
            "format": "STEP",
            "length_unit": "millimetre",
        },
        "bounding_box": {"min": list(box_min), "max": list(box_max)},
        "extents": {
            "x": box_max[0] - box_min[0],
            "y": box_max[1] - box_min[1],
            "z": box_max[2] - box_min[2],
        },
        "solids": [
            {
                "id": "solid_1",
                "bounding_box": {"min": list(box_min), "max": list(box_max)},
            }
        ],
        "parameters": parameters,
        "features": features,
    }


def _template(root: Path, version: str) -> Path:
    path = (
        root
        / "Autodesk"
        / f"RVT {version}"
        / "Family Templates"
        / "English"
        / "Metric Generic Model.rft"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
