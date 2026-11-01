"""Display helpers for model replies."""

from __future__ import annotations

import re

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BOLD = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_ITALIC = re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])")
_STAR_BULLET = re.compile(r"^(\s*)\*\s+", re.MULTILINE)


def strip_markdown(text: str) -> str:
    """Remove markdown emphasis and headings (the chat shows plain text).

    **bold** / __bold__ / *italic* keep their text; "# Title" loses the hashes;
    "* item" bullets become "- item". Underscore italics are left alone, so
    names like snake_case or e-mail addresses are never altered.
    """
    text = _HEADING.sub("", text)
    text = _BOLD.sub(r"\2", text)
    text = _STAR_BULLET.sub(r"\1- ", text)
    return _ITALIC.sub(r"\1", text)
