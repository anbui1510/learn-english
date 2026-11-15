from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Protocol

from pypdf import PdfReader

CLINICAL_HEADINGS = (
    "Clinical Manifestations",
    "Diagnosis",
    "Treatment",
    "Differential Diagnosis",
    "Pathophysiology",
    "Epidemiology",
)


@dataclass(frozen=True)
class ParsedSegment:
    category: str
    source_quote: str
    atomic_fact: str
    page: int
    section: str | None = None


class PdfFactParser(Protocol):
    def parse(self, pdf_bytes: bytes) -> list[ParsedSegment]: ...


class HeuristicPdfParser:
    """Local extractor: pypdf text + clinical heading heuristics (no clinical invention)."""

    def parse(self, pdf_bytes: bytes) -> list[ParsedSegment]:
        text = _pdf_text(pdf_bytes)
        if not text.strip():
            text = pdf_bytes.decode("latin-1", errors="ignore")
        return _segments_from_text(text)


class DoclingPdfParser:
    """Optional Docling-backed parser. Raises if Docling is not installed."""

    def parse(self, pdf_bytes: bytes) -> list[ParsedSegment]:
        try:
            import docling  # noqa: F401  # type: ignore[import-untyped]
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError(
                "Docling is not installed; use HeuristicPdfParser or install docling."
            ) from exc
        # Docling wiring reserved for when the dependency is present.
        raise RuntimeError("Docling parser is not configured in this MVP build")


def get_default_parser() -> PdfFactParser:
    return HeuristicPdfParser()


def _pdf_text(pdf_bytes: bytes) -> str:
    try:
        reader = PdfReader(BytesIO(pdf_bytes))
    except Exception:
        return ""
    parts: list[str] = []
    for page in reader.pages:
        try:
            parts.append(page.extract_text() or "")
        except Exception:
            continue
    return "\n".join(parts)


def _segments_from_text(text: str) -> list[ParsedSegment]:
    # Normalize line endings; keep content after %%EOF for fixture PDFs.
    normalized = text.replace("\r\n", "\n")
    heading_re = re.compile(
        r"(?m)^(?P<head>"
        + "|".join(re.escape(h) for h in CLINICAL_HEADINGS)
        + r")\s*$"
    )
    matches = list(heading_re.finditer(normalized))
    if not matches:
        return []

    segments: list[ParsedSegment] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(normalized)
        body = normalized[start:end].strip()
        if not body:
            continue
        # Drop very short / ambiguous scraps
        if len(body) < 12:
            continue
        quote = " ".join(body.split())
        # atomic_fact = first sentence-ish; still grounded in source quote
        atomic = re.split(r"(?<=[.!?])\s+", quote, maxsplit=1)[0].strip() or quote
        segments.append(
            ParsedSegment(
                category=match.group("head"),
                source_quote=quote,
                atomic_fact=atomic,
                page=1,
                section=match.group("head"),
            )
        )
    return segments
