from typing import TypedDict
from fastapi import HTTPException

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.intake_schemas import IntakeRequest, IntakeState
from app.schemas import AppointmentPreparationRequest, RecommendationRequest
from app.routers.recommendations import recommend_doctors
from app.services.appointment_agent import prepare_appointment
from app.services.intake import intake_turn
from app.services.processed_data import load_doctors
from app.services.hospitals import ALIASES


class CareGraphState(TypedDict, total=False):
    message: str
    operation_id: str
    intake: dict
    intake_response: dict
    recommendation: dict | None
    recommendation_query: str
    preparation: dict | None
    phase: str
    command: dict
    trace: list[dict[str, str]]
    booking_status: str | None
    booking_receipt_number: str | None


def step(state, node, message):
    return (state.get("trace", []) + [{"node": node, "message": message}])[-50:]


def understand(state):
    response = intake_turn(IntakeRequest(message=state["message"], state=IntakeState.model_validate(state.get("intake", {}))))
    return {"intake": response.state.model_dump(mode="json"), "intake_response": response.model_dump(mode="json"),
            "preparation": None, "booking_status": None, "phase": "clarifying",
            "trace": step(state, "understand", "讀取此個案條件，整理本輪需求。")}


def wait_for_details(state):
    command = interrupt({"phase": "clarifying", "reply": state["intake_response"]["reply"]})
    return {"message": command["message"], "operation_id": command["operation_id"], "command": command}


def recommend(state):
    query = state["intake"]["clinical_query"]
    try:
        intake = state["intake"]
        preferences = AppointmentPreparationRequest(
            patient_type=intake.get("patient_type") or "unknown",
            date_from=intake.get("date_from"), date_to=intake.get("date_to"),
            sessions=intake.get("sessions") or ["上午", "下午", "夜診"],
            weekdays=intake.get("weekdays", list(range(7))),
        )
        result = recommend_doctors(RecommendationRequest(query=query, preferences=preferences, hospital=ALIASES.get(intake.get("hospital"), intake.get("hospital", "林口長庚"))))
        if result.clarification_question:
            response = dict(state["intake_response"])
            response.update(ready=False, reply=result.clarification_question, question="clinical_query", quick_replies=[])
            return {"recommendation": None, "intake_response": response, "phase": "clarifying",
                    "trace": (step(state, "recommend", "目前醫療描述不足，先追問而不強制配對醫師。") + result.decision_trace)[-50:]}
        if not result.recommended_doctors:
            response = dict(state["intake_response"])
            provider_blocked = any(item.get("http_status") == 403 for item in result.provider_failures)
            response.update(ready=False, reply=(result.message or "目前沒有確認到符合條件的醫師門診。") + " 你可以修改就診條件後再查詢；我不會自行放寬條件。",
                            question="availability", quick_replies=["改成上午", "改成下午", "日期不限"])
            if provider_blocked:
                response.update(reply=(result.message or "院方限制本站查詢。") + " 原有就診條件已保留，不會自動改院。",
                                question="hospital_availability", quick_replies=["維持目前條件", "改成林口長庚"])
            return {"recommendation": result.model_dump(mode="json"), "intake_response": response, "phase": "clarifying",
                    "trace": (step(state, "recommend", "院方限制查詢，保留條件並等待重試或使用者改院。" if provider_blocked else "已查找替代候選仍無合適門診，詢問是否調整條件，不要求選擇不存在的醫師。") + result.decision_trace)[-50:]}
        return {"recommendation": result.model_dump(mode="json"), "recommendation_query": query,
                "phase": "selecting_doctor", "trace": (step(state, "recommend", "已依目前就醫條件查詢時段，只推薦院方患者資料頁可確認的醫師。") + result.decision_trace)[-50:]}
    except HTTPException:
        raise
    except Exception:
        response = dict(state["intake_response"])
        response.update(ready=False, reply="推薦服務暫時無法完成，條件已保留，請傳送「維持目前條件」重試。")
        return {"recommendation": None, "intake_response": response, "phase": "clarifying",
                "trace": step(state, "recommend", "推薦服務失敗，保留條件並等待使用者重試。")}


def wait_for_selection(state):
    command = interrupt({"phase": "selecting_doctor", "message": "請選擇醫師安排時段，或繼續修改對話條件。"})
    return {"command": command, "message": command.get("message", ""), "operation_id": command["operation_id"]}


def prepare(state):
    command = state["command"]
    recommended_ids = {doctor["doctor_id"] for doctor in (state.get("recommendation") or {}).get("recommended_doctors", [])}
    if command["doctor_id"] not in recommended_ids:
        raise ValueError("醫師不在此個案的推薦名單")
    doctor = next(row for row in load_doctors() if row["doctor_id"] == command["doctor_id"])
    preferences = AppointmentPreparationRequest.model_validate(command["preferences"])
    intake = {**state["intake"], **preferences.model_dump(mode="json"), "date_range_known": True}
    result = prepare_appointment(doctor, preferences)
    return {"preparation": result.model_dump(mode="json"), "intake": intake, "booking_status": None,
            "phase": "awaiting_patient" if result.selected_slot else "selecting_doctor",
            "trace": step(state, "prepare", result.message)}


def wait_for_patient(state):
    message = "時段已選定，等待至院方完成患者資料及身分驗證；本站未完成掛號。" if (state.get("preparation") or {}).get("booking_mode") == "official_handoff" else "時段已選定，等待患者在獨立掛號表單輸入資料與驗證碼。"
    command = interrupt({"phase": "awaiting_patient", "message": message})
    return {"command": command, "message": command.get("message", ""), "operation_id": command["operation_id"]}


def record_outcome(state):
    status = state["command"]["booking_status"]
    phase = "completed" if status == "confirmed" else "needs_verification" if status == "unknown" else "human_required"
    return {"phase": phase, "booking_status": status, "booking_receipt_number": state["command"].get("receipt_number"),
            "trace": step(state, "booking_outcome", "院方已確認掛號成功。" if phase == "completed" else "停止自動操作，等待使用者確認院方狀態。")}


def command_route(state):
    return "record_outcome" if state["command"].get("action") == "booking_outcome" else "prepare" if state["command"].get("action") == "prepare" else "understand"


def build_care_graph(checkpointer):
    graph = StateGraph(CareGraphState)
    for name, node in (
        ("understand", understand), ("wait_for_details", wait_for_details), ("recommend", recommend),
        ("wait_for_selection", wait_for_selection), ("prepare", prepare),
        ("wait_for_patient", wait_for_patient), ("record_outcome", record_outcome),
    ):
        graph.add_node(name, node)
    graph.add_edge(START, "understand")
    graph.add_conditional_edges("understand", lambda state: "recommend" if state["intake_response"]["ready"] else "wait_for_details", ["recommend", "wait_for_details"])
    graph.add_edge("wait_for_details", "understand")
    graph.add_conditional_edges("recommend", lambda state: "wait_for_selection" if state.get("recommendation") is not None and state["phase"] == "selecting_doctor" else "wait_for_details", ["wait_for_selection", "wait_for_details"])
    graph.add_conditional_edges("wait_for_selection", command_route, ["prepare", "understand"])
    graph.add_conditional_edges("prepare", lambda state: "wait_for_patient" if state["phase"] == "awaiting_patient" else "wait_for_selection", ["wait_for_patient", "wait_for_selection"])
    graph.add_conditional_edges("wait_for_patient", command_route, ["record_outcome", "prepare", "understand"])
    graph.add_edge("record_outcome", END)
    return graph.compile(checkpointer=checkpointer)
