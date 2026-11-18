from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from studio.paths import cases_root


def _slugify(title: str) -> str:
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[-\s]+", "-", slug)
    return slug.strip("-")


def _utc_now_z() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_pdf_text(
    pdf: Path, page_start: int | None, page_end: int | None
) -> str:
    reader = PdfReader(str(pdf))
    total = len(reader.pages)
    if total == 0:
        return ""
    start_idx = (page_start - 1) if page_start is not None else 0
    end_idx = page_end if page_end is not None else total
    start_idx = max(0, min(start_idx, total))
    end_idx = max(start_idx, min(end_idx, total))
    chunks: list[str] = []
    for i in range(start_idx, end_idx):
        text = reader.pages[i].extract_text() or ""
        chunks.append(text)
    return "\n".join(chunks).strip()


def ingest_case(
    *,
    title: str,
    case_id: str | None = None,
    pdf: Path | None = None,
    text_file: Path | None = None,
    isbn: str = "",
    edition: str = "",
    page_start: int | None = None,
    page_end: int | None = None,
) -> Path:
    cid = case_id or _slugify(title)
    if not cid:
        raise ValueError("case_id could not be determined; pass --case-id")

    case_dir = cases_root() / cid
    for name in ("dialogues", "audio", "video"):
        (case_dir / name).mkdir(parents=True, exist_ok=True)

    source_text = ""
    if text_file is not None:
        source_text = text_file.read_text(encoding="utf-8").strip()
    elif pdf is not None:
        source_text = _extract_pdf_text(pdf, page_start, page_end)

    if not source_text:
        raise ValueError(
            "No source text available; provide non-empty --text-file or a PDF with extractable text"
        )

    dest_source = case_dir / "source.txt"
    if text_file is not None:
        if text_file.resolve() != dest_source.resolve():
            shutil.copy2(text_file, dest_source)
        else:
            dest_source.write_text(source_text, encoding="utf-8")
    else:
        dest_source.write_text(source_text, encoding="utf-8")

    now = _utc_now_z()
    meta: dict[str, object] = {
        "id": cid,
        "title": title,
        "isbn": isbn,
        "edition": edition,
        "status": "ready_for_generate",
        "created_at": now,
        "updated_at": now,
    }
    if pdf is not None:
        meta["source_pdf"] = str(pdf)
    if page_start is not None:
        meta["page_start"] = page_start
    if page_end is not None:
        meta["page_end"] = page_end

    (case_dir / "case.json").write_text(
        json.dumps(meta, indent=2) + "\n", encoding="utf-8"
    )
    (case_dir / "review.json").write_text("{}\n", encoding="utf-8")

    return case_dir