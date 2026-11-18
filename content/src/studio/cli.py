from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from studio.ingest import ingest_case

app = typer.Typer(help="Learn English content studio CLI.")


@app.callback()
def _main() -> None:
    """Content studio commands."""


@app.command()
def ingest(
    title: str = typer.Option(..., "--title", help="Human-readable case title."),
    case_id: Optional[str] = typer.Option(
        None, "--case-id", help="Filesystem id for the case folder."
    ),
    pdf: Optional[Path] = typer.Option(
        None, "--pdf", exists=True, dir_okay=False, readable=True, help="Source PDF."
    ),
    text_file: Optional[Path] = typer.Option(
        None,
        "--text-file",
        exists=True,
        dir_okay=False,
        readable=True,
        help="Plain-text source when PDF text is missing or unwanted.",
    ),
    isbn: str = typer.Option("", "--isbn"),
    edition: str = typer.Option("", "--edition"),
    page_start: Optional[int] = typer.Option(None, "--page-start"),
    page_end: Optional[int] = typer.Option(None, "--page-end"),
) -> None:
    """Create a case folder with metadata and source text."""
    case_dir = ingest_case(
        title=title,
        case_id=case_id,
        pdf=pdf,
        text_file=text_file,
        isbn=isbn,
        edition=edition,
        page_start=page_start,
        page_end=page_end,
    )
    typer.echo(str(case_dir))