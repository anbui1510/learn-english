# Content Studio Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a CLI-first `content/` studio that ingests clinical English source text/PDF, generates 9 reviewable dialogues (3 contexts × 3 CEFR), synthesizes dual-voice TTS, and renders DualTalk MP4s (Remotion with ffmpeg fallback).

**Architecture:** File-first case warehouse under `content/data/cases/<id>/` with a SQLite manifest index; Typer CLI `studio`; shared JSON Schema for studio dialogues; Remotion `DualTalk` composition beside existing `Karaoke`. Learner `backend/`/`frontend/` stay unchanged.

**Tech Stack:** Python 3.12 + uv, Typer, jsonschema, pypdf, google-genai, edge-tts, SQLite; Remotion 4 + React 19; ffmpeg fallback.

**Spec:** `docs/superpowers/specs/2026-11-18-content-studio-phase1-design.md`

## Global Constraints

- Do not modify learner OAuth, RBAC, karaoke player, or editorial publish gates.
- Contexts must remain `patient_family` | `colleague_sbar` | `expert_cme`.
- CEFR packages must remain `A2` | `B1` | `C1`.
- Only `accepted` dialogues may synthesize/render unless `--force`.
- CI must not require real Gemini API keys or Nelson PDFs (`--mock` + fixtures).
- Voices: `en-US-GuyNeural` (doctor/colleague/expert), `en-US-JennyNeural` (parent/family).
- Runtime artifacts under `content/data/` are gitignored except documented fixtures under `content/fixtures/`.

## File map

| Path | Responsibility |
|------|----------------|
| `content/pyproject.toml` | uv project, console script `studio` |
| `content/README.md` | End-to-end operator guide |
| `content/src/studio/__init__.py` | Package version |
| `content/src/studio/cli.py` | Typer app wiring commands |
| `content/src/studio/paths.py` | Resolve data/fixture roots |
| `content/src/studio/models.py` | Constants, stem helpers, dataclasses |
| `content/src/studio/schema_validate.py` | Load + validate studio dialogue schema |
| `content/src/studio/ingest.py` | Create case folder, extract/copy text |
| `content/src/studio/generate.py` | Gemini + mock writers for 9 dialogues |
| `content/src/studio/review.py` | list/accept/reject + review.json |
| `content/src/studio/synthesize.py` | edge-tts / synthetic TTS + timestamps |
| `content/src/studio/render.py` | Props builder, Remotion invoke, ffmpeg fallback |
| `content/src/studio/manifest.py` | SQLite index rebuild/query |
| `content/src/studio/status.py` | Human-readable pipeline status |
| `content/tests/` | pytest suite |
| `content/fixtures/otitis-demo/` | Synthetic source case |
| `schemas/studio-dialogue.schema.json` | Studio dialogue contract (fact_ids optional) |
| `schemas/fixtures/studio-dialogue.*.json` | Valid/invalid fixtures |
| `video/remotion/src/DualTalkComposition.tsx` | Two-panel conversation UI |
| `video/remotion/src/Root.tsx` | Register DualTalk composition |
| `video/remotion/public/avatars/` | Placeholder avatar PNGs |
| `video/remotion/sample-dualtalk-props.json` | Smoke props |
| `.gitignore` | Ignore `content/data/` |
| `README.md` | Link to Content Studio |

---

### Task 1: Scaffold `content/` package + studio dialogue schema

**Files:**
- Create: `content/pyproject.toml`
- Create: `content/src/studio/__init__.py`
- Create: `content/src/studio/paths.py`
- Create: `content/src/studio/models.py`
- Create: `content/src/studio/schema_validate.py`
- Create: `content/tests/test_schema.py`
- Create: `schemas/studio-dialogue.schema.json`
- Create: `schemas/fixtures/studio-dialogue.valid.json`
- Create: `schemas/fixtures/studio-dialogue.invalid-empty-text.json`
- Modify: `.gitignore` (add `content/data/`, `content/.venv/`)
- Modify: `schemas/README.md` (document studio schema)

