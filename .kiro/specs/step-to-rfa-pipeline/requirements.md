# STEP to parametric Revit family

Requirements only. `design.md` and `tasks.md` are intentionally absent, so this scaffold does not prescribe an implementation. Later changes follow this file as the contract between the STEP parser and the Revit family builder.

## Introduction

STEP2Revit accepts one STEP hardware part (a bolt, bracket, or fitting, including a SolidWorks part exported to STEP) and produces one loadable parametric Revit family. The parser and the builder meet only through a neutral JSON document. The document carries the solids, the bounding dimensions, and the key features and parameters that drive the family.

## Glossary

- **Parser**: the cross-platform Python component that reads a STEP file and writes the neutral JSON document.
- **Neutral document**: the JSON document defined in this spec. Schema version `"1"`.
- **Builder**: the component that reads a neutral document and writes one `.rfa`. It runs inside Revit on Windows.
- **Part**: one STEP file, treated as a single family even when it contains several solids. Mates and motion are out of scope.
- **Feature**: a parametric shape the builder can construct: a cylinder, a hole, or an extrusion.
- **Parameter**: a named length the family exposes. Feature sizes refer to parameters by name.
- **Length**: a value in millimetres.

## Constraints

- The parser runs on Python 3.11 or newer on Windows, macOS, and Linux. It does not require SolidWorks or Revit to be installed.
- The builder runs inside the user's Revit on Windows, as a pyRevit or Revit API script. It reads the neutral document and does not read STEP.
- Libraries and automation added for either side are free and open source. The pipeline does not call a paid API or a proprietary geometry kernel. Revit is the host application already on the builder machine; the project does not wrap it in a paid web service.

## Requirements

### Requirement 1: Accept one STEP part

**User story:** As a Revit user, I want to hand over a STEP file of a bolt, bracket, or fitting, so that I do not redraw it.

#### Acceptance criteria

1. WHEN the parser is given a readable STEP physical file (ISO 10303-21) whose schema is AP203, AP214, or AP242, with a file name ending in `.step` or `.stp`, THE SYSTEM SHALL treat that file as one part.
2. WHEN the parser writes a neutral document, THE SYSTEM SHALL include every solid from that part, including a multi-solid part exported as one static body.
3. THE SYSTEM SHALL read the STEP coordinate values in the file's own right-handed axes and SHALL NOT swap or rebase those axes.
4. IF the input path is missing, unreadable, or not a STEP physical file of schema AP203, AP214, or AP242, THEN THE SYSTEM SHALL fail the conversion without writing a neutral document or a family, and the failure SHALL name the input path and the reason.
5. IF the file contains no solids, THEN THE SYSTEM SHALL fail the conversion without writing a neutral document or a family, and the failure SHALL state that no solids were found.
6. IF the STEP length unit cannot be determined, THEN THE SYSTEM SHALL fail the conversion without writing a neutral document or a family, and the failure SHALL state that the length unit is unknown.

### Requirement 2: Write one neutral document

**User story:** As a developer, I want a single JSON contract between the parser and the builder, so that the two sides can change independently.

#### Acceptance criteria

1. WHEN the parser has read a supported STEP part, has determined its length unit, and can record at least one supported feature, and an output path is given, THE SYSTEM SHALL write exactly one UTF-8 JSON document to that path.
2. WHEN the document is written, THE SYSTEM SHALL set `schema_version` to `"1"`, `units.length` to `"mm"`, and every length in the document to millimetres.
3. WHEN the source file uses a known length unit other than millimetres, THE SYSTEM SHALL convert lengths to millimetres and SHALL record the source unit name in `source.length_unit`.
4. THE SYSTEM SHALL include `source.filename`, `source.format` equal to `"STEP"`, the part `bounding_box`, the part `extents`, the `solids` array, the `parameters` array, and the `features` array, as defined in the neutral document contract below.
5. WHEN a solid is recorded, THE SYSTEM SHALL give it a stable `id` unique among solids and an axis-aligned bounding box tight to that solid.
6. IF the builder is given a document whose `schema_version` is not `"1"`, or which omits a required field, THEN THE SYSTEM SHALL fail without writing a family, and the failure SHALL name the document path and the reason.

### Requirement 3: Keep the document internally consistent

**User story:** As a developer, I want the bounding data to be checkable, so that a bad export fails before it becomes a family.

#### Acceptance criteria

