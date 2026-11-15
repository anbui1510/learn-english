from __future__ import annotations

from datetime import date, timedelta

from app.learner.srs import SrsRepository, next_interval_days
from app.users.repository import UserRepository


def test_sm2_interval_ladder() -> None:
    assert next_interval_days(1) == 1
    assert next_interval_days(2) == 3
    assert next_interval_days(3) == 7
    assert next_interval_days(4) == 14
    assert next_interval_days(99) == 14


def test_mark_done_advances_due_and_repetition(tmp_path) -> None:
    db = str(tmp_path / "srs-sm2.sqlite3")
    users = UserRepository(db)
    learner = users.upsert_google_user(
        google_sub="srs-sm2",
        email="srs-sm2@example.com",
        name="S",
        bootstrap_admin_emails=set(),
    )
    repo = SrsRepository(db)
    created = repo.enqueue_from_score(
        user_id=learner.id,
        attempt_id=None,
        score={"words": [{"word": "cyanosis", "band": "red", "accuracy": 30}]},
    )
    assert len(created) == 1
    assert created[0].repetition == 0

    first = repo.mark_done(card_id=created[0].id, user_id=learner.id)
    assert first is not None
    assert first.repetition == 1
    assert first.done_at is None
    assert first.due_at == (date.today() + timedelta(days=1)).isoformat()
    assert repo.list_due(learner.id, on_or_before=date.today().isoformat()) == []

    # Simulate the card becoming due again.
    with repo._conn() as conn:
        conn.execute(
            "UPDATE srs_cards SET due_at = ? WHERE id = ?",
            (date.today().isoformat(), first.id),
        )
        conn.commit()

    second = repo.mark_done(card_id=first.id, user_id=learner.id)
    assert second is not None
    assert second.repetition == 2
    assert second.due_at == (date.today() + timedelta(days=3)).isoformat()


def test_pa_miss_resets_repetition(tmp_path) -> None:
    db = str(tmp_path / "srs-reset.sqlite3")
    users = UserRepository(db)
    learner = users.upsert_google_user(
        google_sub="srs-reset",
        email="srs-reset@example.com",
        name="R",
        bootstrap_admin_emails=set(),
    )
    repo = SrsRepository(db)
    card = repo.enqueue_from_score(
        user_id=learner.id,
        attempt_id=None,
        score={"words": [{"word": "rales", "band": "yellow", "accuracy": 60}]},
    )[0]
    advanced = repo.mark_done(card_id=card.id, user_id=learner.id)
    assert advanced is not None and advanced.repetition == 1

    again = repo.enqueue_from_score(
        user_id=learner.id,
        attempt_id=None,
        score={"words": [{"word": "rales", "band": "red", "accuracy": 20}]},
    )[0]
    assert again.repetition == 0
    assert again.due_at == (date.today() + timedelta(days=1)).isoformat()