**Interfaces:**
- Produces: `CONTEXTS`, `CEFR_LEVELS`, `dialogue_stem(context, cefr) -> str`, `validate_studio_dialogue(data: dict) -> None` (raises `jsonschema.ValidationError`)
- Produces: `package_root() -> Path`, `data_root() -> Path`, `cases_root() -> Path`, `repo_root() -> Path`

- [ ] **Step 1: Write failing schema test**

```python
# content/tests/test_schema.py
from pathlib import Path
import json
import pytest
from studio.schema_validate import validate_studio_dialogue

FIXTURES = Path(__file__).resolve().parents[2] / "schemas" / "fixtures"

def test_valid_studio_dialogue_passes():
    data = json.loads((FIXTURES / "studio-dialogue.valid.json").read_text())
    validate_studio_dialogue(data)

def test_empty_text_fails():
    data = json.loads((FIXTURES / "studio-dialogue.invalid-empty-text.json").read_text())
    with pytest.raises(Exception):
        validate_studio_dialogue(data)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd content && uv sync && uv run pytest tests/test_schema.py -v`  
Expected: FAIL (module/schema missing)

- [ ] **Step 3: Add schema, package skeleton, and validator**

`schemas/studio-dialogue.schema.json` must require `context`, `cefr_level`, `status`, `lines`; line requires `speaker`, `text`; allow optional `source_quote`, `page`, `text_vi`, `is_key_phrase`; `fact_ids` optional array.

`content/pyproject.toml`:

```toml
[project]
name = "learn-english-studio"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "typer>=0.12",
  "jsonschema>=4.22",
  "pypdf>=5.0",
  "google-genai>=1.0",
  "edge-tts>=7.0",
  "pytest>=8.0",
]

[project.scripts]
studio = "studio.cli:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/studio"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

Implement `validate_studio_dialogue` loading `schemas/studio-dialogue.schema.json` relative to repo root via `paths.repo_root()`.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd content && uv sync && uv run pytest tests/test_schema.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add content schemas .gitignore
git commit -m "feat(studio): scaffold content package and studio dialogue schema"
```

---

### Task 2: Ingest + fixture case + CLI shell

**Files:**
- Create: `content/src/studio/ingest.py`
- Create: `content/src/studio/cli.py`
- Create: `content/tests/test_ingest.py`
- Create: `content/fixtures/otitis-demo/source.txt`
- Create: `content/fixtures/otitis-demo/meta.json`

**Interfaces:**
- Consumes: `cases_root()`, models constants
- Produces: `ingest_case(*, title, case_id=None, pdf=None, text_file=None, isbn="", edition="", page_start=None, page_end=None) -> Path` returning case dir
- Produces: Typer `app` with `ingest` command

- [ ] **Step 1: Write failing ingest test**

```python
# content/tests/test_ingest.py
from pathlib import Path
import json
from studio.ingest import ingest_case

def test_ingest_from_text_file(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_DATA_ROOT", str(tmp_path))
    src = tmp_path / "in.txt"
    src.write_text("Otitis media causes ear pain and fever in children.", encoding="utf-8")
    case_dir = ingest_case(title="Otitis demo", case_id="otitis-demo", text_file=src, isbn="000", edition="1")
    assert (case_dir / "case.json").exists()
    assert "ear pain" in (case_dir / "source.txt").read_text()
    meta = json.loads((case_dir / "case.json").read_text())
    assert meta["id"] == "otitis-demo"
    assert meta["status"] == "ready_for_generate"
    assert (case_dir / "dialogues").is_dir()
```

- [ ] **Step 2: Run test — expect FAIL**

Run: `cd content && uv run pytest tests/test_ingest.py -v`

- [ ] **Step 3: Implement ingest + paths env override + CLI**

`paths.data_root()` honors `STUDIO_DATA_ROOT` else `content/data`.

