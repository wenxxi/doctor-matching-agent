import hashlib
import re
import secrets
import threading
import uuid
import weakref
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta

from fastapi import HTTPException
from langgraph.types import Command
from sqlalchemy import delete, func, select, or_, and_
from sqlalchemy.orm import Session

from app.agent_models import AgentOwner, AgentTask, CareCase, CaseMessage
from app.agent_schemas import AgentTaskResponse, CaseDetailResponse, CaseMessagesPage
from app.services.agent_storage import checkpoint_store
from app.services.care_graph import build_care_graph, CareGraphState
from app.services.intake import SENSITIVE
from app.services.privacy import ensure_safe_text
from app.services.security import security_engine, storage_lock


LOCKS = weakref.WeakValueDictionary()
LOCKS_GUARD = threading.Lock()


@contextmanager
def case_lock(case_id):
    with LOCKS_GUARD:
        lock = LOCKS.get(str(case_id))
        if lock is None:
            lock = threading.Lock()
            LOCKS[str(case_id)] = lock
    with lock:
        yield


def create_owner(session):
    security_engine()
    storage_lock(session)
    if session.scalar(select(func.count()).select_from(AgentOwner)) >= 5000:
        raise HTTPException(429, "個案服務暫時達容量上限，請稍後重試。")
    token = secrets.token_urlsafe(32)
    owner = AgentOwner(token_hash=hashlib.sha256(token.encode()).hexdigest())
    session.add(owner)
    session.commit()
    return token


def authenticate_owner(session, token):
    if not token or not 30 <= len(token) <= 100:
        raise HTTPException(status_code=401, detail="請重新啟用此瀏覽器的個案記憶。")
    owner = session.scalar(select(AgentOwner).where(AgentOwner.token_hash == hashlib.sha256(token.encode()).hexdigest()))
    if owner is None:
        raise HTTPException(status_code=401, detail="個案存取憑證無效。")
    if owner.created_at.replace(tzinfo=timezone.utc) < datetime.now(timezone.utc) - timedelta(days=180):
        raise HTTPException(401, "個案存取憑證已到期，請重新啟用個案記憶。")
    return owner


def owned_case(session, owner, case_id, lock=False):
    query = select(CareCase).where(CareCase.id == case_id, CareCase.owner_id == owner.id)
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    case = session.scalar(query)
    if case is None:
        raise HTTPException(status_code=404, detail="找不到此個案。")
    return case


def current_task(session, case):
    task = session.scalar(select(AgentTask).where(AgentTask.case_id == case.id).order_by(AgentTask.created_at.desc(), AgentTask.id.desc()).limit(1))
    if task is None:
        task = AgentTask(case_id=case.id, snapshot={})
        session.add(task)
        session.flush()
    return task


def message_page(session, case, before=None, limit=50):
    query = select(CaseMessage).where(CaseMessage.case_id == case.id)
    if before:
        cursor = session.scalar(select(CaseMessage).where(CaseMessage.case_id == case.id, CaseMessage.id == before))
        if cursor is None:
            raise HTTPException(404, "找不到此個案的歷史位置。")
        query = query.where(or_(CaseMessage.created_at < cursor.created_at,
                               and_(CaseMessage.created_at == cursor.created_at, CaseMessage.id < cursor.id)))
    rows = session.scalars(query.order_by(CaseMessage.created_at.desc(), CaseMessage.id.desc()).limit(limit + 1)).all()
    selected = rows[:limit]
    return CaseMessagesPage(messages=list(reversed(selected)), next_cursor=selected[-1].id if len(rows) > limit else None)


