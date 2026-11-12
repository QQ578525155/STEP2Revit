# STEP parser

This file records how the parser produces the schema-1 document in `requirements.md`. It does not add JSON fields. The family builder is recorded in `builder.md`. It still only reads that document, inside Revit on Windows.

## Kernel

The parser depends on `cadquery-ocp` (import name `OCP`, Apache-2.0). That package binds Open CASCADE Technology. pythonOCC and CadQuery are allowed alternatives and are not required. The reader sets `xstep.cascade.unit` to `MM` before every file, so coordinates come back in millimetres on the file's own right-handed axes. Nothing is swapped or rebased.

CI installs `cadquery-ocp` (and the VTK wheel it declares) with the package. Tests do not open a display and do not call the network.

## Which files are accepted

The path must name a file ending in `.step` or `.stp`. The header must be an ISO 10303-21 physical file whose `FILE_SCHEMA` contains one of `CONFIG_CONTROL_DESIGN` (AP203), `AUTOMOTIVE_DESIGN` (AP214), `AP203`, `AP214`, or `AP242`. Anything else fails before a document is written, and the error names the path.

## Length unit

After the solids are read, the length unit is the single name reported by the STEP reader's file units for the geometric context. Examples from Open CASCADE: `millimetre`, `metre`, `centimetre`, `micrometre`, `INCH`, `FOOT`. That string is stored in `source.length_unit` unchanged. If the name is missing or two different names are reported, the conversion fails with the reason that the length unit is unknown, and no document is written.

Geometry is not scaled a second time. The millimetre coordinates are the ones Open CASCADE returns for `xstep.cascade.unit = MM`.

## Solids

Every solid in the transferred shape is kept, including a multi-solid file exported as one static body. A closed shell that Open CASCADE did not promote to a solid is not invented into one. Solids are ordered by the minimum corner of the axis-aligned box, then the maximum corner, and named `solid_1`, `solid_2`, and so on. Optional `name` is omitted. The part box is the component-wise union of those solid boxes. Boxes come from the exact Open CASCADE bounding box, rounded to 6 decimal places of a millimetre (0.000001 mm).

## Features the parser emits

A part must yield at least one feature. Otherwise the conversion fails and states that no supported features were found.

Recognition is limited to the shapes below. Fillets, chamfers, cones, spheres, freeform faces, and non-circular cutouts are not features. A solid that still has another recognized feature is kept in `solids`; a part with none of the shapes below fails.

### Cylinder

One full-turn external cylindrical surface (a seam split into faces is joined when the pieces share an axis and a radius and their angle spans sum to a full turn). Every other face is either a plane perpendicular to that axis or a hole as defined below. `origin` is the center of the end whose axis, pointing at the other end, has a positive dominant component (ties prefer Z, then Y, then X). `diameter` and `length` become parameters.

### Hole

A full-turn cylindrical surface whose interior (half the radius, midway along the face) is outside the solid and whose exterior is inside the solid. `origin` is the center of an opening. `axis` points into the material: toward the closed end of a blind hole, or, for a through hole, toward the other opening with the same positive-dominant rule as a cylinder. `depth` is the distance between the two ends. `through` is false when one end is a planar disk of the hole radius, and true when both ends are open. `diameter` and `depth` become parameters. A cylindrical void with no opening is not a hole.

### Extrusion

A right prism: two planar caps perpendicular to one axis, one face on each cap plane, and every other face either a plane parallel to that axis or a hole. Among the axes that fit, the parser uses the shortest. Equal lengths prefer the axis closest to +Z, then +Y, then +X. The profile is the outer wire of the start cap (line edges only), in the profile frame from `requirements.md`, wound counter-clockwise around the axis, with `origin` at the polygon centroid. The start cap is the end the axis points away from. `length` is the distance between the cap planes and becomes a parameter. Profile coordinates stay literal numbers; width and height are not parameters in schema 1.

### Identifiers

Feature ids are `cylinder_N`, `extrusion_N`, and `hole_N`. Each type has its own counter, and the counter runs through the part in solid order. Within a solid the body feature is emitted before that solid's holes, and holes are ordered by origin then diameter. Parameter names follow the rule in `requirements.md`: `cylinder_1` with a diameter is `Cylinder1Diameter`. A second feature that would produce the same name gets `2`, then `3`, appended.

## Failure order

1. Extension, missing path, or unreadable path.
2. Not an accepted STEP physical file.
3. Geometry that cannot be transferred.
4. No solids.
5. Length unit missing or ambiguous.
6. No supported features.
7. The assembled document fails its own consistency checks.

Each failure names the input path and the reason, and does not write a document.

## Samples

Tests build box, cylinder, and plate-with-hole solids at runtime with Open CASCADE primitives and write STEP through the same kernel. The generator is `tests/step_samples.py`, MIT, same as this repository. No third-party STEP file is downloaded or committed. See `tests/NOTICE`.
