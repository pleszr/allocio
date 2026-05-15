"""Greeting domain entity. Maps 1:1 to the `greetings` table (MVP shortcut)."""
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Greeting(Base):
    """A short greeting message returned by the public greeting endpoint."""

    __tablename__ = "greetings"

    id: Mapped[int] = mapped_column(primary_key=True)
    message: Mapped[str] = mapped_column(nullable=False)
