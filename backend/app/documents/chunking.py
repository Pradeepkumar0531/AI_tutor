"""Deterministic, page-aware chunking. No LangChain, no tokenizers.

Strategy: page -> paragraphs (blank-line separated) -> packed chunks. Chunks
never span pages (page ranges stay exact for RAG citations); a chunk carries
``page_start``/``page_end`` provenance. Overlap reuses trailing characters of
the previous chunk for boundary context. Same input + same config always yields
the same chunks (stable ``chunk_index`` order = Prompt 6's chunk identity).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class ChunkConfig:
    chunk_size: int = 1000
    overlap: int = 150
    min_chunk_chars: int = 100


@dataclass(frozen=True)
class PageInput:
    page_number: int  # 1-based PDF page number (citation provenance)
    text: str  # already normalized


@dataclass
class TextChunk:
    index: int
    content: str
    page_start: int
    page_end: int
    metadata: dict = field(default_factory=dict)


def _split_paragraphs(text: str) -> list[str]:
    parts = [p.strip() for p in re.split(r"\n\s*\n", text)]
    return [p for p in parts if p]


def _split_long_paragraph(paragraph: str, limit: int) -> list[str]:
    """Hard-split only when a single paragraph exceeds the limit: prefer
    sentence boundaries, fall back to a hard character cut (deterministic)."""
    if len(paragraph) <= limit:
        return [paragraph]
    pieces: list[str] = []
    current: list[str] = []
    current_len = 0
    for sentence in _SENTENCE_END.split(paragraph):
        sentence = sentence.strip()
        if not sentence:
            continue
        extra = len(sentence) + (1 if current else 0)
        if current and current_len + extra > limit:
            pieces.append(" ".join(current))
            current, current_len = [], 0
        current.append(sentence)
        current_len += len(sentence) + 1
    if current:
        pieces.append(" ".join(current))
    out: list[str] = []
    for piece in pieces:
        while len(piece) > limit:
            out.append(piece[:limit])
            piece = piece[limit:]
        if piece:
            out.append(piece)
    return out


def chunk_pages(pages: list[PageInput], config: ChunkConfig) -> list[TextChunk]:
    """Pack paragraphs into chunks, one page at a time. Deterministic."""
    if config.overlap >= config.chunk_size:
        raise ValueError("chunk overlap must be smaller than chunk size")
    chunks: list[TextChunk] = []
    for page in pages:
        units: list[str] = []
        for paragraph in _split_paragraphs(page.text):
            units.extend(_split_long_paragraph(paragraph, config.chunk_size))
        if not units:
            continue
        # Pack units greedily; merge a short trailing tail into the previous
        # chunk so we never emit dust-sized fragments.
        packed: list[str] = []
        current = ""
        for unit in units:
            candidate = f"{current}\n\n{unit}" if current else unit
            if current and len(candidate) > config.chunk_size:
                packed.append(current)
                current = unit
            else:
                current = candidate
        if current:
            if (
                packed
                and len(current) < config.min_chunk_chars
                and len(packed[-1]) + 2 + len(current) <= config.chunk_size + config.overlap
            ):
                packed[-1] = f"{packed[-1]}\n\n{current}"
            else:
                packed.append(current)
        prev_tail = ""
        for piece in packed:
            # Overlap stays *within* the page: page provenance is exact and no
            # content bleeds across page boundaries.
            content = f"{prev_tail}{piece}" if prev_tail else piece
            chunks.append(
                TextChunk(
                    index=len(chunks),
                    content=content,
                    page_start=page.page_number,
                    page_end=page.page_number,
                    metadata={"page": page.page_number},
                )
            )
            prev_tail = content[-config.overlap :] if config.overlap > 0 else ""
    return chunks


def estimate_tokens(text: str) -> int:
    """Rough char/4 heuristic (documented; no tokenizer dependency)."""
    return max(1, len(text) // 4)
