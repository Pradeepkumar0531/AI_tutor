"""Centralized text normalization. Goal: semantic readability for learning
content, not cosmetic perfection. Paragraphs, headings, lists, and page
boundaries survive; extraction artifacts do not."""

from __future__ import annotations

import re
import unicodedata

_BLANK_RUN = re.compile(r"\n{3,}")
_TRAILING_WS = re.compile(r"[ \f\v]+$", re.MULTILINE)
_INNER_SPACES = re.compile(r" {2,}")


def normalize_text(text: str) -> str:
    """Normalize one page (or chunk) of extracted text.

    - ``\\r\\n``/``\\r`` -> ``\\n``; interior tabs kept (table-like structure).
    - Control characters stripped, except ``\\n`` and ``\\t``.
    - Runs of 2+ interior spaces collapse to one; trailing spaces (not tabs)
      per line removed; 3+ blank lines collapse to one blank line (paragraph
      breaks preserved as a single empty line).
    - Leading/trailing blank lines stripped.
    """
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(c for c in text if c in ("\n", "\t") or unicodedata.category(c) != "Cc")
    text = _INNER_SPACES.sub(" ", text)
    text = _TRAILING_WS.sub("", text)
    text = _BLANK_RUN.sub("\n\n", text)
    return text.strip("\n")
