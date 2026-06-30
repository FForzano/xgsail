"""SQLAlchemy declarative base. ISO timestamps/dates are stored as strings to
round-trip the domain models byte-for-byte with the object backend."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
