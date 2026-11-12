"""Scaffold checks: the package imports, and .kiro stays tracked."""

from __future__ import annotations

import json
import re
import subprocess
import tomllib
from pathlib import Path

import step2revit

ROOT = Path(__file__).resolve().parents[1]

KIRO_PATHS = (
    ".kiro",
    ".kiro/steering/product.md",
    ".kiro/steering/tech.md",
    ".kiro/steering/structure.md",
    ".kiro/specs/step-to-rfa-pipeline/requirements.md",
    ".kiro/hooks/foss-and-kiro-tracking.json",
)


def test_package_imports() -> None:
    with (ROOT / "pyproject.toml").open("rb") as handle:
        project = tomllib.load(handle)["project"]

    assert step2revit.__version__ == "0.1.0"
    assert project["name"] == "step2revit"
    assert project["version"] == step2revit.__version__
    assert project["requires-python"] == ">=3.11"


def test_kiro_exists_and_is_not_gitignored() -> None:
    for relative in KIRO_PATHS:
        assert (ROOT / relative).exists(), relative
        assert _is_ignored(relative) is False, relative

    # A known Python-template ignore still matches, so a passing check-ignore
    # result is meaningful.
    assert _is_ignored(".pytest_cache/cache") is True

    rules = _gitignore_rules()
    kiro_rules = [rule for rule in rules if ".kiro" in rule]
    assert kiro_rules == ["!.kiro/", "!.kiro/**"]

    requirements = (
        ROOT / ".kiro" / "specs" / "step-to-rfa-pipeline" / "requirements.md"
    ).read_text(encoding="utf-8")
    assert "schema_version" in requirements
    assert "THE SYSTEM SHALL" in requirements

    for name in ("product.md", "tech.md", "structure.md"):
        text = (ROOT / ".kiro" / "steering" / name).read_text(encoding="utf-8")
        assert text.startswith("---\ninclusion: always\n---\n"), name

    hook = json.loads(
        (ROOT / ".kiro" / "hooks" / "foss-and-kiro-tracking.json").read_text(
            encoding="utf-8"
        )
    )
    assert hook["version"] == "v1"
    by_trigger = {item["trigger"]: item for item in hook["hooks"]}
    assert set(by_trigger) == {"SessionStart", "PostFileSave"}
    for item in by_trigger.values():
        assert item["name"]
        assert item["action"]["type"] == "agent"
        assert item["action"]["prompt"]

    matcher = by_trigger["PostFileSave"]["matcher"]
    assert re.search(matcher, ".gitignore")
    assert re.search(matcher, "repo/.gitignore")
    assert re.search(matcher, "C:\\repo\\.gitignore")
    assert re.search(matcher, ".gitignore.bak") is None
    assert re.search(matcher, "src/app.py") is None


def _is_ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", "--", path],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode in {0, 1}, result.stderr
    return result.returncode == 0


def _gitignore_rules() -> list[str]:
    rules: list[str] = []
    for raw in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rules.append(line)
    return rules
