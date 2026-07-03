import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database import Base


class Doctor(Base):
    __tablename__ = "doctors"
    __table_args__ = (
        UniqueConstraint(
            "name",
            "hospital",
            "department",
            "profile_url",
            name="uq_doctors_identity",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    hospital: Mapped[str] = mapped_column(Text, nullable=False)
    campus: Mapped[str | None] = mapped_column(Text, nullable=True)
    department: Mapped[str] = mapped_column(Text, nullable=False)
    subspecialty: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    profile_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    registration_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    bio: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_expertise: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    expertise: Mapped[list["DoctorExpertise"]] = relationship(
        back_populates="doctor",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DoctorExpertise(Base):
    __tablename__ = "doctor_expertise"
    __table_args__ = (
        UniqueConstraint("doctor_id", "keyword", name="uq_doctor_expertise_keyword"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    doctor_id: Mapped[uuid.UUID] = mapped_column(
        Uuid,
        ForeignKey("doctors.id", ondelete="CASCADE"),
        nullable=False,
    )
    keyword: Mapped[str] = mapped_column(Text, nullable=False)
    canonical_keyword: Mapped[str | None] = mapped_column(Text, nullable=True)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    doctor: Mapped[Doctor] = relationship(back_populates="expertise")
