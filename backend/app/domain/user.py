"""User ORM model: the authenticated Google account that owns assets and buckets."""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class User(Base):
    """An authenticated user, keyed to a Google account by its stable `sub` claim.

    Lives in `app/domain/` under the MVP 1:1 entity/model shortcut. Carries the workspace-wide
    display preferences the settings panel (#67) edits: `default_currency` (relabel-only display
    currency new buckets adopt) and `language` (persisted preference; UI translation lands later).
    Both have server defaults so existing and future rows are valid without explicit values.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"), default=uuid.uuid4
    )
    google_sub: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    email: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False, server_default=text("''"))
    default_currency: Mapped[str] = mapped_column(String(3), nullable=False, server_default=text("'HUF'"))
    language: Mapped[str] = mapped_column(String(16), nullable=False, server_default=text("'en'"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))