1. WHEN the document is written, `extents.x` SHALL equal `bounding_box.max[0] - bounding_box.min[0]` within 0.001 mm, and the same relation SHALL hold for `y` with index 1 and `z` with index 2.
2. WHEN the document is written, the part bounding box SHALL equal the component-wise union of the solid bounding boxes within 0.001 mm.
3. WHEN the document is written, each solid bounding box SHALL lie inside the part bounding box within 0.001 mm.
4. WHEN a feature has a `solid_id`, THE SYSTEM SHALL use an `id` that exists in `solids`.

### Requirement 4: Record key features and parameters

**User story:** As a Revit user, I want hole diameters, thicknesses, and lengths to be family parameters, so that I can resize the hardware after loading it.

#### Acceptance criteria

1. WHEN the parser writes a neutral document, THE SYSTEM SHALL include at least one feature of type `cylinder`, `hole`, or `extrusion`.
2. WHEN the parser records a cylinder, THE SYSTEM SHALL include `solid_id`, a unit `axis`, `origin`, `diameter`, and `length`. `origin` is the center of one end, and `axis` points toward the other end.
3. WHEN the parser records a hole, THE SYSTEM SHALL include `solid_id` of the solid the hole cuts, a unit `axis` pointing into the material, `origin` at the center of the opening, `diameter`, `depth`, and `through`.
4. WHEN the parser records an extrusion, THE SYSTEM SHALL include `solid_id`, a unit `axis`, `origin`, `length`, and a `profile` of at least three `[u, v]` points in the profile frame defined below.
5. WHEN a feature records `diameter`, `length`, or `depth`, THE SYSTEM SHALL store that size as a parameter reference, and THE SYSTEM SHALL include a matching entry in `parameters` with `kind` `"length"`, `unit` `"mm"`, and the default `value` in millimetres.
6. WHEN the parser names a parameter, THE SYSTEM SHALL build the name from the feature id: split on `_`, uppercase the first character of each segment, leave the rest of the segment unchanged, and append the suffix `Diameter`, `Length`, or `Depth`. WHEN that name is already used, THE SYSTEM SHALL append `2`, `3`, and so on until the name is unique.
7. THE SYSTEM SHALL keep parameter names unique and matching `^[A-Za-z][A-Za-z0-9_]*$`.
8. IF the parser cannot describe the part with at least one feature of type `cylinder`, `hole`, or `extrusion`, THEN THE SYSTEM SHALL fail without writing a neutral document or a family, and the failure SHALL state that no supported features were found.
9. IF a feature `type` is not `cylinder`, `hole`, or `extrusion`, THEN THE SYSTEM SHALL fail without writing a family, and the failure SHALL name the feature id and the type.

### Requirement 5: Build one parametric family from the document alone

**User story:** As a Revit user, I want a loadable `.rfa` whose default shape matches the STEP part, so that I can place the hardware and edit its sizes.

#### Acceptance criteria

1. WHEN the builder is given a valid schema-1 document and an output path, THE SYSTEM SHALL write exactly one loadable Revit family (`.rfa`) to that path.
2. WHEN the family is built, THE SYSTEM SHALL map JSON X, Y, and Z onto the family X, Y, and Z axes in millimetres, with the JSON origin at the family origin.
3. WHEN the family is built, THE SYSTEM SHALL create one family type that exposes every JSON parameter as a length parameter whose default, read back in millimetres, equals the JSON `value` within 0.1 mm.
4. WHEN the family is built at those defaults, THE SYSTEM SHALL construct the geometry from the features, and the family's axis-aligned bounding box SHALL match the JSON `bounding_box` within 0.1 mm on each corner coordinate.
5. WHEN a length parameter changes, THE SYSTEM SHALL change the feature size that references that parameter.
6. WHEN the builder reads a document, THE SYSTEM SHALL ignore unknown JSON keys, SHALL NOT read a STEP file, and SHALL NOT call a network service.
7. THE FAMILY SHALL be a loadable Generic Model, not an in-place family.

### Requirement 6: Stay free and open source

**User story:** As a contributor, I want the pipeline to depend only on free and open-source libraries, so that the project can be built and judged without a paid converter.

#### Acceptance criteria

1. THE PARSER SHALL be implementable with free and open-source Python libraries.
2. THE BUILDER SHALL be implementable as a pyRevit or Revit API script that runs inside Revit on Windows.
3. THE SYSTEM SHALL NOT require a paid web API, a paid conversion service, or a proprietary geometry kernel.

## Neutral document contract

Lengths are JSON numbers in millimetres. Points and vectors are JSON arrays of three numbers. A direction stored in `axis` is a unit vector (length 1 within 1e-6). A size is either `{"parameter": "<name>"}` or, for a value that is not a feature size, `{"value": <number>}`. `diameter`, `length`, and `depth` on a feature always use the parameter form.

