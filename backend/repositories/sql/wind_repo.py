"""SQL wind repository — two distinct concepts (see ``db/models/wind.py``):

- ``wind_stations``/``wind_observations``: raw acquisition, real fixed
  stations only. ``upsert_observations`` relies on the unique
  (wind_station_id, observed_at) constraint with ``ON CONFLICT DO NOTHING``
  so the periodic fetch job is idempotent by construction.
- ``wind_estimates``: the determined wind per grid cell/time bucket,
  read/written by whatever refinement strategy is active (see
  ``services/wind_estimate_refinement.py``) — this repo only stores
  whatever it decides, no logic of its own.
"""

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from ...db.models import WindEstimateORM, WindObservationORM, WindStationORM

_STATION_FIELDS = ("provider", "external_station_id", "name", "station_type", "lat", "lng",
                   "keeps_local_history", "source_url")
_OBS_FIELDS = ("observed_at", "twd_deg", "tws_kts", "gust_kts")
_ESTIMATE_FIELDS = ("twd_deg", "tws_kts", "gust_kts", "confidence", "sources")


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

    # --- observations (real stations only — see module docstring) ---

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
                          end: Optional[datetime] = None,
                          limit: int = 500, offset: int = 0) -> "list[WindObservationORM]":
        """Paginated, newest-first (page 0 = most recent). The cache grows
        without bound (idempotent upsert on every scheduler tick) — callers
        MUST page through it rather than fetch it whole; see the default
        72h window in ``routers/wind.py`` when start/end are omitted."""
        with self.Session() as s:
            q = select(WindObservationORM).where(
                WindObservationORM.wind_station_id == station_id
            )
            if start is not None:
                q = q.where(WindObservationORM.observed_at >= start)
            if end is not None:
                q = q.where(WindObservationORM.observed_at <= end)
            q = q.order_by(WindObservationORM.observed_at.desc()).limit(limit).offset(offset)
            return list(s.scalars(q).all())

    def find_nearest(self, lat: float, lng: float, *,
                     providers: "Optional[list[str]]" = None,
                     max_km: float = 50) -> Optional[WindStationORM]:
        """Closest real station within ``max_km``, optionally restricted to
        ``providers`` (haversine, computed in Python — station counts are
        small, no need for PostGIS)."""
        from ...services.geo import haversine_m

        with self.Session() as s:
            q = select(WindStationORM).where(
                WindStationORM.lat.is_not(None), WindStationORM.lng.is_not(None)
            )
            if providers is not None:
                q = q.where(WindStationORM.provider.in_(providers))
            stations = list(s.scalars(q).all())
        best, best_km = None, max_km
        for st in stations:
            km = haversine_m(lat, lng, st.lat, st.lng) / 1000
            if km <= best_km:
                best, best_km = st, km
        return best

    # --- wind estimates (determined value per grid cell/time bucket) ---

    def get_estimate(self, grid_lat: float, grid_lng: float,
                     time_bucket: datetime) -> Optional[WindEstimateORM]:
        with self.Session() as s:
            return s.scalars(
                select(WindEstimateORM).where(
                    WindEstimateORM.grid_lat == grid_lat,
                    WindEstimateORM.grid_lng == grid_lng,
                    WindEstimateORM.time_bucket == time_bucket,
                )
            ).first()

    def upsert_estimate(self, grid_lat: float, grid_lng: float, time_bucket: datetime,
                        data: dict) -> WindEstimateORM:
        """Write the row a refinement strategy decided on (see
        ``services/wind_estimate_refinement.py``) — a full replace, not a
        merge: the strategy already read the existing row (if any) via
        ``get_estimate`` and decided the complete new state."""
        values = {
            "grid_lat": grid_lat, "grid_lng": grid_lng, "time_bucket": time_bucket,
            **{k: data.get(k) for k in _ESTIMATE_FIELDS},
        }
        with self.Session() as s:
            stmt = pg_insert(WindEstimateORM).values(values)
            stmt = stmt.on_conflict_do_update(
                index_elements=["grid_lat", "grid_lng", "time_bucket"],
                set_={
                    "twd_deg": stmt.excluded.twd_deg,
                    "tws_kts": stmt.excluded.tws_kts,
                    "gust_kts": stmt.excluded.gust_kts,
                    "confidence": stmt.excluded.confidence,
                    "sources": stmt.excluded.sources,
                    "refined_at": func.now(),
                },
            )
            s.execute(stmt)
            s.commit()
        return self.get_estimate(grid_lat, grid_lng, time_bucket)

    def list_estimates_for_cells(self, cells: "list[tuple[float, float]]",
                                 start: datetime, end: datetime) -> "list[WindEstimateORM]":
        """Estimates already on file for a set of (grid_lat, grid_lng) cells
        within ``[start, end]`` — used by ``ingestion.write_wind_cache`` to
        bundle existing grid knowledge alongside freshly-fetched raw data for
        a session's waypoints."""
        if not cells:
            return []
        with self.Session() as s:
            cell_match = or_(*[
                (WindEstimateORM.grid_lat == lat) & (WindEstimateORM.grid_lng == lng)
                for lat, lng in cells
            ])
            q = select(WindEstimateORM).where(
                cell_match,
                WindEstimateORM.time_bucket >= start,
                WindEstimateORM.time_bucket <= end,
            )
            return list(s.scalars(q).all())