def case_detail(session, case):
    task = current_task(session, case)
    values = task.snapshot
    page = message_page(session, case)
    return CaseDetailResponse(
        case=case, messages=page.messages, messages_cursor=page.next_cursor,
        task=AgentTaskResponse(
            id=task.id, status=task.status, version=task.version,
            intake=values.get("intake", {}), intake_response=values.get("intake_response"),
            recommendation=values.get("recommendation") if values.get("intake_response", {}).get("ready") else None,
            preparation=values.get("preparation"), trace=values.get("trace", []),
            booking_status=values.get("booking_status"),
            booking_receipt_number=values.get("booking_receipt_number"),
        ),
    )


def ensure_safe_message(message):
    ensure_safe_text(message)
    if SENSITIVE.search(message) or re.search(r"(?:生日|出生日期|護照|病歷號)\s*[:：]?\s*[0-9A-Za-z]", message):
        raise HTTPException(status_code=422, detail="證號、生日與驗證碼請填在掛號表單，不存入個案對話。")


def create_case(session, owner, title, subject_label):
    ensure_safe_message(title)
    ensure_safe_message(subject_label)
    security_engine()
    storage_lock(session)
    if session.scalar(select(func.count()).select_from(CareCase)) >= 5000:
        raise HTTPException(429, "個案儲存空間已達上限，請稍後重試。")
    if session.scalar(select(func.count()).select_from(CareCase).where(CareCase.owner_id == owner.id)) >= 50:
        raise HTTPException(status_code=409, detail="此瀏覽器已建立 50 個個案，請先刪除不需要的個案。")
    case = CareCase(owner_id=owner.id, title=title.strip() or "新的就醫個案", subject_label=subject_label.strip() or "自己")
    session.add(case)
    session.flush()
    session.add(AgentTask(case_id=case.id, snapshot={}))
    session.commit()
    return case_detail(session, case)


