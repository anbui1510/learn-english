# Design: Content Studio Phase 1 (Dialogue DB + DualTalk Video)

**Date:** 2026-11-18  
**Status:** Approved in chat (location A, hybrid C, Remotion A, CLI A, architecture file-first)  
**Repo:** `learn-english`  
**Branch intent:** `cursor/content-studio-phase1-483b`

---

## 1. Problem & goal

Pivot from “interactive learner app first” to a **content factory**:

1. **Phase 1 (this spec):** Build a durable **dialogue + video database** from English clinical PDF/text sources via CLI.
2. **Phase 2 (out of scope):** Learning pathways / learner product on top of that database.

Phase 1 must produce reviewable dialogue artifacts (3 clinical contexts × 3 CEFR levels) and at least Remotion **DualTalk** MP4s (two-speaker conversation composition with TTS + captions).

---

## 2. Decisions locked

| Topic | Choice |
|-------|--------|
| Placement | New `content/` package **inside** this monorepo |
| Generation | **Hybrid:** Gemini batch dialogues with `source_quote` / page when available; CLI/file review later; no editor UI required |
| Video MVP | **Remotion DualTalk** (2 avatar panels + TTS + karaoke captions); MuseTalk/MultiTalk later |
| Interface | **CLI only** (`uv run studio …`) |
| Data layout | **File-first** case folders + light SQLite manifest |
| Learner app | Do **not** change `frontend/` / auth / karaoke learner flows in this MVP |

---

## 3. Architecture

```text
learn-english/
  content/
    pyproject.toml
    README.md
    src/studio/           # CLI package
    data/                 # runtime artifacts (mostly gitignored)
    fixtures/             # synthetic case for tests/demo
  schemas/                # shared JSON Schema; extend for studio dialogue
  video/remotion/         # add DualTalk composition alongside Karaoke
  backend/ frontend/      # untouched in Phase 1 MVP
```

### Pipeline

```text
PDF or text clinical case
  → ingest      (metadata + source text on disk)
  → generate    (Gemini → 9 dialogue JSON; status needs_review)
  → review      (CLI accept / reject / edit files)
  → synthesize  (edge-tts two voices → mp3 + word timestamps)
  → render      (Remotion DualTalk → mp4; ffmpeg fallback)
  → index       (SQLite manifest mirrors filesystem status)
```

**Gate:** Only dialogues with status `accepted` may be synthesized or rendered (except explicit `--force` for local dev).

**Non-negotiable content rule:** Model must not invent clinical content beyond the provided source text. Missing or weak citations → keep dialogue `needs_review`.

---

## 4. Data model

### 4.1 Case directory layout

```text
content/data/cases/<case_id>/
  case.json
  source.txt
  dialogues/
    patient_family__A2.json
    patient_family__B1.json
    patient_family__C1.json
    colleague_sbar__A2.json
    colleague_sbar__B1.json
    colleague_sbar__C1.json
    expert_cme__A2.json
    expert_cme__B1.json
    expert_cme__C1.json
  audio/<dialogue_stem>/
    line_001.mp3
    …
    timestamps.json
    full.mp3
  video/<dialogue_stem>.mp4
  review.json
```

Dialogue filename stem = `{context}__{cefr}` with:

- `context` ∈ `patient_family` | `colleague_sbar` | `expert_cme`
- `cefr` ∈ `A2` | `B1` | `C1`

### 4.2 `case.json` (minimum)

- `id`, `title`
- `isbn`, `edition` (required when known; empty string forbidden if flag `--require-metadata`)
- `source_pdf` (optional path/object key)
- `page_start`, `page_end` (optional)
- `status`: `draft` | `ready_for_generate` | `generated` | `partially_accepted` | `complete`
- `created_at`, `updated_at` (ISO-8601)

### 4.3 Dialogue artifact (studio)

Reuse concepts from `schemas/dialogue.schema.json`, with Phase 1 relaxations:

**Required per dialogue file:** `context`, `cefr_level`, `status`, `lines`.

**Per line:**

| Field | Required | Notes |
|-------|----------|--------|
| `speaker` | yes | e.g. `doctor`, `parent`, `colleague`, `expert` |
| `text` | yes | English primary |
| `text_vi` | no | Gloss only |
| `source_quote` | recommended | Short quote grounded in `source.txt` |
| `page` | if available | Page number |
| `fact_ids` | **optional in studio** | Unlike learner publish gate; may be `[]` or omitted |
| `is_key_phrase` | no | Forward-compatible with shadowing |

**Dialogue `status`:** `draft` → `needs_review` → `accepted` | `rejected`.

### 4.4 `review.json`

Map of dialogue stem → `{ "status": "accepted"|"rejected"|"needs_review", "notes": "", "reviewed_at": "..." }`  
CLI `review` updates both `review.json` and the dialogue file’s `status` field.

### 4.5 SQLite manifest

Path: `content/data/studio.sqlite`

Tables (minimal):

- `cases(id PK, title, status, path, updated_at)`
- `dialogues(id PK, case_id, context, cefr_level, status, path, updated_at)`
- `assets(id PK, dialogue_id, kind ['audio'|'video'], path, status, updated_at)`

