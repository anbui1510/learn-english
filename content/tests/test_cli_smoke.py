"""End-to-end CLI smoke via Typer CliRunner (mock generate, synthetic TTS, no Gemini)."""

from __future__ import annotations

import shutil

import pytest
from typer.testing import CliRunner

from studio.cli import app

runner = CliRunner()


def test_cli_help_lists_all_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0, result.output
    for name in (
        "ingest",
        "generate",
        "synthesize",
        "render",
        "index",
        "status",
        "review",
    ):
        assert name in result.output


def test_review_subcommands_registered():
    result = runner.invoke(app, ["review", "--help"])
    assert result.exit_code == 0, result.output
    for name in ("list", "accept", "reject"):
        assert name in result.output


def test_cli_mock_pipeline_e2e(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    src = tmp_path / "in.txt"
    src.write_text(
        "Otitis media causes ear pain and fever in children.",
        encoding="utf-8",
    )
    case_id = "otitis-demo"
    stem = "patient_family__A2"

    steps = [
        (
            "ingest",
            [
                "ingest",
                "--text-file",
                str(src),
                "--title",
                "Otitis demo",
                "--case-id",
                case_id,
                "--isbn",
                "000",
                "--edition",
                "1",
            ],
        ),
        ("generate", ["generate", "--case", case_id, "--mock"]),
        (
            "review accept",
            ["review", "accept", "--case", case_id, "--dialogue", stem],
        ),
        (
            "synthesize",
            [
                "synthesize",
                "--case",
                case_id,
                "--dialogue",
                stem,
                "--engine",
                "synthetic",
            ],
        ),
        ("index", ["index"]),
        ("status", ["status", "--case", case_id]),
    ]

    for label, argv in steps:
        result = runner.invoke(app, argv, catch_exceptions=False)
        assert result.exit_code == 0, f"{label} failed:\n{result.output}\n{result.exception}"

    assert stem in result.output
    assert "accepted" in result.output

    case_dir = tmp_path / "cases" / case_id
    assert (case_dir / "dialogues" / f"{stem}.json").is_file()
    assert (case_dir / "audio" / stem / "timestamps.json").is_file()
    assert (tmp_path / "studio.sqlite").is_file()


@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_cli_render_after_pipeline(tmp_path, monkeypatch):
    """Render step via CLI when ffmpeg is available (Remotion optional / ffmpeg fallback)."""
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    src = tmp_path / "in.txt"
    src.write_text("Otitis media causes ear pain and fever in children.", encoding="utf-8")
    case_id = "otitis-demo"
    stem = "patient_family__A2"

    for argv in (
        [
            "ingest",
            "--text-file",
            str(src),
            "--title",
            "Otitis demo",
            "--case-id",
            case_id,
        ],
        ["generate", "--case", case_id, "--mock"],
        ["review", "accept", "--case", case_id, "--dialogue", stem],
        [
            "synthesize",
            "--case",
            case_id,
            "--dialogue",
            stem,
            "--engine",
            "synthetic",
        ],
        ["render", "--case", case_id, "--dialogue", stem],
    ):
        result = runner.invoke(app, argv, catch_exceptions=False)
        assert result.exit_code == 0, result.output

    mp4 = tmp_path / "cases" / case_id / "video" / f"{stem}.mp4"
    assert mp4.is_file()
    assert mp4.stat().st_size > 0