import uuid
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agent_models import AgentOwner, AgentTask, CareCase, CaseMessage
from app.main import app
from app.schemas import AppointmentPreparationResponse, AppointmentSlotResponse
from app.services import care_graph, intake
from app.services.agent_storage import checkpoint_store, get_agent_engine, initialize_agent_storage
from app.services.cases import observe_booking


@pytest.fixture
def database(monkeypatch, tmp_path):
    monkeypatch.setenv("AGENT_DATABASE_URL", f"sqlite:///{tmp_path / 'agent.sqlite3'}")
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.settings import get_openai_settings
    get_openai_settings.cache_clear()
    monkeypatch.setattr(intake, "taipei_today", lambda: date(2026, 11, 26))
    initialize_agent_storage.cache_clear()
    get_agent_engine.cache_clear()
    engine = initialize_agent_storage()
    yield engine
    engine.dispose()
    initialize_agent_storage.cache_clear()
    get_agent_engine.cache_clear()
    get_openai_settings.cache_clear()


@pytest.fixture
def client(database, verified_doctor_availability):
    return TestClient(app)


def owner(client):
    response = client.post("/api/agent/session")
    assert response.status_code == 200
    return {"X-Agent-Token": response.json()["token"]}


def create(client, headers, title="膝蓋問題"):
    response = client.post("/api/agent/cases", headers=headers, json={"title": title, "subject_label": "自己", "consent": True})
    assert response.status_code == 200, response.text
    return response.json()


def message(client, headers, case, text, operation=None):
    return client.post(f'/api/agent/cases/{case["case"]["id"]}/messages', headers=headers, json={
        "message": text, "expected_version": case["task"]["version"], "operation_id": operation or str(uuid.uuid4()),
    })


def ready_case(client, headers):
    case = create(client, headers)
    response = message(client, headers, case, "我是複診，膝蓋疼痛，下週下午")
    assert response.status_code == 200, response.text
    case = response.json()
    assert case["task"]["status"] == "selecting_doctor"
    return case


def prepare_case(client, headers, case, monkeypatch):
    doctor_id = case["task"]["recommendation"]["recommended_doctors"][0]["doctor_id"]
    slot = AppointmentSlotResponse(date="2026-11-30", session="下午", eligibility="一般掛號",
                                   registration_url="https://register.cgmh.org.tw/Checkin/3/32700A/20261130/2245/2")
    monkeypatch.setattr(care_graph, "prepare_appointment", lambda doctor, preferences: AppointmentPreparationResponse(
        doctor_id=doctor["doctor_id"], status="awaiting_patient", selected_slot=slot,
        verified_at=None, candidate_count=1, attempted_count=1, steps=["已確認時段"], message="等待填寫資料",
    ))
    response = client.post(f'/api/agent/cases/{case["case"]["id"]}/prepare', headers=headers, json={
        "doctor_id": doctor_id, "preferences": {"patient_type": "returning", "sessions": ["下午"]},
        "expected_version": case["task"]["version"], "operation_id": str(uuid.uuid4()),
    })
    assert response.status_code == 200, response.text
    return response.json()


def test_owner_tokens_are_hashed_and_access_is_isolated(client, database):
    headers = owner(client)
    case = create(client, headers)
    other = owner(client)
    assert client.get("/api/agent/cases", headers=other).json() == []
    for suffix in ("", "/resolve", "/reopen"):
        method = client.get if not suffix else client.post
        assert method("/api/agent/cases/" + case["case"]["id"] + suffix, headers=other).status_code == 404
    assert client.delete("/api/agent/cases/" + case["case"]["id"], headers=other).status_code == 404
    with Session(database) as session:
        assert all(row.token_hash != headers["X-Agent-Token"] for row in session.scalars(select(AgentOwner)))
    assert client.get("/api/agent/cases").status_code == 422


def test_consent_is_required_before_storing_health_case(client, database):
    headers = owner(client)
    response = client.post("/api/agent/cases", headers=headers, json={"title": "health", "consent": False})
    assert response.status_code == 422
    with Session(database) as session:
        assert session.scalar(select(func.count()).select_from(CareCase)) == 0


