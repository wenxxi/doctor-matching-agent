from typing import TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt

from app.intake_schemas import IntakeRequest, IntakeState
from app.schemas import AppointmentPreparationRequest, RecommendationRequest
from app.routers.recommendations import recommend_doctors
from app.services.appointment_agent import prepare_appointment
from app.services.intake import intake_turn
from app.services.processed_data import load_doctors


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
    if state.get("recommendation_query") == query and state.get("recommendation") is not None:
        return {"phase": "selecting_doctor", "trace": step(state, "recommend", "症狀未改變，沿用此個案已取得的推薦醫師。")}
    try:
        result = recommend_doctors(RecommendationRequest(query=query))
        return {"recommendation": result.model_dump(mode="json"), "recommendation_query": query,
                "phase": "selecting_doctor", "trace": step(state, "recommend", "已呼叫既有醫師推薦服務。")}
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
    command = interrupt({"phase": "awaiting_patient", "message": "時段已選定，等待患者在獨立掛號表單輸入資料與驗證碼。"})
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
    graph.add_conditional_edges("recommend", lambda state: "wait_for_selection" if state.get("recommendation") is not None else "wait_for_details", ["wait_for_selection", "wait_for_details"])
    graph.add_conditional_edges("wait_for_selection", command_route, ["prepare", "understand"])
    graph.add_conditional_edges("prepare", lambda state: "wait_for_patient" if state["phase"] == "awaiting_patient" else "wait_for_selection", ["wait_for_patient", "wait_for_selection"])
    graph.add_conditional_edges("wait_for_patient", command_route, ["record_outcome", "prepare", "understand"])
    graph.add_edge("record_outcome", END)
    return graph.compile(checkpointer=checkpointer)
