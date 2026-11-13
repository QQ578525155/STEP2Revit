---
inclusion: always
---

# Repository structure

```text
.kiro/                  Committed Kiro project. Do not gitignore this tree.
  steering/             Product, technology, and structure guidance.
  specs/                Pipeline requirements later changes follow.
  hooks/                Hook definitions (JSON schema v1).
src/step2revit/         Importable package. The parser and the family plan live here.
  family_plan.py        Headless plan: template, sketches, and parameters.
  family_session.py     Applies a plan through a session that is not Revit.
  revit_host.py         Revit API session. Imports Revit only when building.
revit/STEP2Revit.extension/
                        pyRevit button. Runs inside Revit on Windows.
tests/                  pytest modules, including STEP samples generated at runtime.
  NOTICE                License of those generated samples. Family tests do not launch Revit.
.github/workflows/      CI.
pyproject.toml          Package metadata and pytest/ruff settings.
```

- `.kiro/` and every file under it stay tracked. The Python gitignore pattern `*.spec` matches file names that end in `.spec`. It does not match the `.kiro/specs/` directory. Trailing `!.kiro/` and `!.kiro/**` rules in `.gitignore` keep the tree tracked if a broader rule is added later.
- Parser code lives in `src/step2revit/` and writes only the neutral JSON defined in `.kiro/specs/step-to-rfa-pipeline/requirements.md`. The family builder reads that same document. Its Revit calls live in `revit_host.py` and `revit/STEP2Revit.extension`, and they run inside Revit on Windows.
- `LICENSE` stays the MIT license already in the repo.
