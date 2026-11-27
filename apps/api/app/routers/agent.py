from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Response, Query
from sqlalchemy import select

from app.agent_models import CareCase
from app.agent_schemas import AgentPrepareRequest, AgentSessionResponse, AgentTurnRequest, CaseCreateRequest, CaseDetailResponse, CaseSummary, CaseMessagesPage
from app.services import cases
from app.services.agent_storage import AGENT_STORAGE_ERRORS, get_agent_engine, get_agent_session, initialize_agent_storage


def storage_session():
    try:
        yield from get_agent_session()
    except AGENT_STORAGE_ERRORS:
        raise HTTPException(status_code=503, detail="個案記憶尚未連線或暫時無法存取，請稍後重試。") from None


def private_response(response: Response):
    response.headers["Cache-Control"] = "no-store, private"


router = APIRouter(prefix="/api/agent", tags=["agent"], dependencies=[Depends(private_response)])


def owner_dependency(session=Depends(storage_session), x_agent_token: str = Header(min_length=30, max_length=100)):
    return cases.authenticate_owner(session, x_agent_token)


@router.get("/status")
def agent_status():
    try:
        initialize_agent_storage()
        return {"available": True, "storage": get_agent_engine().dialect.name}
    except AGENT_STORAGE_ERRORS:
        return {"available": False, "message": "個案記憶尚未連接資料庫；你仍可使用目前頁面的對話。"}


@router.post("/session", response_model=AgentSessionResponse)
def create_session(session=Depends(storage_session)):
    return AgentSessionResponse(token=cases.create_owner(session))


@router.get("/cases", response_model=list[CaseSummary])
def list_cases(owner=Depends(owner_dependency), session=Depends(storage_session)):
    return session.scalars(select(CareCase).where(CareCase.owner_id == owner.id).order_by(CareCase.updated_at.desc())).all()


@router.post("/cases", response_model=CaseDetailResponse)
def create_case(request: CaseCreateRequest, owner=Depends(owner_dependency), session=Depends(storage_session)):
    if not request.consent:
        raise HTTPException(status_code=422, detail="請先同意將本個案的健康描述與對話存入資料庫。")
    return cases.create_case(session, owner, request.title, request.subject_label)


@router.get("/cases/{case_id}", response_model=CaseDetailResponse)
def get_case(case_id: UUID, owner=Depends(owner_dependency), session=Depends(storage_session)):
    return cases.case_detail(session, cases.owned_case(session, owner, case_id))


@router.post("/cases/{case_id}/messages", response_model=CaseDetailResponse)
def send_message(case_id: UUID, request: AgentTurnRequest, owner=Depends(owner_dependency), session=Depends(storage_session)):
    return cases.run_case(session, owner, case_id, request)


@router.get("/cases/{case_id}/messages", response_model=CaseMessagesPage)
def older_messages(case_id: UUID, before: UUID | None = None, limit: int = Query(default=50, ge=1, le=50), owner=Depends(owner_dependency), session=Depends(storage_session)):
    return cases.message_page(session, cases.owned_case(session, owner, case_id), before, limit)


@router.post("/cases/{case_id}/prepare", response_model=CaseDetailResponse)
def prepare(case_id: UUID, request: AgentPrepareRequest, owner=Depends(owner_dependency), session=Depends(storage_session)):
    return cases.run_case(session, owner, case_id, request, "prepare")


@router.post("/cases/{case_id}/resolve", response_model=CaseDetailResponse)
def resolve(case_id: UUID, owner=Depends(owner_dependency), session=Depends(storage_session)):
    with cases.case_lock(case_id):
        case = cases.owned_case(session, owner, case_id, lock=True)
        if cases.current_task(session, case).snapshot.get("booking_status") == "submitting":
            raise HTTPException(status_code=409, detail="院方正在處理掛號，請先等候結果，結案不會取消掛號。")
        case.status = "resolved"
        cases.current_task(session, case).status = "closed"
        session.commit()
        return cases.case_detail(session, case)


@router.post("/cases/{case_id}/reopen", response_model=CaseDetailResponse)
def reopen(case_id: UUID, owner=Depends(owner_dependency), session=Depends(storage_session)):
    with cases.case_lock(case_id):
        case = cases.owned_case(session, owner, case_id, lock=True)
        case.status = "active"
        session.commit()
        return cases.case_detail(session, case)


@router.delete("/cases/{case_id}", status_code=204)
def delete_case(case_id: UUID, owner=Depends(owner_dependency), session=Depends(storage_session)):
    cases.delete_case(session, owner, case_id)