The profile frame for an extrusion: let `A` be the unit axis. If `abs(A[0]) <= 1e-8` and `abs(A[1]) <= 1e-8`, the axis is parallel to world Z. Then `U = (1, 0, 0)`. If `A[2] >= 0`, `V = (0, 1, 0)`; otherwise `V = (0, -1, 0)`. Otherwise `U` is the normalization of the cross product of `(0, 0, 1)` and `A`, and `V` is the cross product of `A` and `U`. A profile point `(u, v)` is the 3D point `origin + u * U + v * V`. The solid is that profile swept from distance 0 through `length` along `A`. The builder closes the profile from the last point to the first. Points are not repeated.

Required top-level keys:

| Key | Type | Rule |
| --- | --- | --- |
| `schema_version` | string | `"1"` |
| `units.length` | string | `"mm"` |
| `source.filename` | string | STEP file name only, with no directory |
| `source.format` | string | `"STEP"` |
| `source.length_unit` | string | Unit name from the STEP file, before conversion |
| `bounding_box.min` / `max` | `[x, y, z]` | Axis-aligned box of the final part |
| `extents.x` / `y` / `z` | number | Size of that box on each axis |
| `solids` | array | At least one solid |
| `parameters` | array | One entry per exposed length |
| `features` | array | At least one supported feature |

Each solid requires `id` (non-empty string, unique in `solids`) and `bounding_box`. `name` is optional.

Each parameter requires `name`, `value`, `unit` (`"mm"`), and `kind` (`"length"`).

Each feature requires `id` (unique in `features`, matching `^[a-z][a-z0-9_]*$`), `type`, and `solid_id`.

| Type | Required fields besides `id`, `type`, `solid_id` |
| --- | --- |
| `cylinder` | `origin`, `axis`, `diameter`, `length` |
| `hole` | `origin`, `axis`, `diameter`, `depth`, `through` (boolean) |
| `extrusion` | `origin`, `axis`, `length`, `profile` (array of `[u, v]`, length at least 3) |

`origin` on a cylinder, hole, or extrusion may be a literal point. Schema 1 does not require hole position to be a parameter. On a hole, `through` is true when the opening exits the solid. `depth` is the distance from `origin` along `axis` to the closed end, or to the exit face when `through` is true.

## Worked example

A 10 mm by 40 mm shank centered on the Z axis. `extents` are the box size, not the diameter. Feature ids and solid ids are separate namespaces; this example reuses the word `shank` in both. This object is valid schema 1.

```json
{
  "schema_version": "1",
  "units": {"length": "mm"},
  "source": {
    "filename": "shank.step",
    "format": "STEP",
    "length_unit": "millimetre"
  },
  "bounding_box": {"min": [-5.0, -5.0, 0.0], "max": [5.0, 5.0, 40.0]},
  "extents": {"x": 10.0, "y": 10.0, "z": 40.0},
  "solids": [
    {
      "id": "shank",
      "bounding_box": {"min": [-5.0, -5.0, 0.0], "max": [5.0, 5.0, 40.0]}
    }
  ],
  "parameters": [
    {"name": "ShankDiameter", "value": 10.0, "unit": "mm", "kind": "length"},
    {"name": "ShankLength", "value": 40.0, "unit": "mm", "kind": "length"}
  ],
  "features": [
    {
      "id": "shank",
      "type": "cylinder",
      "solid_id": "shank",
      "origin": [0.0, 0.0, 0.0],
      "axis": [0.0, 0.0, 1.0],
      "diameter": {"parameter": "ShankDiameter"},
      "length": {"parameter": "ShankLength"}
    }
  ]
}
```

A plate extruded along Z uses the parallel-axis frame, so profile `(u, v)` is world `(u, v)` at `origin`. A plate extruded along X uses `U = (0, 1, 0)` and `V = (0, 0, 1)`, so profile `(u, v)` is world `(0, u, v)` at `origin`.

## Out of scope

- Reading SLDPRT, IPT, SAT, IFC, or any file that is not STEP AP203, AP214, or AP242.
- Nested families, mates, joints, and motion.
- Drawings, PMI, GD&T, layers, materials, and textures.
- MEP connectors and editing an existing `.rfa` back into STEP.
- How a later change recognizes a hole or chooses a geometric kernel. Those choices have to emit this document; they are not specified here.

## Evolution

Additive unknown keys are allowed. Removing a required field, renaming a required field, or changing the meaning of a feature type requires a new `schema_version`. The builder rejects versions it does not implement.
