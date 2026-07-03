import os
from functools import lru_cache
from collections.abc import Iterator

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

load_dotenv()


class Base(DeclarativeBase):
    pass


class DatabaseHealthError(Exception):
    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


@lru_cache(maxsize=1)
def get_database_url() -> str | None:
    return os.getenv("DATABASE_URL")


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    database_url = get_database_url()
    if not database_url:
        raise DatabaseHealthError("DATABASE_URL is not configured")

    connect_args = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
    return create_engine(database_url, pool_pre_ping=True, connect_args=connect_args)


@lru_cache(maxsize=1)
def get_sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(autocommit=False, autoflush=False, bind=get_engine())


def get_session() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


def check_database_connection() -> dict[str, str]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("SELECT 1"))
    except DatabaseHealthError:
        raise
    except SQLAlchemyError as exc:
        raise DatabaseHealthError("Database connection failed") from exc

    return {"status": "ok", "database": "connected"}