def test_graph_interrupts_and_resumes_with_persisted_case_memory(client):
    headers = owner(client)
    case = create(client, headers)
    first = message(client, headers, case, "膝蓋疼痛，下週下午").json()
    assert first["task"]["status"] == "clarifying"
    with checkpoint_store() as saver:
        graph = care_graph.build_care_graph(saver)
        checkpoint = graph.get_state({"configurable": {"thread_id": first["task"]["id"]}})
        assert checkpoint.interrupts
    reloaded = TestClient(app).get("/api/agent/cases/" + case["case"]["id"], headers=headers).json()
    second = message(client, headers, reloaded, "我是複診").json()
    assert second["task"]["status"] == "selecting_doctor"
    assert second["task"]["recommendation"]["recommended_doctors"]
    third = message(client, headers, second, "週三不行").json()
    assert third["task"]["intake"]["weekdays"] == [0, 1, 3, 4, 5, 6]
    assert third["task"]["intake"]["sessions"] == ["下午"]
    assert len(third["messages"]) == 6


def test_condition_changes_recheck_availability_instead_of_reusing_old_doctors(client, monkeypatch):
    import app.routers.recommendations as recommendations

    original = recommendations.filter_available_doctors
    calls = []

    def capture(candidates, preferences, limit):
        calls.append(preferences.model_dump(mode="json"))
        return original(candidates, preferences, limit)

    monkeypatch.setattr(recommendations, "filter_available_doctors", capture)
    headers = owner(client)
    case = ready_case(client, headers)
    updated = message(client, headers, case, "改成上午，週三不行").json()
    assert len(calls) == 2
    assert calls[0]["patient_type"] == calls[1]["patient_type"] == "returning"
    assert calls[0]["sessions"] == ["下午"]
    assert calls[1]["sessions"] == ["上午"]
    assert 2 not in calls[1]["weekdays"]
    assert updated["task"]["recommendation"]["recommended_doctors"][0]["availability"]["selected_slot"]["session"] == "上午"


def test_no_verified_slots_returns_to_clarification_instead_of_empty_doctor_selection(client, monkeypatch):
    from app.routers import recommendations

    monkeypatch.setattr(recommendations, "filter_available_doctors", lambda *args: ([], False))
    headers = owner(client)
    case = create(client, headers)
    response = message(client, headers, case, "我是複診，膝蓋疼痛，下週下午")
    assert response.status_code == 200
    task = response.json()["task"]
    assert task["status"] == "clarifying"
    assert task["intake_response"]["question"] == "availability"
    assert task["intake"]["sessions"] == ["下午"]
    assert any(item["node"] == "broaden" for item in task["trace"])
    with checkpoint_store() as saver:
        checkpoint = care_graph.build_care_graph(saver).get_state({"configurable": {"thread_id": task["id"]}})
        assert checkpoint.next == ("wait_for_details",)


def test_database_restart_does_not_lose_checkpoints_or_memory(client, database):
    headers = owner(client)
    case = ready_case(client, headers)
    database.dispose()
    initialize_agent_storage.cache_clear()
    get_agent_engine.cache_clear()
    reloaded = client.get("/api/agent/cases/" + case["case"]["id"], headers=headers).json()
    response = message(client, headers, reloaded, "改成上午")
    assert response.status_code == 200, response.text
    assert response.json()["task"]["intake"]["sessions"] == ["上午"]


def test_duplicate_message_is_idempotent_and_stale_version_is_rejected(client):
    headers = owner(client)
    case = create(client, headers)
    operation = str(uuid.uuid4())
    first = message(client, headers, case, "膝蓋疼痛", operation).json()
    repeated = message(client, headers, case, "膝蓋疼痛", operation)
    assert repeated.status_code == 200
    assert repeated.json()["task"]["version"] == first["task"]["version"]
    assert len(repeated.json()["messages"]) == 2
    assert message(client, headers, case, "下週").status_code == 409


def test_retry_resumes_an_interrupted_read_node_without_duplicate_turn(client, monkeypatch):
    headers = owner(client)
    case = create(client, headers)
    original = care_graph.intake_turn
    calls = []

    def fail_once(request):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("simulated process interruption")
        return original(request)

    monkeypatch.setattr(care_graph, "intake_turn", fail_once)
    operation = str(uuid.uuid4())
    request = {"message": "膝蓋疼痛，下週下午", "operation_id": operation, "expected_version": 0}
    path = "/api/agent/cases/" + case["case"]["id"] + "/messages"
    assert TestClient(app, raise_server_exceptions=False).post(path, headers=headers, json=request).status_code == 500
    retried = client.post(path, headers=headers, json=request)
    assert retried.status_code == 200, retried.text
    assert retried.json()["task"]["version"] == 1
    assert len(retried.json()["messages"]) == 2
    assert retried.json()["task"]["intake"]["sessions"] == ["下午"]


