"""Shared, durable admission controls. Never stores prompts, tokens or raw IPs."""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_CEILING
import hashlib
import json
import os
import secrets
from threading import Lock
from time import time
from weakref import WeakSet

from fastapi import HTTPException
from sqlalchemy import BigInteger, String, select, update
from sqlalchemy.orm import Mapped, mapped_column, Session
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import Base
from app.services.agent_storage import get_agent_engine, AGENT_STORAGE_ERRORS


class SecurityDenied(HTTPException):
    def __init__(self, detail="請求較頻繁或已達今日使用額度，請稍後再試。", code=429, retry=60):
        super().__init__(code, detail, headers={"Retry-After": str(retry), "Cache-Control": "no-store, private"})


class SecurityCounter(Base):
    __tablename__ = "security_counters"
    key: Mapped[str] = mapped_column(String(180), primary_key=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    expires: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)


class SecurityLease(Base):
    __tablename__ = "security_leases"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    holder: Mapped[str] = mapped_column(String(64), nullable=False)
    expires: Mapped[int] = mapped_column(BigInteger, nullable=False)


READY = WeakSet()
SETUP_LOCK = Lock()


def setting(name, default):
    return max(1, int(os.getenv(name, default)))


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass
class RequestBudget:
    ip: str = "internal"
    owner: str | None = None
    model_calls: int = 0
    hospital_calls: int = 0
    lock: Lock = field(default_factory=Lock)


REQUEST_BUDGET = ContextVar("request_budget", default=None)


def security_engine():
    engine = get_agent_engine()
    with SETUP_LOCK:
        if engine not in READY:
            SecurityCounter.__table__.create(engine, checkfirst=True)
            SecurityLease.__table__.create(engine, checkfirst=True)
            READY.add(engine)
    return engine


def insert_for(session, model):
    return (pg_insert if session.bind.dialect.name == "postgresql" else sqlite_insert)(model)


def consume(session, key, amount, limit, expires):
    if amount > limit:
        raise SecurityDenied()
    statement = insert_for(session, SecurityCounter).values(key=key, amount=amount, expires=expires)
    statement = statement.on_conflict_do_update(
        index_elements=[SecurityCounter.key], set_={"amount": SecurityCounter.amount + amount},
        where=SecurityCounter.amount + amount <= limit,
    ).returning(SecurityCounter.amount)
    if session.execute(statement).scalar_one_or_none() is None:
        raise SecurityDenied()


def rate(session, prefix, limit, seconds=60, amount=1):
    window = int(time()) // seconds
    key = f"{prefix}:{window}"
    consume(session, key, amount, limit, (window + 2) * seconds)
    return key


def admit_request(path, method):
    if path == "/api/agent/status":
        return  # Cheap availability check must work even when persistence is unavailable.
    context = REQUEST_BUDGET.get() or RequestBudget()
    try:
        with Session(security_engine()) as session, session.begin():
            rate(session, "http-global", setting("API_GLOBAL_REQUESTS_PER_MINUTE", 300))
            rate(session, "http:" + context.ip, setting("API_REQUESTS_PER_MINUTE", 90))
            if path == "/api/agent/session" and method == "POST":
                rate(session, "mint:" + context.ip, setting("SESSION_CREATES_PER_HOUR", 5), 3600)
                rate(session, "mint-global", setting("SESSION_CREATES_PER_DAY", 200), 86400)
            expensive = (path.startswith(("/api/concepts", "/api/recommendations", "/api/intake"))
                         or path.endswith(("/prepare", "/messages", "/sessions", "/captcha", "/search"))
                         or "/appointments" in path or "/integrations/" in path)
            if expensive:
                rate(session, "expensive:" + context.ip, setting("EXPENSIVE_REQUESTS_PER_MINUTE", 15))
    except AGENT_STORAGE_ERRORS:
        raise SecurityDenied("使用量保護服務暫時無法確認，請稍後重試。", 503) from None


def lease(session, resource, slots, ttl):
    now = int(time())
    for index in range(slots):
        key, holder = f"{resource}:{index}", secrets.token_hex(16)
        statement = insert_for(session, SecurityLease).values(key=key, holder=holder, expires=now + ttl)
        statement = statement.on_conflict_do_update(index_elements=[SecurityLease.key],
            set_={"holder": holder, "expires": now + ttl}, where=SecurityLease.expires <= now).returning(SecurityLease.key)
        if session.execute(statement).scalar_one_or_none() is not None:
            return key, holder
    raise SecurityDenied("服務正在處理其他請求，請稍後重試。", retry=5)


def release(key, holder):
    try:
        with Session(security_engine()) as session, session.begin():
            session.execute(update(SecurityLease).where(SecurityLease.key == key, SecurityLease.holder == holder).values(expires=0))
    except AGENT_STORAGE_ERRORS:
        pass  # Lease expires; never grant extra capacity when the store is unavailable.