`ingest_case`:
1. Create `cases/<id>/{dialogues,audio,video}`
2. Copy `--text-file` or extract PDF via `pypdf`; if empty text and no text file → raise `ValueError` asking for `--text-file`
3. Write `case.json` with timestamps ISO-8601 Z
4. Write empty `review.json` `{}`

Fixture `content/fixtures/otitis-demo/source.txt`: 8–15 short English clinical sentences (synthetic, not copied from Nelson).

Wire Typer:

```python
@app.command()
def ingest(...): ...
```

Minimal `cli.py` may stub other commands with `raise typer.Exit` until later tasks — or only register `ingest` now and add commands incrementally.

- [ ] **Step 4: Pass tests**

Run: `cd content && uv run pytest tests/test_ingest.py tests/test_schema.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add content
git commit -m "feat(studio): add case ingest and CLI entrypoint"
```

---

### Task 3: Mock generate (9 dialogues) + review state machine

**Files:**
- Create: `content/src/studio/generate.py`
- Create: `content/src/studio/review.py`
- Create: `content/tests/test_generate_mock.py`
- Create: `content/tests/test_review.py`
- Modify: `content/src/studio/cli.py`

**Interfaces:**
- Produces: `generate_dialogues(case_id: str, *, mock: bool = False) -> list[Path]`
- Produces: `list_reviews(case_id)`, `accept_dialogue(case_id, stem)`, `reject_dialogue(case_id, stem, notes="")`
- Gate helper: `assert_accepted(case_id, stem, *, force=False)`

- [ ] **Step 1: Write failing generate/review tests**

```python
def test_mock_generate_writes_nine_files(tmp_path, monkeypatch):
    # ingest fixture text into tmp data root, then:
    paths = generate_dialogues("otitis-demo", mock=True)
    assert len(paths) == 9
    data = json.loads(paths[0].read_text())
    assert data["status"] == "needs_review"
    assert data["lines"][0]["source_quote"]

def test_accept_updates_review_json(tmp_path, monkeypatch):
    # after mock generate:
    accept_dialogue("otitis-demo", "patient_family__A2")
    d = json.loads((case_dir / "dialogues" / "patient_family__A2.json").read_text())
    assert d["status"] == "accepted"
    review = json.loads((case_dir / "review.json").read_text())
    assert review["patient_family__A2"]["status"] == "accepted"
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement mock generator + review**

Mock generator:
- Read `source.txt`; take first sentence as `source_quote`
- For each of 9 stems, write 4–6 alternating speaker lines grounded with that quote (short EN + optional `text_vi`)
- Speakers: patient_family → doctor/parent; colleague_sbar → doctor/colleague; expert_cme → expert/learner
- Set `status: needs_review`
- Do **not** overwrite dialogues already `accepted`

Live Gemini path may be a stub raising `NotImplementedError` until Task 4, but CLI `--mock` must work now.

Review accept/reject updates dialogue JSON + `review.json`.

- [ ] **Step 4: Pass tests + wire CLI `generate` / `review`**

Run: `cd content && uv run pytest tests/test_generate_mock.py tests/test_review.py -v`

- [ ] **Step 5: Commit**

```bash
git add content
git commit -m "feat(studio): mock generate nine dialogues and CLI review"
```

---

### Task 4: Live Gemini generate (optional path)

**Files:**
- Modify: `content/src/studio/generate.py`
- Create: `content/tests/test_generate_gemini.py` (mocked HTTP / fake client)
- Create: `content/src/studio/prompts.py`

**Interfaces:**
- Produces: `GeminiDialogueClient.generate_one(source_text, case_meta, context, cefr) -> dict`
- `generate_dialogues(..., mock=False)` uses client when `GEMINI_API_KEY` set

- [ ] **Step 1: Write test with fake client**

```python
class FakeClient:
    def generate_one(self, **kwargs):
        return {
            "context": kwargs["context"],
            "cefr_level": kwargs["cefr"],
            "status": "needs_review",
            "lines": [
                {"speaker": "doctor", "text": "Fever can mean infection.", "source_quote": "fever", "page": 1}
            ],
        }

