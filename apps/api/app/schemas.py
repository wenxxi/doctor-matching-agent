from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class DoctorExpertiseResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    keyword: str
    canonical_keyword: str | None
    category: str | None


class DoctorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    hospital: str
    campus: str | None
    department: str
    subspecialty: str | None
    title: str | None
    profile_url: str | None
    registration_url: str | None
    bio: str | None
    raw_expertise: str | None
    created_at: datetime
    updated_at: datetime
    expertise: list[DoctorExpertiseResponse]
