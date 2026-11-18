# Content Studio (Phase 1)

Typer CLI for ingesting medical cases, generating CEFR dialogues, review, TTS, and DualTalk render. Case data lives under `data/cases/`; a SQLite manifest mirrors filesystem state at `data/studio.sqlite`.

Live Gemini generation uses model `gemini-3.5-flash-lite` by default (override with `STUDIO_GEMINI_MODEL` when needed). Set `GEMINI_API_KEY` in the environment.

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

## Seed a full case (9 dialogues × audio × DualTalk)

Uses synthetic fixture `fixtures/bronchiolitis-demo/` (not a commercial textbook).
Generated artifacts land in gitignored `data/cases/<id>/`.

```bash
cd content && uv sync
uv run studio ingest \
  --text-file fixtures/bronchiolitis-demo/source.txt \
  --title "Infant bronchiolitis — demo seed" \
  --case-id bronchiolitis-demo \
  --isbn SEED-0001 \
  --edition demo-1

# Mock (no API) or live Gemini when GEMINI_API_KEY is set:
uv run studio generate --case bronchiolitis-demo --mock
# uv run studio generate --case bronchiolitis-demo

for stem in patient_family__A2 patient_family__B1 patient_family__C1 \
  colleague_sbar__A2 colleague_sbar__B1 colleague_sbar__C1 \
  expert_cme__A2 expert_cme__B1 expert_cme__C1; do
  uv run studio review accept --case bronchiolitis-demo --dialogue "$stem"
done

uv run studio synthesize --case bronchiolitis-demo --engine auto
uv run studio render --case bronchiolitis-demo
uv run studio status --case bronchiolitis-demo
```

## Other commands

```bash
uv run studio index                    # rebuild SQLite manifest
uv run studio review list --case ID
```

Tests: `uv run pytest -v`