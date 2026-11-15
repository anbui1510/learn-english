from __future__ import annotations

from app.cases.repository import CaseRepository
from app.cases.service import get_case_repository
from app.facts.parser import PdfFactParser, get_default_parser
from app.facts.repository import FactRepository
from app.facts.service import get_fact_repository
from app.storage.base import ObjectStorage
from app.storage.factory import get_storage


class ExtractError(ValueError):
    """Raised when a Case cannot be extracted."""


def run_extract_job(
    *,
    case_id: int,
    cases: CaseRepository | None = None,
    facts: FactRepository | None = None,
    storage: ObjectStorage | None = None,
    parser: PdfFactParser | None = None,
) -> int:
    """
    Run extraction synchronously (MVP in-process worker).
    Returns number of facts written. Updates Case extract_* fields.
    """
    case_repo = cases or get_case_repository()
    fact_repo = facts or get_fact_repository()
    object_store = storage or get_storage()

    case = case_repo.get_by_id(case_id)
    if case is None:
        raise ExtractError("Case not found")
    if not case.pdf_object_key:
        raise ExtractError("Case has no PDF object")
    if not case.isbn or not case.edition:
        raise ExtractError("Case ISBN and edition are required before extract")

    case_repo.set_extract_status(case_id, status="running", error=None)
    try:
        pdf_bytes = object_store.get(case.pdf_object_key)
        active_parser = parser or get_default_parser()
        segments = active_parser.parse(pdf_bytes)
        fact_repo.delete_for_case(case_id)
        written = 0
        for segment in segments:
            fact_repo.insert_fact(
                case_id=case_id,
                source_quote=segment.source_quote,
                atomic_fact=segment.atomic_fact,
                category=segment.category,
                page=segment.page,
                isbn=case.isbn,
                edition=case.edition,
                status="needs_review",
                section=segment.section,
            )
            written += 1
        case_repo.set_extract_status(case_id, status="succeeded", error=None)
        return written
    except Exception as exc:
        case_repo.set_extract_status(case_id, status="failed", error=str(exc))
        raise


def background_extract(case_id: int) -> None:
    """BackgroundTasks entrypoint — swallows ExtractError after status write."""
    try:
        run_extract_job(case_id=case_id)
    except Exception:
        # Status already recorded as failed when applicable.
        return
