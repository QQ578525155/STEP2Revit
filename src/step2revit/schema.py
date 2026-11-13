"""STEP physical-file header checks for AP203, AP214, and AP242.

This module only looks at the ISO 10303-21 header. Geometry and units are
read by the Open CASCADE STEP reader.
"""

from __future__ import annotations

import re


class SchemaError(Exception):
    """The file is not a STEP part this parser accepts."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


_ACCEPTED_TOKENS = (
    "CONFIG_CONTROL_DESIGN",  # AP203
    "AUTOMOTIVE_DESIGN",  # AP214
    "AP203",
    "AP214",
    "AP242",
)

_SCHEMA_RE = re.compile(
    r"FILE_SCHEMA\s*\(\s*\((.*?)\)\s*\)\s*;",
    re.IGNORECASE | re.DOTALL,
)
_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_NAME_RE = re.compile(r"'([^']*)'")

_REJECTED = (
    "not a STEP physical file of schema AP203, AP214, or AP242"
)


def step_schema_names(text: str) -> list[str]:
    """Return the ``FILE_SCHEMA`` names of one accepted STEP physical file.

    Raises:
        SchemaError: the text is not ISO 10303-21, or its schema is not
            AP203, AP214, or AP242. The message names that reason.
    """

    header = _COMMENT_RE.sub("", text).lstrip("\ufeff \t\r\n")
    if not header.startswith("ISO-10303-21"):
        raise SchemaError(_REJECTED)
    match = _SCHEMA_RE.search(header)
    if match is None:
        raise SchemaError(_REJECTED)
    names = [name.strip() for name in _NAME_RE.findall(match.group(1)) if name.strip()]
    if not names or not any(_accepted(name) for name in names):
        found = ", ".join(names) if names else "none"
        raise SchemaError(f"{_REJECTED} (schema: {found})")
    return names


def _accepted(name: str) -> bool:
    upper = name.upper()
    return any(token in upper for token in _ACCEPTED_TOKENS)