def test_generate_uses_client(monkeypatch, tmp_path):
    ...
    generate_dialogues("otitis-demo", mock=False, client=FakeClient())
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement prompts + google-genai structured JSON**

- Env: `GEMINI_API_KEY`, `STUDIO_GEMINI_MODEL` (default `gemini-2.0-flash`)
- Validate each dialogue with `validate_studio_dialogue`
- On failure: retry once; still failing → write `generate_error.json` for that stem; skip clobbering `accepted`
- Missing API key + not mock → clear `RuntimeError`

- [ ] **Step 4: Pass tests**

- [ ] **Step 5: Commit**

```bash
git add content
git commit -m "feat(studio): add Gemini dialogue generation with schema retry"
```

---

### Task 5: Synthesize TTS + timestamps

**Files:**
- Create: `content/src/studio/synthesize.py`
- Create: `content/tests/test_synthesize.py`
- Modify: `content/src/studio/cli.py`

**Interfaces:**
- Produces: `synthesize_case(case_id, dialogue_stem=None, *, force=False, engine="auto") -> list[Path]`
- Writes `audio/<stem>/line_XXX.mp3` (or `.wav` synthetic), `timestamps.json`, `full.mp3`/`full.wav`

- [ ] **Step 1: Failing test with synthetic engine**

```python
def test_synthesize_accepted_only(tmp_path, monkeypatch):
    # mock generate; do NOT accept → synthesize raises
    # accept one → synthesize creates timestamps.json with words
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement synthesizer**

Prefer copying patterns from `backend/app/speech/tts.py` (voice map + synthetic silent/tone fallback) **inside** `content/src/studio/synthesize.py` (do not import backend package — keep studio standalone).

Default CI/`--engine synthetic`: deterministic word timestamps (~320ms/word) and wav bytes.  
`--engine edge` or `auto` with edge-tts available: real mp3 + WordBoundary when network works; on failure fall back to synthetic and record `engine` in `timestamps.json` metadata.

Reject non-accepted without `--force`.

- [ ] **Step 4: Pass tests**

- [ ] **Step 5: Commit**

```bash
git add content
git commit -m "feat(studio): synthesize dual-voice audio and word timestamps"
```

---

### Task 6: Remotion DualTalk + ffmpeg fallback render

**Files:**
- Create: `video/remotion/src/DualTalkComposition.tsx`
- Modify: `video/remotion/src/Root.tsx`
- Create: `video/remotion/sample-dualtalk-props.json`
- Create: `video/remotion/public/avatars/.gitkeep` (and two simple placeholder PNGs or SVG-converted placeholders)
- Create: `content/src/studio/render.py`
- Create: `content/tests/test_render_ffmpeg.py`
- Modify: `video/remotion/package.json` (add render script for DualTalk)
- Modify: `content/src/studio/cli.py`

**Interfaces:**
- Produces: `build_dualtalk_props(case_dir, stem) -> dict`
- Produces: `render_dialogue(case_id, stem, *, force=False) -> Path` returning mp4 path
- Remotion composition id: `DualTalk`

- [ ] **Step 1: Write ffmpeg fallback test**

```python
def test_ffmpeg_fallback_creates_mp4(tmp_path, monkeypatch):
    # accepted + synthesized audio present
    # monkeypatch remotion to missing; call render_dialogue
    # assert video file exists and size > 0 (skip if ffmpeg absent)
