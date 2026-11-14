# Schemas

Shared **JSON Schema draft-07** contracts for clinical fact cards, dialogue artifacts, and Case ownership.
Downstream extraction, ingest, and dialogue epics should import these files rather than inventing parallel shapes.

## Schema files

| Contract | Path | Covers |
|----------|------|--------|
| Clinical fact card | `schemas/clinical-fact.schema.json` | `source_quote`, `metadata` (ISBN, edition, page, optional chapter/section), `atomic_fact`, `category`, `status` ∈ `needs_review` \| `verified`, optional `id` |
| Dialogue artifact | `schemas/dialogue.schema.json` | `context` ∈ `patient_family` \| `colleague_sbar` \| `expert_cme`, `cefr_level` ∈ `A2` \| `B1` \| `C1`, `lines[]` each with non-empty `fact_ids` |
| Case | `schemas/case.schema.json` | `owner_user_id` (editor/admin user id), `title`, `status` ∈ `draft` \| `published`, optional ISBN/edition |

## Fixtures

| Fixture | Path | Expected |
|---------|------|----------|
| Valid fact | `schemas/fixtures/clinical-fact.valid.json` | Passes |
| Invalid fact | `schemas/fixtures/clinical-fact.invalid.json` | Fails (missing `source_quote`, illegal `status`) |
| Valid dialogue | `schemas/fixtures/dialogue.valid.json` | Passes |
| Invalid dialogue | `schemas/fixtures/dialogue.invalid-empty-fact-ids.json` | Fails (empty `fact_ids`) |
| Valid case | `schemas/fixtures/case.valid.json` | Passes |
| Invalid case | `schemas/fixtures/case.invalid-missing-owner.json` | Fails (missing `owner_user_id`) |

Fixture strings are **examples only** — not clinical guidance.

## Validate

From the repo root (requires `uv` on `PATH`, including `$HOME/.local/bin` if needed):

```bash
cd backend && uv sync && uv run pytest tests/test_schemas.py -q
```

The test loads the schema files above and asserts the fixture matrix with the `jsonschema` Draft-07 validator.
