import json
from datetime import date
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.intake_schemas import IntakeRequest, IntakeState
from app.main import app
from app.services import intake


@pytest.fixture(autouse=True)
def local_mode(monkeypatch):
    monkeypatch.setattr(intake, "get_openai_settings", lambda: SimpleNamespace(api_key=None))
    monkeypatch.setattr(intake, "taipei_today", lambda: date(2026, 11, 23))


def turn(message, state=None):
    return intake.intake_turn(IntakeRequest(message=message, state=state or IntakeState()))


def ready_state():
    return IntakeState(clinical_query="膝蓋疼痛", patient_type="returning", date_from="2026-11-30",
                       date_to="2026-12-06", date_range_known=True, sessions=["下午"])


def test_only_asks_for_missing_information_over_multiple_turns():
    first = turn("我膝蓋運動後會痛")
    assert first.state.clinical_query
    assert first.question == "patient_type"
    assert not first.ready
    second = turn("我是複診", first.state)
    assert second.question == "date_range"
    assert second.state.patient_type == "returning"
    third = turn("下週下午", second.state)
    assert third.ready
    assert third.question is None
    assert third.state.clinical_query == first.state.clinical_query
    assert third.state.date_from == date(2026, 11, 30)
    assert third.state.date_to == date(2026, 12, 6)
    assert third.state.sessions == ["下午"]


def test_weekday_exclusion_retains_symptoms_dates_sessions_and_patient_type():
    original = ready_state()
    response = turn("週三不行", original)
    assert response.ready
    assert response.state.weekdays == [0, 1, 3, 4, 5, 6]
    assert response.state.model_dump(exclude={"weekdays"}) == original.model_dump(exclude={"weekdays"})
    restored = turn("週三也可以", response.state)
    assert restored.state.weekdays == list(range(7))


def test_complete_initial_goal_requires_no_redundant_question():
    response = turn("我是複診，膝蓋疼痛想看骨科，下週下午，週三不行")
    assert response.ready
    assert response.state.sessions == ["下午"]
    assert 2 not in response.state.weekdays


def test_unsure_patient_type_is_remembered_without_repeated_question():
    response = turn("不確定是不是科初診", ready_state().model_copy(update={"patient_type": None}))
    assert response.ready
    assert response.state.patient_type == "unknown"


def test_unrestricted_answers_are_explicitly_remembered():
    state = turn("膝蓋疼痛").state
    state = turn("不確定", state).state
    state = turn("日期不限", state).state
    response = turn("時段不限", state)
    assert response.ready
    assert response.state.date_range_known
    assert response.state.date_from is None and response.state.date_to is None
    assert response.state.sessions == ["上午", "下午", "夜診"]


def test_unrestricted_weekdays_do_not_erase_date_or_session_constraints():
    original = ready_state()
    response = turn("星期不限", original)
    assert response.state.model_dump(exclude={"weekdays"}) == original.model_dump(exclude={"weekdays"})
    missing_dates = original.model_copy(update={"date_range_known": False})
    assert turn("星期不限", missing_dates).question == "date_range"


def test_weekend_goal_and_weekday_goal_are_applied():
    weekend = turn("下週末下午", ready_state())
    assert weekend.state.weekdays == [5, 6]
    weekdays = turn("平日晚上", ready_state())
    assert weekdays.state.weekdays == [0, 1, 2, 3, 4]
    assert weekdays.state.sessions == ["夜診"]


def test_corrections_update_only_relevant_fields():
    original = ready_state()
    response = turn("改成上午", original)
    assert response.state.sessions == ["上午"]
    assert response.state.model_dump(exclude={"sessions"}) == original.model_dump(exclude={"sessions"})
    assert turn("日期不限", response.state).state.date_from is None


@pytest.mark.parametrize("message", ["不要週三", "不能週三", "排除週三"])
def test_weekday_negation_prefix_is_preserved(message):
    response = turn(message, ready_state())
    assert response.ready
    assert response.state.weekdays == [0, 1, 3, 4, 5, 6]


def test_session_exclusion_and_replacement_in_same_message():
    response = turn("下午不行，晚上可以", ready_state())
    assert response.ready
    assert response.state.sessions == ["夜診"]


def test_negated_patient_type_requires_clarification():
    response = turn("不是複診", ready_state())
    assert not response.ready
    assert response.question == "patient_type"


def test_unknown_new_constraint_is_not_silently_accepted():
    original = ready_state()
    response = turn("改成下班以後", original)
    assert response.state == original
    assert not response.ready
    assert "還沒確認" in response.reply


def test_invalid_dates_preserve_existing_state():
    original = ready_state()
    for message in ("2026-12-10到2026-12-01", "2026-13-40"):
        response = turn(message, original)
        assert response.state == original
        assert not response.ready


