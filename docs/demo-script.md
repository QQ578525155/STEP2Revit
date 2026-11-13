# STEP2Revit demo script

Devpost Kiroween 2026, Frankenstein category. This file is the read-aloud script. The repository does not contain a video.

Read the voiceover at a steady pace, about 150 words a minute. The voiceover is about 470 words, a little over three minutes. Paths and commands are on screen; say the names, not every punctuation mark. Screen directions are not spoken.

The Revit section is narration of the click path in the README and in `revit/STEP2Revit.extension`. It is not footage of Revit. Revit is not installed in GitHub Actions or in the cloud environment that prepared this demo, so no `.rfa` was generated. Do not present that section as a recording.

The sample on screen is the cylinder `tests/step_samples.py` already builds with `write_cylinder` (radius 5 mm, length 40 mm). The parse command is the one the package ships: `python -m step2revit`.

## 0:00–0:22 — STEP hardware part in

**On screen:** Title card, STEP2Revit. A hardware part named as a STEP file (a bolt shank). Cut to the first paragraph of `README.md`.

**Voiceover:** A bolt, a bracket, or a fitting starts as STEP, the file SolidWorks already exports. STEP2Revit turns that hardware part into a parametric Revit family: one loadable .rfa, with the key sizes as type parameters. The two CAD systems do not share a kernel. A neutral JSON document is the stitch. That is the Frankenstein entry.

## 0:22–0:45 — Spec and hook

**On screen:** `.kiro/specs/step-to-rfa-pipeline/requirements.md`, the line that schema version is `"1"`, and the split between the parser and the builder. Then `.kiro/hooks/foss-and-kiro-tracking.json`, the session-start hook named "Keep .kiro tracked and stay FOSS-only".

**Voiceover:** The contract lives under .kiro, and that tree stays committed. The spec is schema 1. The parser writes the JSON. The builder reads only that document and does not read STEP. The session-start hook keeps all of .kiro in git and allows only free and open-source libraries. No paid API, and no proprietary geometry kernel.

## 0:45–1:21 — Parser on a generated sample

**On screen:** A terminal at the repository root. The editable install from the README is already done. Run the generator the tests use, then the real CLI:

```python
from pathlib import Path
from tests.step_samples import write_cylinder

write_cylinder(Path("shank.step"))
```

```bash
python -m step2revit shank.step shank.json
```

The command exits 0. No `.rfa` appears.

**Voiceover:** This is the parser on a sample the repository generates itself. tests/step_samples.py builds a cylinder with Open CASCADE primitives: radius five millimetres, length forty. Nothing is downloaded. From the repository root, write_cylinder writes shank.step. The command the package already ships is python -m step2revit shank.step shank.json. In Python the same entry is parse_step. The file has to be STEP AP203, AP214, or AP242. Lengths in the JSON are millimetres. source.length_unit keeps the unit name from the STEP file. Continuous integration runs this parse. It does not run Revit.

## 1:21–1:41 — Neutral JSON

**On screen:** `shank.json`. The document also has `bounding_box`, `extents`, and `solids`: `solid_1` spans x and y from -5 to 5 and z from 0 to 40, and the extents are 10, 10, and 40. Hold on the fields below.

```json
{
  "schema_version": "1",
  "units": { "length": "mm" },
  "source": {
    "filename": "shank.step",
    "format": "STEP",
    "length_unit": "millimetre"
  },
  "parameters": [
    { "name": "Cylinder1Diameter", "value": 10.0, "unit": "mm", "kind": "length" },
    { "name": "Cylinder1Length", "value": 40.0, "unit": "mm", "kind": "length" }
  ],
  "features": [
    {
      "id": "cylinder_1",
      "type": "cylinder",
      "solid_id": "solid_1",
      "origin": [0.0, 0.0, 0.0],
      "axis": [0.0, 0.0, 1.0],
      "diameter": { "parameter": "Cylinder1Diameter" },
      "length": { "parameter": "Cylinder1Length" }
    }
  ]
}
```

**Voiceover:** Here is the JSON. schema_version is 1. units.length is mm. One solid. One cylinder, origin at zero, axis along Z. Cylinder1Diameter is ten millimetres. Cylinder1Length is forty. Those names become family type parameters. The builder never opens the STEP file, and importing the package does not load the STEP kernel.

## 1:41–2:49 — In Revit, narrated

**On screen:** A card, held long enough to read: "Not a Revit recording. Revit is not available in CI or in this cloud environment. No .rfa was generated." Then the folder `revit/STEP2Revit.extension` and the comment at the top of `revit/STEP2Revit.extension/STEP2Revit.tab/Build.panel/BuildFamily.pushbutton/script.py`. Then the click path as text: STEP2Revit → Build → Build Family. Then the template name `Metric Generic Model.rft` and the three environment variables `STEP2REVIT_TEMPLATE`, `STEP2REVIT_JSON`, `STEP2REVIT_RFA`. Stay on the repository. Do not cut to a Revit window.

**Voiceover:** Building the family is a click inside Revit on Windows. This stretch is spoken, not filmed. Revit is not installed in GitHub Actions or in the cloud environment that prepared this demo, so no .rfa was generated. Install pyRevit and use its CPython engine, Python 3.11 or newer. Revit's own Python shell on Revit 2025 or newer also works. Into that Python, run python -m pip install -e ., or run the script from this clone. The script adds src to sys.path and does not need cadquery-ocp. Add revit/STEP2Revit.extension as a pyRevit extension and reload. The button is STEP2Revit, then Build, then Build Family. It asks for the schema-1 JSON and the output .rfa path. The template is Metric Generic Model.rft, under ProgramData, Autodesk, RVT year, Family Templates, English. STEP2REVIT_TEMPLATE overrides that file. STEP2REVIT_JSON and STEP2REVIT_RFA skip the prompts. The script extrudes each cylinder, prism, and hole, and binds every JSON length to a type parameter. It does not read STEP, and it does not use the network.

## 2:49–3:08 — MIT, free and open source, the stitch

**On screen:** `LICENSE` (MIT). `.kiro/steering/product.md`: MIT, the Frankenstein category, and `.kiro/` stays in git. End card, three labels: STEP, neutral JSON, parametric `.rfa`.

**Voiceover:** The result is one loadable Generic Model family. The license is MIT. cadquery-ocp is Apache-2.0. pyRevit is free and open source. CI is GitHub Actions. No paid service sits in the pipeline. STEP hardware in, neutral JSON, parametric Revit family out. Two CAD tools, one stitch.
