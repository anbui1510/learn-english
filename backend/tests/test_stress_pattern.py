from __future__ import annotations

from app.dialogues.generator import TemplateDialogueGenerator, build_stress_pattern
from app.facts.repository import FactRecord
from app.learner.pronunciation import WordScore, _stress_hint
from tests.test_schemas import _validator


def test_build_stress_pattern_peaks_on_long_token() -> None:
    pattern = build_stress_pattern(
        "Review electrocardiogram findings carefully today"
    )
    assert pattern is not None
    assert len(pattern) == 5
    assert max(pattern) == 3
    assert pattern[1] == 3  # electrocardiogram


def test_build_stress_pattern_skips_short_words() -> None:
    assert build_stress_pattern("short words only here") is None


def test_stress_hint_gated_on_green_and_prosody() -> None:
    words = [
        WordScore(word="bronchiolitis", accuracy=90, band="green"),
        WordScore(word="care", accuracy=92, band="green"),
    ]
    assert (
        _stress_hint(
            cefr_level="C1",
            stress_pattern=[3, 1],
            words=words,
            prosody=80,
        )
        is None
    )
    hint = _stress_hint(
        cefr_level="C1",
        stress_pattern=[3, 1],
        words=words,
        prosody=60,
    )
    assert hint and "bronchiolitis" in hint.lower()


def test_stress_hint_when_stressed_word_not_green() -> None:
    words = [
        WordScore(word="bronchiolitis", accuracy=40, band="red"),
        WordScore(word="care", accuracy=90, band="green"),
    ]
    hint = _stress_hint(
        cefr_level="C1",
        stress_pattern=[3, 1],
        words=words,
        prosody=90,
    )
    assert hint and "bronchiolitis" in hint.lower()


def test_c1_generator_emits_valid_stress_pattern() -> None:
    facts = [
        FactRecord(
            id=1,
            case_id=1,
            source_quote="q",
            atomic_fact="Supportive care for bronchiolitis remains first-line.",
            category="treatment",
            status="verified",
            page=1,
            chapter=None,
            section=None,
            isbn="isbn",
            edition="1",
            created_at="t",
            updated_at="t",
        )
    ]
    payload = TemplateDialogueGenerator().generate(
        facts=facts,
        context="patient_family",
        cefr_level="C1",
        include_vi=False,
    )
    assert any("stress_pattern" in line for line in payload["lines"])
    _validator("dialogue.schema.json").validate(payload)


def test_b1_generator_skips_stress_pattern() -> None:
    facts = [
        FactRecord(
            id=1,
            case_id=1,
            source_quote="q",
            atomic_fact="Supportive care for bronchiolitis remains first-line.",
            category="treatment",
            status="verified",
            page=1,
            chapter=None,
            section=None,
            isbn="isbn",
            edition="1",
            created_at="t",
            updated_at="t",
        )
    ]
    payload = TemplateDialogueGenerator().generate(
        facts=facts,
        context="patient_family",
        cefr_level="B1",
        include_vi=False,
    )
    assert all("stress_pattern" not in line for line in payload["lines"])
