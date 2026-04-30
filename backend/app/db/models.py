from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base. Concrete models (Document, DocChunk) land in Phase 2."""