def run_case(session, owner, case_id, request, action="message"):
    if action == "message":
        ensure_safe_message(request.message)
        if request.message.strip() in {"重新開始", "清除記憶", "清除對話", "重設條件"}:
            raise HTTPException(status_code=409, detail="這是已儲存個案。要清除全部對話與記憶，請使用「刪除此個案」；要處理新問題，請建立新個案。")
    with case_lock(case_id):
        case = owned_case(session, owner, case_id, lock=True)
        task = current_task(session, case)
        already_handled = session.scalar(select(CaseMessage.id).where(CaseMessage.task_id == task.id, CaseMessage.operation_id == request.operation_id).limit(1))
        if already_handled:
            return case_detail(session, case)
        if session.scalar(select(func.count()).select_from(CaseMessage).where(CaseMessage.case_id == case.id)) >= 1000:
            raise HTTPException(409, "此個案已達對話上限，請建立新個案。")
        if task.version != request.expected_version:
            raise HTTPException(status_code=409, detail="個案已在其他分頁更新，請重新載入個案。")
        if task.snapshot.get("booking_status") in {"submitting", "awaiting_confirmation"}:
            raise HTTPException(status_code=409, detail="此任務已有掛號送出流程，請先完成確認或查詢院方結果。")
        if task.snapshot.get("booking_status") in {"unknown", "needs_official"} and (
            action != "message" or request.message != "已向院方確認未掛號，重新安排"
        ):
            raise HTTPException(status_code=409, detail="請先至院方確認結果；確認未掛號後，可輸入「已向院方確認未掛號，重新安排」。")
        if action == "prepare" and task.status not in {"selecting_doctor", "awaiting_patient"}:
            raise HTTPException(status_code=409, detail="請先完成就醫條件並取得推薦醫師。")
        if action == "prepare" and request.doctor_id not in {
            doctor["doctor_id"] for doctor in (task.snapshot.get("recommendation") or {}).get("recommended_doctors", [])
        }:
            raise HTTPException(status_code=409, detail="請選擇此個案目前推薦名單中的醫師。")
        if task.status in {"needs_verification", "human_required"} and action == "prepare":
            raise HTTPException(status_code=409, detail="請先確認上一筆院方掛號結果，不可直接重送。")
        if case.status == "resolved":
            raise HTTPException(status_code=409, detail="此個案已結案，請先重新開啟。")
        command = {"action": action, "operation_id": str(request.operation_id)}
        if action == "message":
            command["message"] = request.message
        else:
            command.update(doctor_id=request.doctor_id, preferences=request.preferences.model_dump(mode="json"))
        with checkpoint_store() as saver:
            graph = build_care_graph(saver)
            previous_intake = task.snapshot.get("intake", {})
            if task.status in {"completed", "needs_verification", "human_required", "closed"}:
                if session.scalar(select(func.count()).select_from(AgentTask).where(AgentTask.case_id == case.id)) >= 100:
                    raise HTTPException(409, "此個案已達任務上限，請建立新個案。")
                if action != "message":
                    raise HTTPException(status_code=409, detail="請先重新描述或確認就醫需求。")
                task = AgentTask(case_id=case.id, snapshot={}, version=task.version)
                session.add(task)
                session.flush()
                session.commit()
            config = {"configurable": {"thread_id": str(task.id)}}
            checkpoint = graph.get_state(config)
            try:
                if checkpoint.values.get("operation_id") == str(request.operation_id):
                    values = graph.invoke(None, config) if checkpoint.next and not checkpoint.interrupts else dict(checkpoint.values)
                elif checkpoint.next:
                    values = graph.invoke(Command(resume=command), config)
                else:
                    values = graph.invoke({"message": command["message"], "operation_id": str(request.operation_id), "intake": previous_intake, "trace": []}, config)
            except HTTPException:
                # Admission failures must not leave a partly advanced graph that replays
                # an old message when the user retries with a different operation ID.
                saver.delete_thread(str(task.id))
                if task.snapshot:
                    source_node = {"clarifying": "understand", "selecting_doctor": "recommend", "awaiting_patient": "prepare"}.get(task.status)
                    if source_node:
                        snapshot = {key: value for key, value in task.snapshot.items() if key in CareGraphState.__annotations__}
                        graph.update_state(config, snapshot, as_node=source_node)
                        graph.invoke(None, config)  # Rebuild the previous human interrupt; no model/tool call.
                raise
        values.pop("__interrupt__", None)
        task.snapshot = dict(values)
        task.status = values["phase"]
        task.version += 1
        case.updated_at = datetime.now(timezone.utc)
        text = request.message if action == "message" else f"請助理安排醫師 {request.doctor_id} 的門診時段。"
        reply = values.get("preparation", {}).get("message") if action == "prepare" else values.get("intake_response", {}).get("reply")
        written_at = datetime.now(timezone.utc)
        session.add_all([
            CaseMessage(case_id=case.id, task_id=task.id, operation_id=request.operation_id, role="user", content=text, created_at=written_at),
            CaseMessage(case_id=case.id, task_id=task.id, operation_id=request.operation_id, role="assistant", content=reply or "個案進度已更新。", created_at=written_at + timedelta(microseconds=1)),
        ])
        session.commit()
        return case_detail(session, case)


def delete_case(session, owner, case_id, *, older_than=None):
    with case_lock(case_id):
        case = owned_case(session, owner, case_id, lock=True)
        if older_than is not None and case.updated_at.replace(tzinfo=timezone.utc) >= older_than:
            return False
        if current_task(session, case).snapshot.get("booking_status") == "submitting":
            raise HTTPException(409, "掛號正在送出，請先等候院方結果。")
        tasks = session.scalars(select(AgentTask).where(AgentTask.case_id == case.id)).all()
        with checkpoint_store() as saver:
            for task in tasks:
                saver.delete_thread(str(task.id))
        session.execute(delete(CaseMessage).where(CaseMessage.case_id == case.id))
        session.execute(delete(AgentTask).where(AgentTask.case_id == case.id))
        session.delete(case)
        session.commit()
        return True