def test_clear_memory_in_saved_case_requires_explicit_case_deletion(client):
    headers = owner(client)
    case = ready_case(client, headers)
    response = message(client, headers, case, "清除記憶")
    assert response.status_code == 409
    assert "刪除此個案" in response.json()["detail"]
    current = client.get("/api/agent/cases/" + case["case"]["id"], headers=headers).json()
    assert current["messages"] == case["messages"]


def test_two_cases_never_share_symptoms_or_conditions(client):
    headers = owner(client)
    knee = ready_case(client, headers)
    eye = create(client, headers, "媽媽的眼睛問題")
    response = message(client, headers, eye, "眼睛酸澀，上午").json()
    assert response["task"]["intake"]["sessions"] == ["上午"]
    assert "膝" not in response["task"]["intake"]["clinical_query"]
    reloaded = client.get("/api/agent/cases/" + knee["case"]["id"], headers=headers).json()
    assert reloaded["task"]["intake"]["sessions"] == ["下午"]


def test_graph_calls_existing_preparation_tool_and_waits_for_patient(client, monkeypatch):
    headers = owner(client)
    case = prepare_case(client, headers, ready_case(client, headers), monkeypatch)
    assert case["task"]["status"] == "awaiting_patient"
    assert case["task"]["preparation"]["selected_slot"]
    with checkpoint_store() as saver:
        checkpoint = care_graph.build_care_graph(saver).get_state({"configurable": {"thread_id": case["task"]["id"]}})
        assert checkpoint.interrupts


def test_invalid_doctor_selection_never_advances_checkpoint(client):
    headers = owner(client)
    case = ready_case(client, headers)
    response = client.post("/api/agent/cases/" + case["case"]["id"] + "/prepare", headers=headers, json={
        "doctor_id": "not-in-recommendations", "preferences": {"patient_type": "returning"},
        "operation_id": str(uuid.uuid4()), "expected_version": case["task"]["version"],
    })
    assert response.status_code == 409
    current = client.get("/api/agent/cases/" + case["case"]["id"], headers=headers).json()
    assert current["task"]["version"] == case["task"]["version"]


def test_booking_outcome_resumes_graph_without_persisting_patient_data(client, monkeypatch):
    headers = owner(client)
    case = prepare_case(client, headers, ready_case(client, headers), monkeypatch)
    observe_booking(uuid.UUID(case["task"]["id"]), case["task"]["version"], "confirmed")
    result = client.get("/api/agent/cases/" + case["case"]["id"], headers=headers).json()
    assert result["task"]["status"] == "completed"
    assert result["task"]["booking_status"] == "confirmed"
    assert "verification" not in result["task"]
    with checkpoint_store() as saver:
        checkpoint = care_graph.build_care_graph(saver).get_state({"configurable": {"thread_id": case["task"]["id"]}})
        assert not checkpoint.next


def test_uncertain_booking_prevents_preparation_replay(client, monkeypatch):
    headers = owner(client)
    case = prepare_case(client, headers, ready_case(client, headers), monkeypatch)
    observe_booking(uuid.UUID(case["task"]["id"]), case["task"]["version"], "unknown")
    result = client.get("/api/agent/cases/" + case["case"]["id"], headers=headers).json()
    assert result["task"]["status"] == "needs_verification"
    response = client.post("/api/agent/cases/" + case["case"]["id"] + "/prepare", headers=headers, json={
        "doctor_id": "CGMH_LINKOU_ORTHO_001", "preferences": {"patient_type": "returning"},
        "expected_version": result["task"]["version"], "operation_id": str(uuid.uuid4()),
    })
    assert response.status_code == 409


def test_resolve_reopen_starts_new_task_but_retains_case_context(client):
    headers = owner(client)
    case = ready_case(client, headers)
    path = "/api/agent/cases/" + case["case"]["id"]
    resolved = client.post(path + "/resolve", headers=headers).json()
    assert message(client, headers, resolved, "改成上午").status_code == 409
    reopened = client.post(path + "/reopen", headers=headers).json()
    response = message(client, headers, reopened, "改成上午")
    assert response.status_code == 200, response.text
    updated = response.json()
    assert updated["task"]["id"] != case["task"]["id"]
    assert updated["task"]["intake"]["clinical_query"] == case["task"]["intake"]["clinical_query"]


