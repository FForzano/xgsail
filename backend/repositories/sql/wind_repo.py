"""SQL wind repository: ``wind_stations`` + ``wind_observations`` cache.

``upsert_observations`` relies on the unique (wind_station_id, observed_at)
constraint with ``ON CONFLICT DO NOTHING`` so the periodic fetch job is
idempotent by construction.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ...db.models import WindObservationORM, WindStationORM

_STATION_FIELDS = ("provider", "external_station_id", "name", "station_type", "lat", "lng")
_OBS_FIELDS = ("observed_at", "twd_deg", "tws_kts", "gust_kts")


class SqlWindRepo:
    def __init__(self, session_factory):
        self.Session = session_factory

    # --- stations ---

    def list(self, *, provider: Optional[str] = None) -> "list[WindStationORM]":
        with self.Session() as s:
            q = select(WindStationORM)
            if provider is not None:
                q = q.where(WindStationORM.provider == provider)
            return list(s.scalars(q).all())

    def get(self, station_id: uuid.UUID) -> Optional[WindStationORM]:
        with self.Session() as s:
            return s.get(WindStationORM, station_id)

    def get_by_provider_external(self, provider: str,
                                 external_station_id: str) -> Optional[WindStationORM]:
        with self.Session() as s:
            return s.scalars(
                select(WindStationORM).where(
                    WindStationORM.provider == provider,
                    WindStationORM.external_station_id == external_station_id,
                )
            ).first()

    def create(self, data: dict) -> WindStationORM:
        with self.Session() as s:
            orm = WindStationORM(**{k: data.get(k) for k in _STATION_FIELDS if k in data})
            s.add(orm)
            s.commit()
            new_id = orm.id
        return self.get(new_id)

    def update(self, station_id: uuid.UUID, changes: dict) -> Optional[WindStationORM]:
        with self.Session() as s:
            orm = s.get(WindStationORM, station_id)
            if orm is None:
                return None
            for k, v in changes.items():
                if k in _STATION_FIELDS:
                    setattr(orm, k, v)
            s.commit()
        return self.get(station_id)

    def delete(self, station_id: uuid.UUID) -> bool:
        with self.Session() as s:
            orm = s.get(WindStationORM, station_id)
            if orm is None:
                return False
            s.delete(orm)
            s.commit()
            return True

    # --- observations ---

    def upsert_observations(self, station_id: uuid.UUID, rows: "list[dict]") -> int:
        """Insert observations, silently skipping (station, observed_at)
        duplicates. Returns the number actually inserted."""
        if not rows:
            return 0
        values = [
            {"wind_station_id": station_id, **{k: r.get(k) for k in _OBS_FIELDS}}
            for r in rows
        ]
        with self.Session() as s:
            stmt = (
                pg_insert(WindObservationORM)
                .values(values)
                .on_conflict_do_nothing(index_elements=["wind_station_id", "observed_at"])
                .returning(WindObservationORM.id)  # rowcount is -1 for ON CONFLICT inserts
            )
            inserted = len(s.execute(stmt).fetchall())
            s.commit()
            return inserted

    def list_observations(self, station_id: uuid.UUID, *,
                          start: Optional[datetime] = None,
                          end: Optional[datetime] = None) -> "list[WindObservationORM]":
        with self.Session() as s:
            q = select(WindObservationORM).where(
                WindObservationORM.wind_station_id == station_id
            )
            if start is not None:
                q = q.where(WindObservationORM.observed_at >= start)
            if end is not None:
                q = q.where(WindObservationORM.observed_at <= end)
            q = q.order_by(WindObservationORM.observed_at)
            return list(s.scalars(q).all())
