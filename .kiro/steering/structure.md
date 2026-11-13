---
inclusion: always
---

# Repository structure

```text
.kiro/                  Committed Kiro project. Do not gitignore this tree.
  steering/             Product, technology, and structure guidance.
  specs/                Pipeline requirements later changes follow.
  hooks/                Hook definitions (JSON schema v1).
src/step2revit/         Importable package.
tests/                  pytest modules.
.github/workflows/      CI.
pyproject.toml          Package metadata and pytest/ruff settings.
```

- `.kiro/` and every file under it stay tracked. The Python gitignore pattern `*.spec` matches file names that end in `.spec`. It does not match the `.kiro/specs/` directory. Trailing `!.kiro/` and `!.kiro/**` rules in `.gitignore` keep the tree tracked if a broader rule is added later.
- Parser and builder code, when added, lives in `src/step2revit/` and exchanges only the neutral JSON defined in `.kiro/specs/step-to-rfa-pipeline/requirements.md`.
- `LICENSE` stays the MIT license already in the repo.
