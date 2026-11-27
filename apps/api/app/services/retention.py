"""Bounded cleanup while the API runs, with a 30-day grace period for existing cases."""
import asyncio
from datetime import datetime, timedelta, timezone
from time import time

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.agent_models import AgentOwner, CareCase
from app.services.agent_storage import initialize_agent_storage, AGENT_STORAGE_ERRORS
from app.services.security import SecurityCounter, insert_for, security_engine, lease, release, SecurityDenied, storage_lock


RETENTION_DAYS = 30


def sweep(now=None):
    now = now or datetime.now(timezone.utc)
    initialize_agent_storage()
    engine = security_engine()
    with Session(engine) as session, session.begin():
        session.execute(insert_for(session, SecurityCounter).values(key="retention-enabled-at", amount=int(time()), expires=2**62).on_conflict_do_nothing())
        activated = session.get(SecurityCounter, "retention-enabled-at").amount
        key, holder = lease(session, "maintenance", 1, 3600)
    try:
        cutoff = now - timedelta(days=RETENTION_DAYS)
        removed = 0
        if now.timestamp() >= activated + RETENTION_DAYS * 86400:
            from app.services.cases import delete_case
            from fastapi import HTTPException
            with Session(engine) as session:
                expired = session.scalars(select(CareCase).where(CareCase.updated_at < cutoff).order_by(CareCase.updated_at).limit(20)).all()
                for case in expired:
                    owner = session.get(AgentOwner, case.owner_id)
                    try:
                        removed += bool(delete_case(session, owner, case.id, older_than=cutoff))
                    except HTTPException:
                        session.rollback()  # Never erase an in-flight registration.
                storage_lock(session)  # Serialize orphan cleanup with concurrent case creation.
                session.execute(delete(AgentOwner).where(AgentOwner.created_at < cutoff,
                    ~select(CareCase.id).where(CareCase.owner_id == AgentOwner.id).exists()))
                session.commit()
        with Session(engine) as session, session.begin():
            old_keys = select(SecurityCounter.key).where(SecurityCounter.expires < int(now.timestamp())).limit(5000)
            session.execute(delete(SecurityCounter).where(SecurityCounter.key.in_(old_keys)))
        return removed
    finally:
        release(key, holder)


async def maintenance_loop():
    while True:
        try:
            await asyncio.to_thread(sweep)
        except (SecurityDenied, *AGENT_STORAGE_ERRORS):
            pass  # Memory can be unavailable; paid model paths independently fail closed.
        await asyncio.sleep(60)