```

- [ ] **Step 2: Implement DualTalk composition**

Layout 1920×1080:
- Left/right panels with avatar + speaker label
- Highlight active speaker from props timeline
- Caption EN with optional word highlight index
- Footer watermark: title · ISBN · edition

Register in `Root.tsx` with `calculateMetadata` from audio duration or line count.

- [ ] **Step 3: Implement `render.py`**

1. Build props JSON under case `video/<stem>.props.json`
2. Try `npx remotion render src/index.ts DualTalk <out> --props=...` cwd `video/remotion`
3. On failure/missing: ffmpeg concat audio + drawtext/srt burn-in; set metadata `engine=ffmpeg`

- [ ] **Step 4: Pass content tests; optional local Remotion smoke**

Run: `cd content && uv run pytest tests/test_render_ffmpeg.py -v`  
Optional: `cd video/remotion && npm install && npx remotion render src/index.ts DualTalk /tmp/dual.mp4 --props=./sample-dualtalk-props.json`

- [ ] **Step 5: Commit**

```bash
git add content video/remotion
git commit -m "feat(studio): DualTalk Remotion composition and ffmpeg render fallback"
```

---

### Task 7: Manifest index + status + README E2E

**Files:**
- Create: `content/src/studio/manifest.py`
- Create: `content/src/studio/status.py`
- Create: `content/tests/test_manifest_status.py`
- Create: `content/README.md`
- Modify: `content/src/studio/cli.py` (`index`, `status`)
- Modify: `README.md` (short Content Studio section + link)

**Interfaces:**
- Produces: `rebuild_index() -> int` (rows touched)
- Produces: `case_status(case_id) -> str` (printable summary)

- [ ] **Step 1: Failing manifest/status test**

```python
def test_index_and_status(tmp_path, monkeypatch):
    # ingest + mock generate + accept one
    n = rebuild_index()
    assert n >= 1
    text = case_status("otitis-demo")
    assert "patient_family__A2" in text
    assert "accepted" in text
```

- [ ] **Step 2: Implement SQLite schema + status printer**

Tables per spec §4.5. Use `content/data/studio.sqlite` under `data_root()`.

- [ ] **Step 3: Write `content/README.md` with exact commands**

```bash
cd content && uv sync
uv run studio ingest --text-file fixtures/otitis-demo/source.txt --title "Otitis demo" --case-id otitis-demo --isbn 000 --edition 1
uv run studio generate --case otitis-demo --mock
uv run studio review accept --case otitis-demo --dialogue patient_family__A2
uv run studio synthesize --case otitis-demo --dialogue patient_family__A2 --engine synthetic
uv run studio render --case otitis-demo --dialogue patient_family__A2
uv run studio status --case otitis-demo
```

- [ ] **Step 4: Run full content pytest**

Run: `cd content && uv run pytest -v`  
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add content README.md
git commit -m "feat(studio): SQLite manifest, status command, and operator README"
```

---

### Task 8: Wiring polish + CI smoke (optional light)

**Files:**
- Modify: `.github/workflows/ci.yml` (add content pytest job or step)
- Modify: `content/src/studio/cli.py` ensure all commands registered
- Create: `content/tests/test_cli_smoke.py` using Typer `CliRunner`

- [ ] **Step 1: CLI smoke test** end-to-end mock pipeline via CliRunner in tmp data root

- [ ] **Step 2: Add CI step**

```yaml
- name: Content studio tests
  working-directory: content
  run: |
    uv sync
    uv run pytest -q
```

- [ ] **Step 3: Run locally `cd content && uv run pytest -q` + confirm root CI YAML valid**

- [ ] **Step 4: Commit**

```bash
git add content .github/workflows/ci.yml
git commit -m "ci: run content studio pytest on PRs"
```

- [ ] **Step 5: Push branch and update PR description with DoD checklist**

---

## Self-review (plan vs spec)

| Spec requirement | Task |
|------------------|------|
| `content/` CLI uv package | 1–2 |
| Hybrid generate + source_quote | 3–4 |
| Review CLI gate | 3 |
| TTS two voices + timestamps | 5 |
| DualTalk Remotion + ffmpeg | 6 |
| SQLite manifest + status | 7 |
| README E2E + fixture | 2, 7 |
| Learner app untouched | Global constraint |
| CI without real Gemini/Nelson | 3 mock, 5 synthetic, 8 |

No TBD placeholders in task steps. Types/names consistent: `dialogue_stem`, `needs_review`/`accepted`, composition id `DualTalk`.
