from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class SessionSummary(BaseModel):
    id: int
    track: str
    car: str
    driver: str
    started_at: datetime
    ended_at: Optional[datetime] = None
    is_active: bool
    frame_count: int
    duration_seconds: float
    total_laps: int
    best_lap_time_ms: Optional[int] = None
    created_at: datetime

class LapSummary(BaseModel):
    id: int
    session_id: int
    lap_number: int
    lap_time_ms: Optional[int] = None
    is_valid: bool = True
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    sector1_ms: Optional[int] = None
    sector2_ms: Optional[int] = None
    sector3_ms: Optional[int] = None
    max_speed: float = 0.0
    avg_speed: float = 0.0
    frame_count: int = 0

class TelemetryFrame(BaseModel):
    id: Optional[int] = None
    session_id: Optional[int] = None
    lap_number: int = 0
    timestamp: datetime
    session_time: float = 0.0
    lap_time_ms: int = 0
    track_pos: float = 0.0
    speed: float = 0.0
    rpm: int = 0
    max_rpm: int = 8500
    gear: int = 0
    throttle: float = 0.0
    brake: float = 0.0
    clutch: float = 0.0
    steer: float = 0.0
    coord_x: float = 0.0
    coord_y: float = 0.0
    coord_z: float = 0.0
    yaw_rate: float = 0.0
    g_force_lat: float = 0.0
    g_force_lon: float = 0.0
    tyre_press_fl: float = 0.0
    tyre_press_fr: float = 0.0
    tyre_press_rl: float = 0.0
    tyre_press_rr: float = 0.0
    tyre_temp_fl: float = 0.0
    tyre_temp_fr: float = 0.0
    tyre_temp_rl: float = 0.0
    tyre_temp_rr: float = 0.0
    brake_temp_fl: float = 0.0
    brake_temp_fr: float = 0.0
    brake_temp_rl: float = 0.0
    brake_temp_rr: float = 0.0
    fuel: float = 0.0
    raw_data: Optional[Dict[str, Any]] = None

class LiveStatus(BaseModel):
    status: str
    active_session_id: Optional[int] = None
    track: Optional[str] = None
    car: Optional[str] = None
    driver: Optional[str] = None
    frame_count: int = 0
    duration_seconds: float = 0.0
    current_lap: int = 0
    current_speed: float = 0.0
    current_rpm: int = 0
    current_gear: int = 0