def validate_booking_task(session, owner, task_id, registration_url):
    task = session.get(AgentTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="找不到任務。")
    case = owned_case(session, owner, task.case_id)
    preparation = task.snapshot.get("preparation") or {}
    selected = preparation.get("selected_slot") or {}
    if case.status != "active" or task.status != "awaiting_patient" or selected.get("registration_url") != registration_url:
        raise HTTPException(status_code=409, detail="此任務的醫師或時段已變更，請重新安排。")
    if task.snapshot.get("booking_status") not in {None, "awaiting_patient", "captcha_error"}:
        raise HTTPException(status_code=409, detail="此任務已有送出紀錄，請先確認院方結果。")
    return task


def observe_booking(task_id, expected_version, status, receipt_number=None, *, booking_token=None, expected_booking_status=None):
    from app.services.agent_storage import initialize_agent_storage

    with Session(initialize_agent_storage(), expire_on_commit=False) as session:
        task = session.get(AgentTask, task_id)
        if task is None:
            return False
        with case_lock(task.case_id):
            case = session.scalar(select(CareCase).where(CareCase.id == task.case_id).with_for_update())
            task = session.scalar(select(AgentTask).where(AgentTask.id == task_id).with_for_update().execution_options(populate_existing=True))
            if task.version != expected_version:
                return False
            binding = hashlib.sha256(booking_token.encode()).hexdigest() if booking_token else None
            current_binding = task.snapshot.get("booking_session_hash")
            if (status == "awaiting_patient" and binding and task.snapshot.get("booking_status") in {"awaiting_patient", "captcha_error"}
                    and task.snapshot.get("booking_session_expires", 2**62) <= datetime.now(timezone.utc).timestamp()):
                current_binding = None  # Only an unsubmitted, expired claim can be replaced.
            if current_binding and current_binding != binding:
                return False
            if status == "awaiting_patient" and binding and not current_binding:
                if case.status != "active" or task.status != "awaiting_patient" or task.snapshot.get("booking_status") not in {None, "awaiting_patient", "captcha_error"}:
                    return False
            if status == "submitting" and (case.status != "active" or task.status != "awaiting_patient"):
                return False
            if status == "submitting" and (
                task.snapshot.get("booking_status") not in {"awaiting_patient", "captcha_error", "awaiting_confirmation"}
                or (expected_booking_status is not None and task.snapshot.get("booking_status") != expected_booking_status)
            ):
                return False
            values = dict(task.snapshot)
            if binding:
                values["booking_session_hash"] = binding
                if not current_binding:
                    values["booking_session_expires"] = int(datetime.now(timezone.utc).timestamp()) + 600
            values["booking_status"] = status
            if status in {"confirmed", "unknown", "needs_official", "rejected"}:
                with checkpoint_store() as saver:
                    graph = build_care_graph(saver)
                    config = {"configurable": {"thread_id": str(task.id)}}
                    if graph.get_state(config).next:
                        values = graph.invoke(Command(resume={"action": "booking_outcome", "booking_status": status, "receipt_number": receipt_number, "operation_id": str(uuid.uuid4())}), config)
                        values.pop("__interrupt__", None)
                task.status = values["phase"]
                task.version += 1
            task.snapshot = values
            session.commit()
            return True


def release_booking_claim(task_id, version, token):
    from app.services.agent_storage import initialize_agent_storage
    with Session(initialize_agent_storage()) as session:
        task = session.get(AgentTask, task_id)
        if task is None:
            return
        with case_lock(task.case_id):
            task = session.scalar(select(AgentTask).where(AgentTask.id == task_id).with_for_update().execution_options(populate_existing=True))
            if (task.version == version and task.snapshot.get("booking_session_hash") == hashlib.sha256(token.encode()).hexdigest()
                    and task.snapshot.get("booking_status") in {"awaiting_patient", "captcha_error"}):
                values = dict(task.snapshot)
                values.pop("booking_session_hash", None)
                values.pop("booking_session_expires", None)
                task.snapshot = values
                session.commit()
