from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.database import get_session
from app.models import Doctor, DoctorExpertise
from app.schemas import DoctorResponse

router = APIRouter(prefix="/api/doctors", tags=["doctors"])


def _case_insensitive_equals(column, value: str):
    return func.lower(column) == value.lower()


@router.get("", response_model=list[DoctorResponse])
def list_doctors(
    session: Annotated[Session, Depends(get_session)],
    hospital: Annotated[str | None, Query()] = None,
    campus: Annotated[str | None, Query()] = None,
    department: Annotated[str | None, Query()] = None,
    keyword: Annotated[str | None, Query()] = None,
) -> list[Doctor]:
    statement = select(Doctor).options(selectinload(Doctor.expertise))

    if hospital:
        statement = statement.where(_case_insensitive_equals(Doctor.hospital, hospital))
    if campus:
        statement = statement.where(_case_insensitive_equals(Doctor.campus, campus))
    if department:
        statement = statement.where(_case_insensitive_equals(Doctor.department, department))
    if keyword:
        keyword_pattern = f"%{keyword.lower()}%"
        statement = statement.join(Doctor.expertise).where(
            or_(
                func.lower(DoctorExpertise.keyword).like(keyword_pattern),
                func.lower(DoctorExpertise.canonical_keyword).like(keyword_pattern),
            )
        )

    statement = statement.distinct().order_by(Doctor.hospital, Doctor.department, Doctor.name)
    return list(session.scalars(statement).all())
