from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer

from studio.generate import generate_dialogues
from studio.ingest import ingest_case
from studio.review import accept_dialogue, list_reviews, reject_dialogue

app = typer.Typer(help="Learn English content studio CLI.")
review_app = typer.Typer(help="Review generated dialogues.")
app.add_typer(review_app, name="review")


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


@app.command()
def generate(
    case: str = typer.Option(..., "--case", help="Case id under data/cases."),
    mock: bool = typer.Option(False, "--mock", help="Use mock dialogue writer."),
) -> None:
    """Generate nine dialogues for a case (mock or Gemini)."""
    paths = generate_dialogues(case, mock=mock)
    for path in paths:
        typer.echo(str(path))


@review_app.command("list")
def review_list(
    case: str = typer.Option(..., "--case", help="Case id."),
) -> None:
    """List dialogue review statuses."""
    for row in list_reviews(case):
        typer.echo(
            f"{row['stem']}\t{row['status']}"
            + (f"\t{row['notes']}" if row.get("notes") else "")
        )


@review_app.command("accept")
def review_accept(
    case: str = typer.Option(..., "--case"),
    dialogue: str = typer.Option(..., "--dialogue", help="Dialogue stem."),
) -> None:
    """Mark a dialogue accepted."""
    accept_dialogue(case, dialogue)
    typer.echo(f"accepted {dialogue}")


@review_app.command("reject")
def review_reject(
    case: str = typer.Option(..., "--case"),
    dialogue: str = typer.Option(..., "--dialogue", help="Dialogue stem."),
    notes: str = typer.Option("", "--notes", help="Rejection notes."),
) -> None:
    """Mark a dialogue rejected."""
    reject_dialogue(case, dialogue, notes=notes)
    typer.echo(f"rejected {dialogue}")