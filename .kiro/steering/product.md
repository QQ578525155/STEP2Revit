---
inclusion: always
---

# Product

STEP2Revit turns a hardware part exported as STEP into a parametric Revit family (`.rfa`). The parts in scope are bolts, brackets, and fittings, including parts modeled in SolidWorks and exported to STEP. The person using it already has the solid and needs a loadable family whose key sizes are Revit parameters.

The pipeline has three stages:

1. Read one STEP part.
2. Write one neutral JSON document that records the solids, the bounding dimensions, and the key features and parameters.
3. Build one parametric `.rfa` from that JSON document alone.

The JSON document is the only hand-off between the parser and the family builder. Both sides follow `.kiro/specs/step-to-rfa-pipeline/requirements.md`. This scaffold does not implement either side.

The project is MIT-licensed and is entered in the Devpost Kiroween 2026 hackathon, Frankenstein category. Kiro project files under `.kiro/` are part of the product and stay in git.
