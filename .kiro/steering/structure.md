---
inclusion: always
---

# Repository structure

```text
.kiro/                  Committed Kiro project. Do not gitignore this tree.
  steering/             Product, technology, and structure guidance.
  specs/                Pipeline requirements later changes follow.
  hooks/                Hook definitions (JSON schema v1).
src/step2revit/         Importable package. The parser lives here.
tests/                  pytest modules, including STEP samples generated at runtime.
  NOTICE                License of those generated samples.
.github/workflows/      CI.
pyproject.toml          Package metadata and pytest/ruff settings.
```

- `.kiro/` and every file under it stay tracked. The Python gitignore pattern `*.spec` matches file names that end in `.spec`. It does not match the `.kiro/specs/` directory. Trailing `!.kiro/` and `!.kiro/**` rules in `.gitignore` keep the tree tracked if a broader rule is added later.
- Parser code lives in `src/step2revit/` and writes only the neutral JSON defined in `.kiro/specs/step-to-rfa-pipeline/requirements.md`. The family builder, when added, reads that same document.
- `LICENSE` stays the MIT license already in the repo.
