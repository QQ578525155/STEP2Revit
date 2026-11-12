# Revit family builder

This file records how the builder turns the schema-1 document in `requirements.md` into one loadable Generic Model family. It does not add JSON fields. `design.md` is the parser. The builder does not read STEP.

## Where it runs

`step2revit.family_plan` and `step2revit.family_session` are pure Python. pytest and ruff run them on Linux in GitHub Actions. They do not import the Revit API and do not write a `.rfa`.

`revit/STEP2Revit.extension/.../BuildFamily.pushbutton/script.py` and `step2revit.revit_host` run inside the user's Revit on Windows, as a pyRevit script or from Revit's Python shell. The host imports `Autodesk.Revit.DB` only when `build_family` is called with a Revit application.

Revit is not installed in GitHub Actions or in the cloud environment used to develop this repository. Nothing in CI produces a `.rfa`. pyRevit is the free, open-source host. The builder does not call a paid API or a network service.

Importing `step2revit` does not import the STEP kernel. The kernel loads only when `parse_step` is used, so Revit's Python does not need `cadquery-ocp` to build a family from JSON.

## Template

The plan names `Metric Generic Model.rft`. The family category is Generic Model (`OST_GenericModel`). The document is a loadable family, not an in-place family. The host uses the template's current type and does not add another type unless the template has none, in which case it adds one type named `STEP2Revit`.

The script looks for the English template under `%ProgramData%\Autodesk\RVT <year>\Family Templates\`. `STEP2REVIT_TEMPLATE` overrides that search. Localized template file names are not guessed.

## Units and axes

The plan stays in millimetres. The session receives Revit internal units, the international foot: millimetres divided by 304.8. JSON X, Y, and Z map onto the family X, Y, and Z axes. The JSON origin is the family origin. Nothing is swapped.

## Geometry

Each feature becomes one extrusion on the plane whose origin is the feature origin and whose normal is the feature axis. The profile frame is the one in `requirements.md`.

- A cylinder is a solid extrusion of two semicircular arcs. A single arc from 0 to 2π is not used, because its start and end are the same point and Revit rejects that curve. Diameter and length are parameters.
- An extrusion is a solid extrusion of the closed profile. Profile coordinates stay literal numbers. A clockwise profile is reversed so the loop is counter-clockwise around the axis. Length is a parameter.
- A hole is a void extrusion (`isSolid` false) of two semicircles. Diameter and depth are parameters. `through` is recorded on the plan. Blind and through holes both use `depth` as the void length.

Solids are created before voids, so a hole cuts the body even when the JSON lists the hole first. Relative order inside each group follows the document.

## Parameters

Every JSON parameter becomes a family type length (`isInstance` false) in the Geometry group. The default is the JSON value, converted to internal feet.

The host associates the extrusion's end parameter with the length or depth parameter. It tries `EXTRUSION_END_PARAM`, then `EXTRUSION_DEPTH_PARAM`, then `EXTRUSION_LENGTH`, and uses the first one Revit will associate. That is what makes a later edit of the type parameter change the extrusion distance.

For a circle, the host labels a diameter dimension with the diameter parameter. If that dimension is rejected, the host adds `<Name>_Radius` with the formula `<Name> / 2` and labels a radial dimension. Editing the JSON diameter parameter still changes the circle. The radius parameter is only the fallback.

`with_parameter_values` is the headless counterpart. It returns a new plan whose extrusion distances and circle radii follow the new millimetre values. CI checks that. It does not open Revit.

## Failures

`FamilyBuildError` names the path and the reason. A document whose `schema_version` is not `"1"`, a missing required field, an unknown feature type, a non-positive size, a missing template, or a Revit error all fail this way. The host closes the open family without `SaveAs`. An existing file at the output path is left untouched. The output path must end in `.rfa`.

## Out of scope here

The bilingual demo walkthrough and the 3-minute video. Running Revit in CI. Nested families, materials, connectors, and editing an existing `.rfa` back into STEP, which `requirements.md` already excludes.
