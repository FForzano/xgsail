"""Data schemas for SailFrames analysis engine.

Defines structured models for sessions, boats, maneuvers, legs,
and analysis results used throughout the processing pipeline.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class ManeuverType(str, Enum):
    TACK = "tack"
    GYBE = "gybe"
    # A significant course change that does NOT cross the wind / change tacks
    # (bearing away, luffing up, a reach-to-reach heading change, a mark
    # rounding that isn't a tack/gybe). Introduced end-to-end but DORMANT: the
    # active geometric classifier never emits it, so no maneuver is labelled
    # course_change today. It becomes populated once (a) Stage 1 detection is
    # broadened beyond wind-axis crossings and/or (b) the ML classifier
    # (maneuver_classification._ml_classifier) is registered. When that lands,
    # decide whether a course_change opens a new leg in segment_legs (it does
    # NOT flip tacks the way a tack/gybe does). The DB CHECK constraint
    # (backend/db/models/session.py: MANEUVER_TYPES) already allows it.
    COURSE_CHANGE = "course_change"


class PointOfSail(str, Enum):
    UPWIND = "upwind"
    DOWNWIND = "downwind"
    REACHING = "reaching"
    CLOSE_REACH = "close_reach"
    BROAD_REACH = "broad_reach"


class LegType(str, Enum):
    UPWIND = "upwind"
    DOWNWIND = "downwind"
    REACH = "reach"


@dataclass
class BoatProfile:
    boat_id: str
    name: str
    boat_class: str  # e.g. "Sonar 23", "J/80"
    sail_number: Optional[str] = None
    crew_weight_kg: Optional[float] = None
    jib_type: Optional[str] = None
    main_type: Optional[str] = None
    notes: Optional[str] = None


@dataclass
class GpsPoint:
    timestamp: float  # unix epoch
    lat: float
    lon: float
    speed_kts: float
    heading_deg: float
    fix_quality: int = 0


@dataclass
class ImuReading:
    timestamp: float
    heading_deg: float
    pitch_deg: float
    heel_deg: float
    accel_x: float = 0.0
    accel_y: float = 0.0
    accel_z: float = 0.0


@dataclass
class WindReading:
    timestamp: float
    apparent_speed_kts: float
    apparent_angle_deg: float  # 0=bow, 180=stern, positive=starboard


@dataclass
class PressureReading:
    timestamp: float
    pressure_hpa: float
    temperature_c: float


@dataclass
class Maneuver:
    maneuver_type: ManeuverType
    start_time: float
    end_time: float
    duration_sec: float
    speed_loss_kts: float  # speed before minus minimum speed during
    speed_before_kts: float
    speed_min_kts: float
    speed_after_kts: float
    recovery_time_sec: float  # time to regain 90% of entry speed
    heading_change_deg: float
    distance_lost_m: Optional[float] = None
    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    # The statistical feature vector for this maneuver (see
    # processing/maneuver_features.py). Persisted as JSON on session_maneuvers
    # to accumulate a training dataset for the future ML classifier. Additive:
    # the set/values of the fields above are unchanged. May be None when no
    # features were computed.
    features: Optional[dict] = None


@dataclass
class ManeuverCandidate:
    """A detected significant course change BEFORE it is classified — Stage 1
    output. Carries the boundaries and the type-independent metrics already
    computed during detection, plus the ``features`` dict a classifier
    (geometric today, ML tomorrow) consumes. Internal to the worker: never
    serialized or persisted directly; ``_finalize`` turns a classified
    candidate into a ``Maneuver``.

    Metrics that only describe the specific occurrence (position, timing) sit
    here as their own fields and end up as ``Maneuver`` columns. Metrics that
    characterize the maneuver itself (e.g. heel) go straight into ``features``
    instead — see ``max_heel_deg`` handling in ``_detect_candidates``, which
    feeds it directly into ``FeatureContext`` rather than carrying it as a
    field here.
    """
    start_time: float
    end_time: float
    duration_sec: float
    heading_change_deg: float
    speed_before_kts: float
    speed_min_kts: float
    speed_after_kts: float
    recovery_time_sec: float
    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    # Classifier inputs (rel_before/rel_after to the wind axis) + the richer
    # configurable statistics. Keys defined by maneuver_features.ENABLED_FEATURES.
    features: dict = field(default_factory=dict)


@dataclass
class StraightLineLeg:
    leg_type: LegType
    start_time: float
    end_time: float
    duration_sec: float
    distance_nm: float
    avg_speed_kts: float
    max_speed_kts: float
    avg_vmg_kts: float
    avg_heel_deg: Optional[float] = None
    avg_twa_deg: Optional[float] = None
    tack: Optional[str] = None  # "port" | "starboard" — which side the wind is on
    std_heading_deg: float = 0.0  # heading stability
    num_points: int = 0
    start_lat: Optional[float] = None
    start_lon: Optional[float] = None
    end_lat: Optional[float] = None
    end_lon: Optional[float] = None


@dataclass
class PolarPoint:
    twa_deg: float  # true wind angle bucket center
    tws_kts: float  # true wind speed bucket center
    boat_speed_kts: float  # average or max boat speed
    vmg_kts: float
    sample_count: int = 0


@dataclass
class VmgResult:
    timestamp: float
    vmg_kts: float
    twa_deg: float
    boat_speed_kts: float
    tws_kts: Optional[float] = None
    optimal_vmg_kts: Optional[float] = None  # from polar
    vmg_efficiency: Optional[float] = None  # actual/optimal ratio


@dataclass
class SessionMetadata:
    device_id: str
    date: str  # YYYY-MM-DD
    start_time: float
    end_time: float
    duration_sec: float
    boat: Optional[BoatProfile] = None
    wind_avg_kts: Optional[float] = None
    wind_dir_avg_deg: Optional[float] = None
    distance_nm: Optional[float] = None
    max_speed_kts: Optional[float] = None
    num_tacks: int = 0
    num_gybes: int = 0


@dataclass
class SessionData:
    """Container for all sensor data in a session."""
    metadata: SessionMetadata
    gps: list[GpsPoint] = field(default_factory=list)
    imu: list[ImuReading] = field(default_factory=list)
    wind: list[WindReading] = field(default_factory=list)
    pressure: list[PressureReading] = field(default_factory=list)


@dataclass
class AnalysisResult:
    """Complete analysis output for a session."""
    session: SessionMetadata
    maneuvers: list[Maneuver] = field(default_factory=list)
    legs: list[StraightLineLeg] = field(default_factory=list)
    polar_points: list[PolarPoint] = field(default_factory=list)
    vmg_series: list[VmgResult] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


# =============================================================================
# Race Dashboard Models
# =============================================================================

@dataclass
class Regatta:
    """A regatta/series containing multiple races."""
    regatta_id: str
    name: str  # "J/80 Spring Series 2026"
    venue: str  # "Courageous Sailing Center"
    boat_class: str  # "J/80"
    start_date: str  # "2026-04-27"
    end_date: str  # "2026-05-25"
    race_ids: list[str] = field(default_factory=list)
    created_at: str = ""
    updated_at: str = ""


@dataclass
class StartFinishLine:
    """Start or finish line defined by two endpoints."""
    pin_lat: float  # Pin end coordinates
    pin_lon: float
    boat_lat: float  # Committee boat end
    boat_lon: float


@dataclass
class RaceBoat:
    """A boat entry in a race."""
    device_id: str  # "E1", "E2", etc.
    boat_name: str  # "Defiance"
    sail_number: str  # "123"
    session_path: Optional[str] = None  # Auto-matched session path


@dataclass
class StartAnalysis:
    """Start line analysis for a single boat."""
    time_to_line_sec: float  # Seconds from gun to crossing line
    distance_at_gun_m: float  # Distance from line at start signal
    speed_at_gun_kts: float  # Boat speed at gun
    line_end: str  # "pin" or "boat" - which end was closer
    ocs: bool  # Over early (crossed before gun)


@dataclass
class BoatRaceResult:
    """Race results for a single boat."""
    device_id: str
    finish_position: int  # Manual entry (1-based)
    elapsed_sec: float
    delta_to_leader_sec: float
    avg_speed_kts: float
    max_speed_kts: float
    tack_count: int
    gybe_count: int
    distance_nm: float
    start_analysis: Optional[StartAnalysis] = None


@dataclass
class RaceResults:
    """Computed results for a race."""
    finish_order: list[str] = field(default_factory=list)  # device_ids
    boat_results: dict = field(default_factory=dict)  # device_id -> BoatRaceResult
    computed_at: str = ""


@dataclass
class Mark:
    """A course mark (buoy) placed on the map."""
    mark_id: str
    name: str  # "Windward", "Leeward A", "Gate Port"
    mark_type: str  # "windward" | "leeward" | "gate_port" | "gate_stbd" | "offset" | "start_pin" | "start_boat" | "finish_pin" | "finish_boat" | "custom"
    lat: float
    lon: float


@dataclass
class Race:
    """A single race with boats, times, and results."""
    race_id: str
    name: str  # "Race 1"
    date: str  # "2026-05-04"
    start_time: str  # ISO timestamp (gun time)
    end_time: str  # ISO timestamp
    boats: list[RaceBoat] = field(default_factory=list)
    regatta_id: Optional[str] = None
    start_line: Optional[StartFinishLine] = None
    finish_line: Optional[StartFinishLine] = None
    marks: list[Mark] = field(default_factory=list)
    course: list[str] = field(default_factory=list)  # ordered mark_ids defining leg sequence
    finish_order: list[str] = field(default_factory=list)  # Manual entry
    results: Optional[RaceResults] = None
    created_at: str = ""
    updated_at: str = ""
