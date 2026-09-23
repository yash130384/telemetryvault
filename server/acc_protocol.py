import struct
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

PROTOCOL_VERSION = 4

REGISTER_COMMAND_APPLICATION = 1
UNREGISTER_COMMAND_APPLICATION = 9
REQUEST_ENTRY_LIST = 10
REQUEST_TRACK_DATA = 11

REGISTRATION_RESULT = 1
REALTIME_UPDATE = 2
REALTIME_CAR_UPDATE = 3
ENTRY_LIST = 4
TRACK_DATA = 5
ENTRY_LIST_CAR = 6

_NO_TIME = 2147483647
_GEAR_OFFSET = 1

@dataclass
class LapInfo:
    laptime_ms: Optional[int] = None
    splits: List[Optional[int]] = field(default_factory=list)
    is_invalid: bool = False
    is_valid_for_best: bool = False

@dataclass
class RegistrationResult:
    connection_id: int
    success: bool
    read_only: bool
    error: str

@dataclass
class RealtimeUpdate:
    focused_car_index: int
    session_phase: int
    event_index: int = 0
    session_index: int = 0
    session_time_ms: float = 0.0

@dataclass
class RealtimeCarUpdate:
    car_index: int
    gear: int
    kmh: int
    world_pos_x: float
    world_pos_y: float
    spline_position: float
    car_location: int
    laps: int
    delta_ms: int
    best_lap: LapInfo
    last_lap: LapInfo
    current_lap: LapInfo

@dataclass
class TrackData:
    track_name: str
    track_id: int
    track_meters: int

@dataclass
class DriverInfo:
    first_name: str
    last_name: str
    short_name: str

@dataclass
class CarEntry:
    car_index: int
    car_model_type: int
    team_name: str
    race_number: int
    current_driver_index: int
    drivers: List[DriverInfo]

class Reader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    def take(self, fmt: str):
        val = struct.unpack_from(fmt, self.data, self.pos)[0]
        self.pos += struct.calcsize(fmt)
        return val

    def u8(self) -> int: return self.take("<B")
    def u16(self) -> int: return self.take("<H")
    def i32(self) -> int: return self.take("<i")
    def f32(self) -> float: return self.take("<f")
    def string(self) -> str:
        length = self.u16()
        raw = self.data[self.pos : self.pos + length]
        self.pos += length
        return raw.decode("utf-8", "replace")

def read_lap(r: Reader) -> LapInfo:
    laptime = r.i32()
    r.u16() # car index
    r.u16() # driver index
    split_count = r.u8()
    splits = [r.i32() for _ in range(split_count)]
    is_invalid = r.u8() > 0
    is_valid_for_best = r.u8() > 0
    r.u8() # is outlap
    r.u8() # is inlap
    return LapInfo(
        laptime_ms=None if laptime == _NO_TIME else laptime,
        splits=[None if s == _NO_TIME else s for s in splits],
        is_invalid=is_invalid,
        is_valid_for_best=is_valid_for_best
    )

def parse_packet(data: bytes):
    if not data:
        return None
    r = Reader(data)
    msg_type = r.u8()

    if msg_type == REGISTRATION_RESULT:
        conn_id = r.i32()
        success = r.u8() > 0
        read_only = r.u8() > 0
        err = r.string()
        return RegistrationResult(conn_id, success, read_only, err)

    if msg_type == REALTIME_UPDATE:
        event_index = r.u16()
        session_index = r.u16()
        r.u8() # session type
        phase = r.u8()
        session_time_ms = r.f32()
        r.f32() # session end time
        focused = r.i32()
        return RealtimeUpdate(
            focused_car_index=focused,
            session_phase=phase,
            event_index=event_index,
            session_index=session_index,
            session_time_ms=session_time_ms
        )

    if msg_type == REALTIME_CAR_UPDATE:
        car_index = r.u16()
        r.u16() # driver index
        r.u8() # driver count
        gear = r.u8() - _GEAR_OFFSET
        world_x = r.f32()
        world_y = r.f32()
        r.f32() # yaw
        car_location = r.u8()
        kmh = r.u16()
        r.u16() # official pos
        r.u16() # cup pos
        r.u16() # track pos
        spline = r.f32()
        laps = r.u16()
        delta = r.i32()
        best = read_lap(r)
        last = read_lap(r)
        current = read_lap(r)
        return RealtimeCarUpdate(
            car_index=car_index,
            gear=gear,
            kmh=kmh,
            world_pos_x=world_x,
            world_pos_y=world_y,
            spline_position=spline,
            car_location=car_location,
            laps=laps,
            delta_ms=delta,
            best_lap=best,
            last_lap=last,
            current_lap=current
        )

    if msg_type == TRACK_DATA:
        r.i32()
        name = r.string()
        track_id = r.i32()
        meters = r.i32()
        return TrackData(track_name=name, track_id=track_id, track_meters=meters)

    if msg_type == ENTRY_LIST_CAR:
        car_idx = r.u16()
        model_type = r.u8()
        team_name = r.string()
        race_num = r.i32()
        cup = r.u8()
        curr_driver_idx = r.u8()
        nationality = r.u16()
        driver_count = r.u8()
        drivers = []
        for _ in range(driver_count):
            first = r.string()
            last = r.string()
            short = r.string()
            r.u8() # category
            r.u16() # nationality
            drivers.append(DriverInfo(first_name=first, last_name=last, short_name=short))
        return CarEntry(
            car_index=car_idx,
            car_model_type=model_type,
            team_name=team_name,
            race_number=race_num,
            current_driver_index=curr_driver_idx,
            drivers=drivers
        )

    return None

def write_string(s: str) -> bytes:
    raw = s.encode("utf-8")
    return struct.pack("<H", len(raw)) + raw

def build_registration_request(display_name="TelemetryVault", update_interval_ms=100) -> bytes:
    return (
        struct.pack("<BB", REGISTER_COMMAND_APPLICATION, PROTOCOL_VERSION)
        + write_string(display_name)
        + write_string("")
        + struct.pack("<i", update_interval_ms)
        + write_string("")
    )

def build_request_track_data(connection_id: int) -> bytes:
    return struct.pack("<Bi", REQUEST_TRACK_DATA, connection_id)

def build_request_entry_list(connection_id: int) -> bytes:
    return struct.pack("<Bi", REQUEST_ENTRY_LIST, connection_id)
