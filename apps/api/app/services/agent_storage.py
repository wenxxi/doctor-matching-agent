import os
import sqlite3
import threading
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.sqlite import SqliteSaver
from sqlalchemy import create_engine, event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from psycopg import Error as PsycopgError

from app.agent_models import AgentOwner, AgentTask, CareCase, CaseMessage


class AgentStorageError(Exception):
    pass


AGENT_STORAGE_ERRORS = (AgentStorageError, SQLAlchemyError, sqlite3.DatabaseError, PsycopgError, OSError)
INITIALIZATION_LOCK = threading.Lock()


@lru_cache(maxsize=1)
def get_agent_engine():
    database_url = os.getenv("AGENT_DATABASE_URL") or os.getenv("DATABASE_URL")
    if not database_url:
        if os.getenv("RENDER"):
            raise AgentStorageError("線上個案記憶尚未連接 PostgreSQL，請先設定 AGENT_DATABASE_URL。")
        path = Path(__file__).resolve().parents[4] / "var" / "agent-memory.sqlite3"
        path.parent.mkdir(parents=True, exist_ok=True)
        database_url = f"sqlite:///{path}"
    if database_url.startswith("postgres://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgres://")
    elif database_url.startswith("postgresql://"):
        database_url = "postgresql+psycopg://" + database_url.removeprefix("postgresql://")
    parsed = make_url(database_url)
    if parsed.get_backend_name() not in {"sqlite", "postgresql"}:
        raise AgentStorageError("個案記憶需要 PostgreSQL 或本機 SQLite。")
    if parsed.get_backend_name() == "sqlite" and (os.getenv("RENDER") or not parsed.database or parsed.database == ":memory:"):
        raise AgentStorageError("線上記憶需要 PostgreSQL；本機 SQLite 必須使用檔案。")
    engine = create_engine(database_url, pool_pre_ping=True,
                           connect_args={"check_same_thread": False, "timeout": 30} if parsed.get_backend_name() == "sqlite" else {"connect_timeout": 10})
    if parsed.get_backend_name() == "sqlite":
        @event.listens_for(engine, "connect")
        def configure_sqlite(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
    return engine


@lru_cache(maxsize=1)
def initialize_agent_storage():
    engine = get_agent_engine()
    with INITIALIZATION_LOCK:
        for model in (AgentOwner, CareCase, AgentTask, CaseMessage):
            model.__table__.create(engine, checkfirst=True)
        with checkpoint_store() as saver:
            saver.setup()
    return engine


def get_agent_session():
    with Session(initialize_agent_storage(), expire_on_commit=False) as session:
        yield session


@contextmanager
def checkpoint_store():
    parsed = get_agent_engine().url
    if parsed.get_backend_name() == "sqlite":
        with sqlite3.connect(parsed.database, check_same_thread=False, timeout=30) as connection:
            yield SqliteSaver(connection)
    else:
        connection_string = parsed.set(drivername="postgresql", query={**parsed.query, "connect_timeout": "10"}).render_as_string(hide_password=False)
        with PostgresSaver.from_conn_string(connection_string) as saver:
            yield saver
