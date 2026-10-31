"""Extract and split the store policy PDF into top-level sections."""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from pypdf import PdfReader

from emporio.data import RAW_DATA_DIR

POLICY_PDF = RAW_DATA_DIR / "políticas_da_loja.pdf"

# Lines repeated on every page (header, page number, closing tagline).
_NOISE_LINES = [
    re.compile(r"^Empório da Música\s+Manual de Políticas e Procedimentos$"),
    re.compile(r"^Página \d+$"),
    re.compile(r"^Empório da Música — Sua música começa aqui\.$"),
    re.compile(r"^Última atualização:.*$"),
]

# Known errors in the PDF, fixed in the extracted text (data/raw stays untouched).
CORRECTIONS: dict[str, str] = {
    # Wrong WhatsApp number in section 7; see docs/data-quality.md, item a.
    "(67) 3321-4500": "(67) 3341-4444",
    # Accented (undeliverable) email in table 1.2; see docs/data-quality.md, item b.
    "contato@empóriodamusica.com.br": "contato@emporiodamusica.com.br",
}

# Top-level headers start at column 0 ("2. Horário ..."). Sub-sections ("3.1 ...")
# have no dot after the number, and numbered list items are indented.
_SECTION_HEADER = re.compile(r"^(\d{1,2})\.\s+(\S.*)$")


def _clean_line(line: str) -> str:
    """Tidy one layout-mode line: bullets, table spacing and trailing spaces."""
    line = line.rstrip()
    stripped = line.strip()
    stripped = re.sub(r"^•\s+", "• ", stripped)
    stripped = re.sub(r"^(\d+\.)\s{2,}", r"\1 ", stripped)
    # Wide gaps come from table columns; mark them with a separator.
    return re.sub(r"\s{3,}", " | ", stripped)


def extract_policy_text(pdf_path: Path = POLICY_PDF) -> str:
    """Return the cleaned text of the policy PDF (headers/footers removed, CORRECTIONS applied).

    Section headers keep column 0 so they can be detected; other lines are stripped.
    """
    reader = PdfReader(pdf_path)
    lines: list[str] = []
    for page in reader.pages:
        for raw in page.extract_text(extraction_mode="layout").splitlines():
            text = raw.strip()
            if any(p.match(text) for p in _NOISE_LINES):
                continue
            is_header = bool(_SECTION_HEADER.match(raw.rstrip()))
            lines.append(raw.rstrip() if is_header else _clean_line(raw))
    text = apply_corrections("\n".join(lines))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def apply_corrections(text: str) -> str:
    """Replace known errors in the policy text (see CORRECTIONS)."""
    for wrong, right in CORRECTIONS.items():
        text = text.replace(wrong, right)
    return text


def split_sections(text: str) -> dict[str, str]:
    """Split text into {"N. Title": body} using sequential top-level numbers.

    Anything before section 1 (the cover page) is dropped.
    """
    sections: dict[str, str] = {}
    expected = 1
    title: str | None = None
    body: list[str] = []
    for line in text.splitlines():
        match = _SECTION_HEADER.match(line)
        if match and int(match.group(1)) == expected:
            if title is not None:
                sections[title] = "\n".join(body).strip()
            title = f"{match.group(1)}. {match.group(2).strip()}"
            body = []
            expected += 1
        elif title is not None:
            body.append(line)
    if title is not None:
        sections[title] = "\n".join(body).strip()
    return sections


@lru_cache(maxsize=None)
def load_policy_sections(pdf_path: Path = POLICY_PDF) -> dict[str, str]:
    """Return the policy document as {section_title: text}, cached."""
    return split_sections(extract_policy_text(pdf_path))
