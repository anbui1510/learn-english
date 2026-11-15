from __future__ import annotations

from fastapi.testclient import TestClient

from app.auth.settings import AuthSettings
from app.learner.skill_tree import build_skill_tree, tree_to_dict
from tests.conftest import seed_admin_editor_learner, set_session_cookie
from tests.test_learner_stack import _published_with_dialogue


def test_skill_tree_locks_cardiology_until_foundations() -> None:
    nodes = build_skill_tree(
        cases_by_module={
            "peds-fever": [1],
            "peds-diarrhea": [2],
            "peds-respiratory": [3],
            "peds-cardiology": [4],
        },
        completed_case_ids=set(),
        certified_modules=set(),
    )
    payload = tree_to_dict(nodes)
    foundations = next(n for n in payload if n["slug"] == "peds-foundations")
    assert foundations["children"][0]["unlocked"] is True
    cardio = next(n for n in payload if n["slug"] == "peds-cardiology")
    assert cardio["unlocked"] is False
    assert "peds-foundations" in (cardio["unlock_reason"] or "")

    unlocked = build_skill_tree(
        cases_by_module={
            "peds-fever": [1],
            "peds-diarrhea": [2],
            "peds-respiratory": [3],
            "peds-cardiology": [4],
        },
        completed_case_ids={1, 2, 3},
        certified_modules=set(),
    )
    cardio2 = next(n for n in tree_to_dict(unlocked) if n["slug"] == "peds-cardiology")
    assert cardio2["unlocked"] is True


def test_word_replay_and_skill_tree_api(
    client: TestClient, auth_settings: AuthSettings
) -> None:
    case_id, dialogue_id = _published_with_dialogue(client, auth_settings)
    _, editor, learner = seed_admin_editor_learner(auth_settings)
    set_session_cookie(client, auth_settings, editor)
    assert (
        client.post(
            f"/editor/cases/{case_id}/dialogues/{dialogue_id}/synthesize"
        ).status_code
        == 200
    )
    client.patch(
        f"/editor/cases/{case_id}/progression",
        json={"module_slug": "peds-respiratory", "clear_unlock_requires_case": True},
    )

    set_session_cookie(client, auth_settings, learner)
    tree = client.get("/learner/skill-tree")
    assert tree.status_code == 200
    assert tree.json()["nodes"]

    lesson = client.get(f"/learner/dialogues/{dialogue_id}/lesson")
    assert lesson.status_code == 200
    word = lesson.json()["playlist"][0]["timestamps"][0]["word"]
    replay = client.get(
        f"/learner/dialogues/{dialogue_id}/lines/0/words/{word}/replay"
    )
    assert replay.status_code == 200, replay.text
    body = replay.json()
    assert body["audio_url"]
    assert body["end_ms"] > body["start_ms"]