def test_retry_after_reopen_keeps_the_operation_version(client, monkeypatch):
    headers = owner(client)
    case = ready_case(client, headers)
    path = "/api/agent/cases/" + case["case"]["id"]
    client.post(path + "/resolve", headers=headers)
    reopened = client.post(path + "/reopen", headers=headers).json()
    original = care_graph.intake_turn
    calls = []

    def fail_once(request):
        calls.append(True)
        if len(calls) == 1:
            raise RuntimeError("simulated restart after task creation")
        return original(request)

    monkeypatch.setattr(care_graph, "intake_turn", fail_once)
    payload = {"message": "改成上午", "operation_id": str(uuid.uuid4()), "expected_version": reopened["task"]["version"]}
    assert TestClient(app, raise_server_exceptions=False).post(path + "/messages", headers=headers, json=payload).status_code == 500
    retried = client.post(path + "/messages", headers=headers, json=payload)
    assert retried.status_code == 200, retried.text
    assert retried.json()["task"]["intake"]["sessions"] == ["上午"]


def test_delete_case_removes_messages_tasks_and_graph_checkpoints(client, database):
    headers = owner(client)
    case = ready_case(client, headers)
    response = client.delete("/api/agent/cases/" + case["case"]["id"], headers=headers)
    assert response.status_code == 204
    with Session(database) as session:
        for model in (CareCase, AgentTask, CaseMessage):
            assert session.scalar(select(func.count()).select_from(model)) == 0
    with checkpoint_store() as saver:
        assert saver.get_tuple({"configurable": {"thread_id": case["task"]["id"]}}) is None


def test_registration_identifiers_are_rejected_before_any_checkpoint_write(client):
    headers = owner(client)
    case = create(client, headers)
    response = message(client, headers, case, "證號TEST000000")
    assert response.status_code == 422
    assert "TEST000000" not in response.text
    result = client.get("/api/agent/cases/" + case["case"]["id"], headers=headers).json()
    assert result["messages"] == []


def test_render_without_postgres_keeps_persistent_memory_disabled(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("AGENT_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    get_agent_engine.cache_clear()
    initialize_agent_storage.cache_clear()
    try:
        response = TestClient(app).get("/api/agent/status")
        assert response.status_code == 200
        assert response.json()["available"] is False
    finally:
        get_agent_engine.cache_clear()
        initialize_agent_storage.cache_clear()


def test_linked_booking_is_scoped_and_reports_only_outcome_to_graph(client, monkeypatch):
    import secrets
    from datetime import datetime, timedelta, timezone
    from app.booking_schemas import BookingStateResponse
    from app.services import booking

    headers = owner(client)
    case = prepare_case(client, headers, ready_case(client, headers), monkeypatch)
    slot = AppointmentSlotResponse.model_validate(case["task"]["preparation"]["selected_slot"])
    calls = []

    def fake_start(doctor, url):
        token = secrets.token_urlsafe(32)
        booking.SESSIONS[token] = booking.BookingSession(
            client=None, doctor_name=doctor["doctor_name_zh"], slot=slot,
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=10), form=booking.HospitalForm(""),
        )
        return BookingStateResponse(status="awaiting_patient", token=token, message="test")

    def fake_submit(token, patient):
        calls.append(True)
        session = booking.get_session(token)
        session.status = "confirmed"
        session.response = BookingStateResponse(status="confirmed", receipt_number="42", message="test")
        return session.response

    monkeypatch.setattr(booking, "start_booking", fake_start)
    monkeypatch.setattr(booking, "submit_patient", fake_submit)
    body = {"doctor_id": case["task"]["preparation"]["doctor_id"], "registration_url": slot.registration_url, "task_id": case["task"]["id"]}
    assert client.post("/api/booking/sessions", headers=owner(client), json=body).status_code == 404
    started = client.post("/api/booking/sessions", headers=headers, json=body)
    assert started.status_code == 200, started.text
    token = started.json()["token"]
    response = client.post("/api/booking/submit", headers={"X-Booking-Token": token}, json={
        "id_type": "2", "id_number": "TEST000000", "birthday": "1990-01-01",
        "verification": "TEST", "consent": True,
    })
    assert response.status_code == 200, response.text
    reloaded = client.get("/api/agent/cases/" + case["case"]["id"], headers=headers)
    assert reloaded.json()["task"]["status"] == "completed"
    assert reloaded.json()["task"]["booking_receipt_number"] == "42"
    assert "TEST000000" not in reloaded.text
    assert "1990-01-01" not in reloaded.text
    with checkpoint_store() as saver:
        values = care_graph.build_care_graph(saver).get_state({"configurable": {"thread_id": case["task"]["id"]}}).values
        assert "TEST000000" not in str(values)
    assert calls == [True]
    booking.close_booking(token)
