"""Security acceptance: no paid calls, real patient data or hospital submissions."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
import secrets
from threading import Event
from types import SimpleNamespace
import uuid

from fastapi import HTTPException
from fastapi.testclient import TestClient
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.main import app
from app.security_middleware import SecurityMiddleware
from app.agent_models import AgentOwner, AgentTask, CareCase, CaseMessage
from app.services import security, booking, cases, retention, doctor_relevance
from app.services.agent_storage import initialize_agent_storage, get_agent_engine, checkpoint_store
from app.services.privacy import ensure_safe_text
from app.settings import get_openai_settings
from test_cases import database, client, owner, ready_case, prepare_case


@pytest.fixture(autouse=True)
def no_models(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    get_openai_settings.cache_clear()
    booking.SESSIONS.clear()
    yield
    booking.SESSIONS.clear()
    get_openai_settings.cache_clear()


class FakeModel:
    def __init__(self, usage=None, error=None):
        self.calls, self.options, self.usage, self.error = [], [], usage, error
        self.responses = self
    def with_options(self, **options):
        self.options.append(options)
        return self
    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return SimpleNamespace(usage=self.usage, output_text="{}")


def model_args():
    return dict(model="gpt-4o-mini", input=json.dumps({"query":"膝蓋痛"}), instructions="Extract concepts", max_output_tokens=100)


def spend():
    with Session(security.security_engine()) as session:
        return session.scalar(select(security.SecurityCounter.amount).where(security.SecurityCounter.key.startswith("llm-spend:")))


def test_http_limits_cannot_be_reset_with_forwarded_ip_or_owner_headers(monkeypatch):
    monkeypatch.setenv("EXPENSIVE_REQUESTS_PER_MINUTE", "3")
    from app.routers import concepts
    calls=[]
    monkeypatch.setattr(concepts,"get_concept_extractor",lambda:SimpleNamespace(extract_with_metadata=lambda q: calls.append(q) or SimpleNamespace(
        concepts=[],extractor="test",fallback_used=False,candidate_concepts_count=0,input_tokens=0,output_tokens=0)))
    client=TestClient(app)
    responses=[client.post('/api/concepts/extract',json={"query":"膝蓋痛"},headers={"X-Forwarded-For":f"192.0.2.{i}","X-Agent-Token":secrets.token_hex(20)}) for i in range(6)]
    assert [r.status_code for r in responses]==[200,200,200,429,429,429]
    assert len(calls)==3 and responses[-1].headers['retry-after']


def test_anonymous_token_minting_has_independent_quota(monkeypatch):
    monkeypatch.setenv('SESSION_CREATES_PER_HOUR','2')
    client=TestClient(app)
    assert [client.post('/api/agent/session').status_code for _ in range(3)]==[200,200,429]
    with Session(get_agent_engine()) as session:
        assert session.scalar(select(func.count()).select_from(AgentOwner))==2


def test_oversize_query_and_body_rejected_without_model(monkeypatch):
    from app.routers import concepts
    monkeypatch.setattr(concepts,'get_concept_extractor',lambda:pytest.fail('must not enter service'))
    client=TestClient(app)
    assert client.post('/api/concepts/extract',json={"query":"痛"*2001}).status_code==422
    assert client.post('/api/concepts/extract',json={"query":" "}).status_code==422
    assert client.post('/api/concepts/extract',json={"query":"痛"*100000}).status_code==413
    marker='PRIVATE_SYNTHETIC_MARKER'
    invalid=client.post('/api/concepts/extract',json={"query":{"value":marker}})
    assert invalid.status_code==422 and marker not in invalid.text
    assert invalid.headers['cache-control']=='no-store, private'


def test_chunked_body_cannot_bypass_size_limit():
    entered=[]
    async def endpoint(*args): entered.append(True)
    middleware=SecurityMiddleware(endpoint,max_bytes=8)
    chunks=iter([{'type':'http.request','body':b'12345','more_body':True}, {'type':'http.request','body':b'67890','more_body':False}])
    output=[]
    async def receive(): return next(chunks)
    async def send(value): output.append(value)
    asyncio.run(middleware({'type':'http','path':'/api/concepts/extract','method':'POST','headers':[(b'content-length',b'0')]},receive,send))
    assert output[0]['status']==413 and not entered


def test_slow_request_has_total_receive_deadline():
    async def endpoint(*args): pytest.fail('must not enter service')
    async def receive(): await asyncio.sleep(1)
    output=[]
    async def send(value): output.append(value)
    asyncio.run(SecurityMiddleware(endpoint,timeout=.01)({'type':'http','path':'/api/intake/chat','method':'POST'},receive,send))
    assert output[0]['status']==408


def test_common_model_gate_disables_storage_and_refunds_known_usage():
    model=FakeModel(usage=SimpleNamespace(input_tokens=10,output_tokens=5))
    security.create_response(model,**model_args())
    assert model.calls[0]['store'] is False
    assert model.options==[{'timeout':25,'max_retries':0}]
    assert spend()==security.cost(10,5,security.priced_model('gpt-4o-mini'))


def test_unknown_timeout_retains_reservation_and_is_not_retried():
    model=FakeModel(error=TimeoutError('synthetic'))
    with pytest.raises(TimeoutError): security.create_response(model,**model_args())
    assert len(model.calls)==1 and spend()>0
    with Session(security.security_engine()) as session:
        assert all(row.expires==0 for row in session.scalars(select(security.SecurityLease)))


def test_parallel_calls_cannot_overspend_and_budget_survives_new_client(monkeypatch):
    monkeypatch.setenv('LLM_DAILY_BUDGET_USD','0.00030')
    entered,finish=Event(),Event()
    model=FakeModel()
    original=model.create
    def create(**kwargs): entered.set(); finish.wait(3); return original(**kwargs)
    model.create=create
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(security.create_response,model,**model_args())
        assert entered.wait(3)
        try:
            with pytest.raises(security.SecurityDenied): security.create_response(FakeModel(),**model_args())
        finally: finish.set()
        first.result()
    assert 0<spend()<=300 and len(model.calls)==1
    with pytest.raises(security.SecurityDenied): security.create_response(FakeModel(),**model_args())


def test_model_request_budget_includes_all_steps_and_fallback_cannot_swallow_denial(monkeypatch):
    context=security.REQUEST_BUDGET.set(security.RequestBudget())
    try:
        for _ in range(4): security.create_response(FakeModel(),**model_args())
        with pytest.raises(security.SecurityDenied): security.create_response(FakeModel(),**model_args())
    finally: security.REQUEST_BUDGET.reset(context)
    from app.services.concept_extractor import FallbackConceptExtractor, KeywordConceptExtractor
    class Denied:
        def extract_with_metadata(self,q): raise security.SecurityDenied()
    with pytest.raises(security.SecurityDenied): FallbackConceptExtractor(Denied(),KeywordConceptExtractor()).extract_with_metadata('膝蓋痛')


@pytest.mark.parametrize('text', ['生日為1990-01-01','出生日期：1990年1月1日','DOB: 1990/01/01',
    'passport number TEST000000','證號 TEST000000','膝蓋痛A123456789','身分證Ａ１２３４５６７８９','birthday is 19900101'])
def test_sensitive_variants_rejected(text):
    with pytest.raises(HTTPException): ensure_safe_text(text)


def test_medical_words_and_appointment_dates_are_not_identity_data():
    for text in ('Thyroid nodule','膝蓋痛，想在2026-12-01看診','生日快樂','birth injury'):
        ensure_safe_text(text)


def test_sensitive_text_rejected_by_direct_routes_and_not_persisted():
    client=TestClient(app)
    for route in ('/api/concepts/extract','/api/recommendations'):
        assert client.post(route,json={'query':'證號 TEST000000 膝蓋痛'}).status_code==422
    headers={'X-Agent-Token':client.post('/api/agent/session').json()['token']}
    case=client.post('/api/agent/cases',headers=headers,json={'consent':True}).json()
    response=client.post('/api/agent/cases/'+case['case']['id']+'/messages',headers=headers,json={
        'message':'生日為1990-01-01','operation_id':str(uuid.uuid4()),'expected_version':0})
    assert response.status_code==422
    with Session(get_agent_engine()) as session:
        assert session.scalar(select(func.count()).select_from(CaseMessage))==0


def test_unpriced_model_and_unavailable_ledger_fail_before_paid_call(monkeypatch):
    model=FakeModel(); args=model_args(); args['model']='unknown-model'
    with pytest.raises(security.SecurityDenied): security.create_response(model,**args)
    from app.services.agent_storage import AgentStorageError
    monkeypatch.setattr(security,'security_engine',lambda: (_ for _ in ()).throw(AgentStorageError()))
    with pytest.raises(security.SecurityDenied): security.create_response(model,**model_args())
    assert model.calls==[]


def test_message_pagination_is_bounded_and_cursors_are_owner_scoped():
    client=TestClient(app)
    headers={'X-Agent-Token':client.post('/api/agent/session').json()['token']}
    case=client.post('/api/agent/cases',headers=headers,json={'consent':True}).json()
    with Session(get_agent_engine()) as session:
        session.add_all([CaseMessage(case_id=uuid.UUID(case['case']['id']),task_id=uuid.UUID(case['task']['id']),
            operation_id=uuid.uuid4(),role='user',content=str(i),created_at=datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=i)) for i in range(125)])
        session.commit()
    detail=client.get('/api/agent/cases/'+case['case']['id'],headers=headers).json()
    assert len(detail['messages'])==50 and detail['messages_cursor']
    ids={message['id'] for message in detail['messages']}
    for expected in (50,25):
        page=client.get('/api/agent/cases/'+case['case']['id']+'/messages',params={'before':detail['messages_cursor']},headers=headers).json()
        assert len(page['messages'])==expected and not (ids & {row['id'] for row in page['messages']})
        ids.update(row['id'] for row in page['messages']);detail['messages_cursor']=page['next_cursor']
    assert len(ids)==125 and detail['messages_cursor'] is None
    other={'X-Agent-Token':client.post('/api/agent/session').json()['token']}
    assert client.get('/api/agent/cases/'+case['case']['id']+'/messages',headers=other).status_code==404


def test_lexical_index_reused_without_caching_patient_queries():
    from app.services.concept_extractor import KeywordConceptExtractor
    from app.services.department_intent import detect_department_intent
    doctor_relevance.lexical_index.cache_clear()
    concepts=KeywordConceptExtractor().extract_concepts('膝蓋痛')
    intent=detect_department_intent('膝蓋痛',concepts)
    doctor_relevance.retrieve_candidates('膝蓋痛',concepts,intent)
    doctor_relevance.retrieve_candidates('跑步膝蓋痛',concepts,intent,expanded=True)
    assert doctor_relevance.lexical_index.cache_info().hits==1


def test_retention_grace_and_checkpoint_erasure():
    engine=initialize_agent_storage();security.security_engine()
    now=datetime.now(timezone.utc)
    with Session(engine) as session:
        token=cases.create_owner(session);owner=cases.authenticate_owner(session,token)
        detail=cases.create_case(session,owner,'review','自己');case_id=detail.case.id;task_id=detail.task.id
        case=session.get(CareCase,case_id);case.updated_at=now-timedelta(days=90);session.commit()
    assert retention.sweep(now)==0
    with Session(engine) as session:
        activation=session.get(security.SecurityCounter,'retention-enabled-at');activation.amount=int((now-timedelta(days=31)).timestamp());session.commit()
    assert retention.sweep(now)==1
    with Session(engine) as session:
        assert session.get(CareCase,case_id) is None and session.get(AgentTask,task_id) is None
    with checkpoint_store() as saver:
        assert saver.get_tuple({'configurable':{'thread_id':str(task_id)}}) is None


def test_task_claim_rejects_second_form_and_stale_form_before_hospital_call(client, database, monkeypatch):
    from app.schemas import AppointmentSlotResponse
    from test_booking import PATIENT
    headers=owner(client)
    detail=prepare_case(client,headers,ready_case(client,headers),monkeypatch)
    slot=AppointmentSlotResponse.model_validate(detail['task']['preparation']['selected_slot'])
    calls=[]
    def start(doctor,url):
        token=secrets.token_urlsafe(32)
        booking.SESSIONS[token]=booking.BookingSession(None,doctor['doctor_name_zh'],slot,
            datetime.now(timezone.utc)+timedelta(minutes=10),booking.HospitalForm(''))
        return BookingStateResponse(status='awaiting_patient',message='test',token=token)
    def submit(token,patient):
        calls.append(token)
        current=booking.get_session(token);current.status='awaiting_confirmation'
        current.response=BookingStateResponse(status='awaiting_confirmation',message='test')
        return current.response
    from app.booking_schemas import BookingStateResponse
    monkeypatch.setattr(booking,'start_booking',start)
    monkeypatch.setattr(booking,'submit_patient',submit)
    body={'doctor_id':detail['task']['preparation']['doctor_id'],'registration_url':slot.registration_url,'task_id':detail['task']['id']}
    first=client.post('/api/booking/sessions',headers=headers,json=body)
    assert first.status_code==200
    token=first.json()['token']
    assert client.post('/api/booking/sessions',headers=headers,json=body).status_code==409
    current=booking.get_session(token)
    stale=secrets.token_urlsafe(32)
    booking.SESSIONS[stale]=booking.BookingSession(None,current.doctor_name,slot,current.expires_at,booking.HospitalForm(''),task_id=current.task_id,task_version=current.task_version)
    assert client.post('/api/booking/submit',headers={'X-Booking-Token':stale},json=PATIENT).status_code==409
    assert calls==[]
    assert client.post('/api/booking/submit',headers={'X-Booking-Token':token},json=PATIENT).json()['status']=='awaiting_confirmation'
    assert client.post('/api/booking/submit',headers={'X-Booking-Token':stale},json=PATIENT).status_code==409
    assert len(calls)==1


def test_booking_start_capacity_reserves_inflight_work(monkeypatch):
    from app.schemas import AppointmentSlotResponse
    expiry=datetime.now(timezone.utc)+timedelta(minutes=10)
    booking.SESSIONS.update({str(i):SimpleNamespace(expires_at=expiry) for i in range(99)})
    entered,finish=Event(),Event()
    def slow_start(*args): entered.set();finish.wait(3);return 'started'
    monkeypatch.setattr(booking,'_start_booking',slow_start)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first=pool.submit(booking.start_booking,{},'')
        assert entered.wait(3)
        try:
            with pytest.raises(booking.BookingError): booking.start_booking({},'')
        finally: finish.set()
        assert first.result()=='started'
    assert booking.STARTING_SESSIONS==0


def test_nested_workers_share_request_tool_budget():
    from app.services.parallel import context_submit
    context=security.RequestBudget();context.hospital_calls=79
    reset=security.REQUEST_BUDGET.set(context)
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            def call():
                with security.provider_request('synthetic'): pass
            context_submit(pool,call).result()
            with pytest.raises(security.SecurityDenied): context_submit(pool,call).result()
        assert context.hospital_calls==81
    finally: security.REQUEST_BUDGET.reset(reset)


def test_budget_denial_does_not_replay_old_message_on_retry(client, monkeypatch):
    from app.services import care_graph
    headers=owner(client)
    case=client.post('/api/agent/cases',headers=headers,json={'consent':True}).json()
    original=care_graph.intake_turn
    def deny(request): raise security.SecurityDenied()
    monkeypatch.setattr(care_graph,'intake_turn',deny)
    url='/api/agent/cases/'+case['case']['id']+'/messages'
    assert client.post(url,headers=headers,json={'message':'舊的訊息','operation_id':str(uuid.uuid4()),'expected_version':0}).status_code==429
    monkeypatch.setattr(care_graph,'intake_turn',original)
    response=client.post(url,headers=headers,json={'message':'新的訊息','operation_id':str(uuid.uuid4()),'expected_version':0})
    assert response.status_code==200
    detail=response.json()
    assert detail['messages'][0]['content']=='新的訊息'
    monkeypatch.setattr(care_graph,'intake_turn',deny)
    assert client.post(url,headers=headers,json={'message':'第二次被拒','operation_id':str(uuid.uuid4()),'expected_version':1}).status_code==429
    monkeypatch.setattr(care_graph,'intake_turn',original)
    response=client.post(url,headers=headers,json={'message':'之後的新訊息','operation_id':str(uuid.uuid4()),'expected_version':1})
    assert response.status_code==200 and response.json()['messages'][-2]['content']=='之後的新訊息'