Manifest is an **index**, not source of truth. Files on disk win; `studio index` / each command refreshes rows.

---

## 5. CLI surface

Entry: `uv run studio` from `content/` (Typer or argparse; prefer Typer).

| Command | Behavior |
|---------|----------|
| `ingest --pdf PATH --title T [--isbn I --edition E --case-id ID] [--text-file PATH]` | Create case folder; extract text (pypdf first; optional docling later). If extract empty → require `--text-file`. |
| `generate --case ID [--mock]` | Call Gemini structured output for all 9 combos (or mock fixture writer). Validate schema; write dialogues; set `needs_review`. |
| `review list --case ID` | Print dialogue statuses |
| `review accept --case ID --dialogue STEM` | Mark accepted |
| `review reject --case ID --dialogue STEM [--notes …]` | Mark rejected |
| `synthesize --case ID [--dialogue STEM] [--force]` | TTS accepted dialogues only; two Neural voices |
| `render --case ID [--dialogue STEM] [--force]` | Remotion DualTalk; ffmpeg caption fallback if Remotion unavailable |
| `status --case ID` | Pipeline summary from FS + SQLite |
| `index` | Rebuild SQLite from `content/data/cases/**` |

### Voices (MVP)

- Doctor / colleague / expert: `en-US-GuyNeural`
- Parent / patient-family counterpart: `en-US-JennyNeural`

---

## 6. Gemini generation

- SDK: `google-genai`
- Model: configurable via env `STUDIO_GEMINI_MODEL` (default a current Gemini flash/pro suitable for structured JSON)
- Input: `case.json` metadata + full `source.txt` (truncate with clear warning if over token budget; prefer page-bounded ingest)
- Output: structured JSON matching studio dialogue schema
- Prompts: three context system prompts (patient/family layman; colleague+SBAR; expert/CME formal) × CEFR controls (vocab, length, formality)
- Target duration: ~2 minutes spoken English per dialogue at 1x (soft guideline in prompt)
- On schema failure: one retry; then write `generate_error.json` and leave previous accepted files untouched

Env: `GEMINI_API_KEY` required unless `--mock`.

---

## 7. DualTalk Remotion composition

**Composition id:** `DualTalk` in `video/remotion`.

- Two fixed panels (left speaker A, right speaker B)
- Active speaker highlighted; idle dimmed
- Static avatar images (placeholders in repo under `video/remotion/public/avatars/`)
- English captions with word-level highlight from `timestamps.json`
- Optional smaller Vietnamese line when `text_vi` present
- Watermark/footer: title + ISBN/edition (and page range if present)
- Props file generated by `studio render` into the case folder before invoking Remotion CLI

**Fallback:** ffmpeg concat of line audio + simple SRT burn-in; record `engine=ffmpeg` in asset metadata / status output.

Existing `Karaoke` composition remains for learner export; DualTalk is studio-specific and may later feed Phase 2.

---

## 8. Error handling

| Situation | Behavior |
|-----------|----------|
| Missing `GEMINI_API_KEY` (non-mock) | Exit non-zero with clear message |
| Invalid Gemini JSON after retry | `generate_error.json`; no clobber of `accepted` dialogues |
| Lines missing `source_quote` | Dialogue stays / becomes `needs_review`; block synth/render without `--force` |
| Per-dialogue TTS/render failure | Continue siblings; mark asset `failed` |
| PDF text extraction empty | Require `--text-file` |
| Remotion missing | Automatic ffmpeg fallback + warning |

---

## 9. Testing strategy

- Schema unit tests for studio dialogue (valid / missing speaker / empty text)
- Review state machine tests (accept/reject updates files + review.json)
- Manifest index tests with temp directories
- `generate --mock` writes 9 valid files from fixture source
- TTS/Remotion: mock or skip heavy deps in CI; ffmpeg fallback path tested with tiny wav/mp3 fixture when available
- No dependency on real Nelson PDF in CI (synthetic fixture only)

---

## 10. Definition of done (Phase 1 MVP)

1. `content/` CLI installable via `uv sync` and documented in `content/README.md`
2. Fixture case can run: ingest (text) → generate mock → review accept one → synthesize → render (Remotion or ffmpeg)
3. Nine dialogue JSON files produced for a case (mock or live Gemini)
4. At least one DualTalk (or ffmpeg fallback) MP4 for an accepted dialogue
5. `studio status` reflects pipeline state accurately
6. Root README links to Content Studio Phase 1 briefly
7. `backend/` / `frontend/` learner behavior unchanged

---

## 11. Explicitly out of scope

- Google OAuth, RBAC, editor UI fact review
- Learner karaoke/shadowing/role-play changes
- Azure Pronunciation Assessment, SRS, gamification
- MuseTalk / SadTalker / MultiTalk photoreal talking heads
- Mobile / Capacitor
- Publishing dialogues into production learner DB (Phase 2 import)

---

## 12. Phase 2 handoff (non-binding)

Later work may import `content/data/cases/**` into Cloud SQL / app `Case` + `Dialogue` tables, then attach learning pathways. Studio schemas should stay compatible with existing `context` / `cefr_level` enums to minimize remapping.
