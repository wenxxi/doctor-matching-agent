"""Opt-in integration tests restricted to the disposable local security_test DB."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import os
from types import SimpleNamespace
import uuid

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.agent_models import AgentOwner, CareCase, AgentTask
from app.services import security, cases, agent_storage, retention
from app.services.care_graph import build_care_graph
from app.agent_schemas import AgentTurnRequest
from app.settings import get_openai_settings


@pytest.fixture
def pg(monkeypatch):
    raw=os.getenv('SECURITY_TEST_POSTGRES_URL')
    if not raw: pytest.skip('requires disposable PostgreSQL on localhost:55432')
    url=make_url(raw)
    assert url.host in {'localhost','127.0.0.1'} and url.port==55432 and url.database=='security_test'
    schema='test_'+uuid.uuid4().hex
    admin=create_engine(raw)
    with admin.begin() as conn: conn.execute(text('CREATE SCHEMA '+schema))
    monkeypatch.setenv('AGENT_DATABASE_URL',url.update_query_dict({'options':'-csearch_path='+schema}).render_as_string(hide_password=False))
    monkeypatch.delenv('OPENAI_API_KEY',raising=False)
    get_openai_settings.cache_clear()
    agent_storage.get_agent_engine.cache_clear();agent_storage.initialize_agent_storage.cache_clear()
    engine=agent_storage.initialize_agent_storage();security.security_engine()
    yield engine
    engine.dispose();agent_storage.get_agent_engine.cache_clear();agent_storage.initialize_agent_storage.cache_clear()
    with admin.begin() as conn: conn.execute(text('DROP SCHEMA '+schema+' CASCADE'))
    admin.dispose();get_openai_settings.cache_clear()


def test_pg_atomic_daily_budget_across_connections(pg,monkeypatch):
    monkeypatch.setenv('LLM_DAILY_BUDGET_USD','0.001')
    monkeypatch.setenv('LLM_CONCURRENCY','8')
    class Fake:
        responses=None
        def __init__(self):self.responses=self
        def with_options(self,**kw):return self
        def create(self,**kw):return SimpleNamespace(usage=None)
    def invoke(_):
        try:
            security.create_response(Fake(),model='gpt-4o-mini',input='{"query":"膝蓋痛"}',instructions='extract',max_output_tokens=100)
            return True
        except security.SecurityDenied:return False
    with ThreadPoolExecutor(max_workers=8) as pool: accepted=list(pool.map(invoke,range(8)))
    with Session(pg) as session:
        spent=session.scalar(select(security.SecurityCounter.amount).where(security.SecurityCounter.key.startswith('llm-spend:')))
    assert 0<sum(accepted)<8 and 0<spent<=1000


def test_pg_submission_claim_works_without_process_lock(pg,monkeypatch):
    with Session(pg) as session:
        token=cases.create_owner(session);owner=cases.authenticate_owner(session,token)
        case=cases.create_case(session,owner,'test','自己')
        task=session.get(AgentTask,case.task.id);task.status='awaiting_patient';session.commit();task_id=task.id
    assert cases.observe_booking(task_id,0,'awaiting_patient',booking_token='synthetic-session')
    monkeypatch.setattr(cases,'case_lock',lambda _:nullcontext())
    def submit(_):return cases.observe_booking(task_id,0,'submitting',booking_token='synthetic-session',expected_booking_status='awaiting_patient')
    with ThreadPoolExecutor(max_workers=6) as pool: outcomes=list(pool.map(submit,range(6)))
    assert sum(outcomes)==1
    assert not cases.observe_booking(task_id,0,'awaiting_patient',booking_token='another-session')


def test_pg_retention_deletes_real_graph_checkpoints(pg):
    with Session(pg) as session:
        token=cases.create_owner(session);owner=cases.authenticate_owner(session,token)
        detail=cases.create_case(session,owner,'test','自己')
        detail=cases.run_case(session,owner,detail.case.id,AgentTurnRequest(message='你好',operation_id=uuid.uuid4(),expected_version=0))
        case=session.get(CareCase,detail.case.id);case.updated_at=datetime.now(timezone.utc)-timedelta(days=40);session.commit()
    with agent_storage.checkpoint_store() as saver:
        assert saver.get_tuple({'configurable':{'thread_id':str(detail.task.id)}}) is not None
    retention.sweep()
    with Session(pg) as session:
        row=session.get(security.SecurityCounter,'retention-enabled-at');row.amount-=31*86400;session.commit()
    assert retention.sweep()==1
    with agent_storage.checkpoint_store() as saver:
        assert saver.get_tuple({'configurable':{'thread_id':str(detail.task.id)}}) is None
