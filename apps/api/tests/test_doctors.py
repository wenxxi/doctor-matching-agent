from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_session
from app.main import app
from app.models import Doctor
from scripts.import_doctors import SAMPLE_CSV_PATH, import_doctors


@pytest.fixture()
def session() -> Session:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    testing_sessionmaker = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    with testing_sessionmaker() as db_session:
        yield db_session


@pytest.fixture()
def client(session: Session) -> TestClient:
    def override_get_session():
        yield session

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def test_importing_sample_doctors(session: Session):
    result = import_doctors(Path(SAMPLE_CSV_PATH), session)
    session.commit()

    doctors = session.scalars(select(Doctor)).all()

    assert result == {"created": 12, "updated": 0}
    assert len(doctors) == 12
    assert all(doctor.expertise for doctor in doctors)


def test_importing_sample_doctors_is_idempotent(session: Session):
    import_doctors(Path(SAMPLE_CSV_PATH), session)
    session.commit()

    result = import_doctors(Path(SAMPLE_CSV_PATH), session)
    session.commit()

    doctors = session.scalars(select(Doctor)).all()
    assert result == {"created": 0, "updated": 12}
    assert len(doctors) == 12


def test_get_doctors_returns_doctors(client: TestClient, session: Session):
    import_doctors(Path(SAMPLE_CSV_PATH), session)
    session.commit()

    response = client.get("/api/doctors")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 12
    assert data[0]["name"]
    assert data[0]["expertise"]


def test_get_doctors_filters_by_department(client: TestClient, session: Session):
    import_doctors(Path(SAMPLE_CSV_PATH), session)
    session.commit()

    response = client.get("/api/doctors", params={"department": "Cardiology"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["department"] == "Cardiology"


def test_get_doctors_filters_by_keyword(client: TestClient, session: Session):
    import_doctors(Path(SAMPLE_CSV_PATH), session)
    session.commit()

    response = client.get("/api/doctors", params={"keyword": "stroke"})

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert {doctor["department"] for doctor in data} == {"Neurology", "Rehabilitation Medicine"}