def priced_model(model):
    if model in {"gpt-4o-mini", "gpt-4o-mini-2024-07-18"}:
        return Decimal("0.15"), Decimal("0.60")
    if os.getenv("LLM_PRICED_MODEL") == model:
        try:
            prices = Decimal(os.environ["LLM_INPUT_USD_PER_MILLION"]), Decimal(os.environ["LLM_OUTPUT_USD_PER_MILLION"])
            if all(value.is_finite() and value > 0 for value in prices):
                return prices
        except (KeyError, ValueError, ArithmeticError):
            pass
    raise SecurityDenied("模型費率尚未設定，已暫停付費呼叫。", 503)


def cost(input_tokens, output_tokens, prices):
    # USD per million tokens equals micro-USD per token; round up, ignore cache discounts.
    return int((input_tokens * prices[0] + output_tokens * prices[1]).to_integral_value(rounding=ROUND_CEILING))


def create_response(client, **kwargs):
    """All paid model paths, including direct graph calls, must pass this gate."""
    from app.services.privacy import ensure_safe_text, ensure_safe_payload
    ensure_safe_payload(json.loads(kwargs["input"]))
    kwargs.update(store=False)
    if set(kwargs) - {"model", "instructions", "input", "text", "temperature", "max_output_tokens", "store"}:
        raise SecurityDenied("不支援的模型呼叫設定。", 503)
    output_limit = kwargs.get("max_output_tokens", 0)
    # UTF-8 bytes are a conservative token upper bound, plus protocol overhead.
    input_upper = len(json.dumps(kwargs, ensure_ascii=False).encode()) + 1024
    if input_upper > setting("LLM_MAX_INPUT_TOKENS", 64000) or not 1 <= output_limit <= 2600:
        raise SecurityDenied("模型輸入超過本次處理上限，請縮短描述。", 422)
    context = REQUEST_BUDGET.get() or RequestBudget()
    with context.lock:
        context.model_calls += 1
        if context.model_calls > 4:
            raise SecurityDenied("本輪模型呼叫已達上限。")
    prices = priced_model(kwargs["model"])
    reserved = cost(input_upper, output_limit, prices)
    daily_limit = int(Decimal(os.getenv("LLM_DAILY_BUDGET_USD", "1.00")) * 1_000_000)
    try:
        with Session(security_engine()) as session, session.begin():
            key, holder = lease(session, "llm", setting("LLM_CONCURRENCY", 2), 120)
            rate(session, "llm-ip:" + context.ip, setting("LLM_CALLS_PER_HOUR", 60), 3600)
            if context.owner:
                rate(session, "llm-owner:" + context.owner, setting("LLM_CALLS_PER_HOUR", 60), 3600)
            day_key = rate(session, "llm-spend", daily_limit, 86400, reserved)
    except AGENT_STORAGE_ERRORS:
        raise SecurityDenied("費用預算暫時無法確認，已暫停模型呼叫。", 503) from None
    try:
        response = client.with_options(timeout=25, max_retries=0).responses.create(**kwargs)
        usage = getattr(response, "usage", None)
        get = (lambda name: usage.get(name)) if isinstance(usage, dict) else (lambda name: getattr(usage, name, None))
        incoming, outgoing = get("input_tokens"), get("output_tokens")
        if isinstance(incoming, int) and isinstance(outgoing, int) and incoming >= 0 and outgoing >= 0:
            actual = cost(incoming, outgoing, prices)
            if actual < reserved:
                try:
                    with Session(security_engine()) as session, session.begin():
                        session.execute(update(SecurityCounter).where(SecurityCounter.key == day_key).values(amount=SecurityCounter.amount - (reserved - actual)))
                except AGENT_STORAGE_ERRORS:
                    pass  # Keep the conservative reservation on uncertain accounting.
        return response
    finally:
        release(key, holder)  # Failures retain their full reserved budget; no automatic retry.


@contextmanager
def provider_request(provider):
    context = REQUEST_BUDGET.get()
    if context:
        with context.lock:
            context.hospital_calls += 1
            if context.hospital_calls > 80:
                raise SecurityDenied("本輪院方查詢已達上限，請稍後重試。")
    try:
        with Session(security_engine()) as session, session.begin():
            key, holder = lease(session, "provider:" + provider, 8, 60)
            rate(session, "provider:" + provider, setting("PROVIDER_REQUESTS_PER_MINUTE", 180))
    except AGENT_STORAGE_ERRORS:
        raise SecurityDenied("院方流量保護暫時無法確認，已停止查詢。", 503) from None
    try:
        yield
    finally:
        release(key, holder)


def storage_lock(session):
    statement = insert_for(session, SecurityCounter).values(key="storage-lock", amount=0, expires=2**62).on_conflict_do_nothing()
    session.execute(statement)
    session.execute(update(SecurityCounter).where(SecurityCounter.key == "storage-lock").values(amount=0))