@pytest.mark.parametrize("today, expected", [
    (date(2026, 11, 23), date(2026, 11, 30)),
    (date(2026, 11, 29), date(2026, 11, 30)),
    (date(2026, 12, 28), date(2027, 1, 4)),
])
def test_relative_week_is_anchored_to_taipei_calendar(monkeypatch, today, expected):
    monkeypatch.setattr(intake, "taipei_today", lambda: today)
    assert turn("下週", ready_state()).state.date_from == expected


def test_unsupported_hospital_is_not_silently_changed():
    response = turn("改去台大", ready_state())
    assert response.question == "hospital"
    assert response.state.hospital == "台大"
    assert not response.ready
    assert turn("可以", response.state).state.hospital == "林口長庚"


def test_expired_preference_requires_date_confirmation():
    state = ready_state().model_copy(update={"date_to": date(2026, 11, 22), "date_from": date(2026, 11, 20)})
    response = turn("我是複診", state)
    assert response.question == "date_range"
    assert not response.ready


def test_reset_clears_conditions():
    response = turn("清除記憶", ready_state())
    assert response.state == IntakeState()
    assert response.question == "clinical_query"


def test_empty_weekday_availability_is_not_ready():
    state = ready_state().model_copy(update={"weekdays": [2]})
    response = turn("週三不行", state)
    assert response.question == "weekdays"
    assert not response.ready
    assert turn("星期不限", response.state).ready


def test_model_receives_structured_memory_and_unmentioned_fields_are_preserved(monkeypatch):
    original = ready_state()
    payload = {
        "updated_fields": ["weekdays"], "clinical_query": "should not replace symptoms",
        "hospital": "台大", "patient_type": "first_visit", "date_from": None,
        "date_to": None, "sessions": ["上午"], "weekdays": [0, 1, 3, 4, 5, 6],
    }
    calls = []

    class FakeClient:
        def with_options(self, **kwargs):
            return self

        @property
        def responses(self):
            return self

        def create(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(output_text=json.dumps(payload))

    monkeypatch.setattr(intake, "get_openai_settings", lambda: SimpleNamespace(api_key="test"))
    monkeypatch.setattr(intake, "get_openai_client", FakeClient)
    monkeypatch.setattr(intake, "get_openai_model", lambda: "test-model")
    response = turn("週三不行", original)
    assert response.extraction_method == "openai"
    assert response.state.model_dump(exclude={"weekdays"}) == original.model_dump(exclude={"weekdays"})
    sent = json.loads(calls[0]["input"])
    assert sent["state"]["clinical_query"] == original.clinical_query
    assert sent["today_taipei"] == "2026-11-23"


def test_model_error_uses_local_parser(monkeypatch):
    def fail_client():
        raise RuntimeError("test")

    monkeypatch.setattr(intake, "get_openai_settings", lambda: SimpleNamespace(api_key="test"))
    monkeypatch.setattr(intake, "get_openai_client", fail_client)
    response = turn("週三不行", ready_state())
    assert response.ready
    assert response.extraction_method == "local"
    assert 2 not in response.state.weekdays


def test_explicit_dates_and_weekday_edits_override_model_miscalculation(monkeypatch):
    monkeypatch.setattr(intake, "get_openai_settings", lambda: SimpleNamespace(api_key="test"))
    monkeypatch.setattr(intake, "llm_updates", lambda *args: {"weekdays": [0, 1, 4, 5, 6]})
    response = turn("下週下午，週三不行", ready_state().model_copy(update={"date_range_known": False, "date_from": None, "date_to": None}))
    assert response.ready
    assert response.state.date_from == date(2026, 11, 30)
    assert response.state.date_to == date(2026, 12, 6)
    assert response.state.weekdays == [0, 1, 3, 4, 5, 6]


def test_sensitive_identifier_is_not_sent_to_model(monkeypatch):
    calls = []
    monkeypatch.setattr(intake, "get_openai_settings", lambda: SimpleNamespace(api_key="test"))
    monkeypatch.setattr(intake, "get_openai_client", lambda: calls.append(True))
    response = turn("證號TEST000000", ready_state())
    assert not calls
    assert not response.ready
    assert response.state == ready_state()
    assert "未送交語言模型" in response.reply


def test_chat_api_accepts_memory_and_sanitizes_validation_errors():
    client = TestClient(app)
    response = client.post("/api/intake/chat", json={"message": "週三不行", "state": ready_state().model_dump(mode="json")})
    assert response.status_code == 200
    assert response.json()["ready"]
    assert response.json()["state"]["weekdays"] == [0, 1, 3, 4, 5, 6]
    assert "no-store" in response.headers["cache-control"]
    invalid = client.post("/api/intake/chat", json={"message": "private-health-description", "state": {"weekdays": [9]}})
    assert invalid.status_code == 422
    assert "private-health-description" not in invalid.text
