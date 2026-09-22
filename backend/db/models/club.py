"""Clubs and club membership (``clubs``, ``user_clubs``).

Membership (``user_clubs``) is plain visibility/affiliation — independent of
the RBAC roles: a scoped ``club_admin``/``race_officer`` grant lives in
``user_roles.scope_club_id``. Clubs are never hard-deleted; they are
deactivated via ``is_active`` to preserve history (regattas, members, boats).
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..base import Base, CreatedAtMixin, TimestampMixin, UUIDPKMixin, enum_check

# invited = manager invited the user (user accepts); requested = user asked to
# join (manager approves). Both are pending, but who may activate them differs.
USER_CLUB_STATUSES = ("invited", "requested", "active", "deleted")


class ClubORM(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "clubs"
    __table_args__ = (UniqueConstraint("osm_ref"), UniqueConstraint("school_osm_ref"))
    __wire_children__ = {"members": "members"}

    name: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    address_line_1: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    address_line_2: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    state_province: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    postal_code: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # free format
    country: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)  # ISO 3166-1 alpha-2
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    founded_year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    website: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    contact_email: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    logo_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        ForeignKey("images.id", ondelete="SET NULL"), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Does this club run a sailing school? Declared by its own managers, and
    # deliberately independent of OSM: a club that teaches but is not mapped
    # must still be able to say so. ``GET /clubs/{id}/school-suggestion`` only
    # *proposes* the value from the cached POIs; setting it is PATCH /clubs.
    #
    # NOT NULL default false rather than a nullable "unknown" tri-state: the
    # flag drives a badge and a filter, where "we don't know" and "no" render
    # identically, so a third state would buy nothing while forcing every
    # consumer to handle NULL. The unknown case is answered by the suggestion
    # endpoint, which is computed per request and never stored.
    has_sailing_school: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # The OSM element this club *is*, as "{osm_type}/{osm_id}" (e.g. "way/123456").
    # Deliberately the exact string the frontend already computes as
    # ``NauticalPoi.id``, so deduping the Overpass POI against this club on the
    # explorer map is a plain equality with no parsing on either side. UNIQUE
    # because one OSM element maps to at most one club — that constraint *is*
    # the anti-duplication guarantee. NULL until someone links the two.
    osm_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    # The **separate** OSM element that is this club's sailing school, in the
    # same "{osm_type}/{osm_id}" form — distinct from ``osm_ref`` above, which
    # is the club itself. It exists so the explorer map can stop drawing a
    # second pin for a school a club has confirmed as its own: without it,
    # ``has_sailing_school`` says *that* there is a school but not *which*
    # element it is, and the map has nothing to dedupe against.
    #
    # UNIQUE for the same reason ``osm_ref`` is: one OSM element belongs to at
    # most one club, and that constraint *is* the anti-duplication guarantee.
    # The router checks both columns together, since an element another club
    # declares itself to be is just as taken (``routers/clubs.py``).
    #
    # NULL is the normal state, including for a club whose school is tagged on
    # its *own* element (``amenity=sailing_school`` on the club): there is only
    # one element there and ``osm_ref`` already dedupes it, so recording it
    # here too would be a second, driftable copy — the router rejects it.
    # Non-NULL always implies ``has_sailing_school``.
    school_osm_ref: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    members: Mapped[list["UserClubORM"]] = relationship(
        back_populates="club", cascade="all, delete-orphan", lazy="selectin"
    )


class UserClubORM(UUIDPKMixin, CreatedAtMixin, Base):
    __tablename__ = "user_clubs"
    __table_args__ = (
        UniqueConstraint("user_id", "club_id"),
        enum_check("status", USER_CLUB_STATUSES),
    )
    __wire_exclude__ = ("id", "club_id")

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    club_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"))
    status: Mapped[str] = mapped_column(String, nullable=False, default="invited")
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    club: Mapped["ClubORM"] = relationship(back_populates="members")
