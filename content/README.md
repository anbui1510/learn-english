# Content Studio (Phase 1)

Typer CLI for ingesting medical cases, generating CEFR dialogues, review, TTS, and DualTalk render. Case data lives under `data/cases/`; a SQLite manifest mirrors filesystem state at `data/studio.sqlite`.

## Setup

```bash
cd content && uv sync
```

## End-to-end fixture pipeline (CI-safe mock + synthetic TTS)

```bash
cd content && uv sync
uv run studio ingest --text-file fixtures/otitis-demo/source.txt --title "Otitis demo" --case-id otitis-demo --isbn 000 --edition 1
uv run studio generate --case otitis-demo --mock
uv run studio review accept --case otitis-demo --dialogue patient_family__A2
uv run studio synthesize --case otitis-demo --dialogue patient_family__A2 --engine synthetic
uv run studio render --case otitis-demo --dialogue patient_family__A2
uv run studio status --case otitis-demo
```

## Other commands

```bash
uv run studio index                    # rebuild SQLite manifest
uv run studio review list --case ID
```

Tests: `uv run pytest -v`