import asyncio
import datetime
import json
import logging
import time
from typing import Optional, Dict, Any, List, Set
from fastapi import WebSocket
from server.config import UDP_HOST, UDP_PORT, SESSION_IDLE_TIMEOUT
from server.db import get_db_pool

logger = logging.getLogger("telemetryvault.ingest")

COLS = [
    "session_id", "lap_number", "timestamp", "session_time", "lap_time_ms", "track_pos",
    "speed", "rpm", "max_rpm", "gear", "throttle", "brake", "clutch", "steer",
    "coord_x", "coord_y", "coord_z", "yaw_rate", "g_force_lat", "g_force_lon",
    "tyre_press_fl", "tyre_press_fr", "tyre_press_rl", "tyre_press_rr",
    "tyre_temp_fl", "tyre_temp_fr", "tyre_temp_rl", "tyre_temp_rr",
    "brake_temp_fl", "brake_temp_fr", "brake_temp_rl", "brake_temp_rr",
    "fuel", "raw_data"
]

class TelemetryManager:
    def __init__(self):
        self.active_session_id: Optional[int] = None
        self.last_packet_time: float = 0.0
        self.session_started_at: Optional[datetime.datetime] = None
        self.frame_count: int = 0
        self.current_lap: int = 0
        self.lap_speeds: List[float] = []
        self.lap_start_time: Optional[datetime.datetime] = None
        self.lap_frame_count: int = 0
        self.best_lap_time_ms: Optional[int] = None
        self.total_laps: int = 0

        self.latest_frame: Optional[Dict[str, Any]] = None
        self.live_clients: Set[WebSocket] = set()
        self.queue: asyncio.Queue = asyncio.Queue(maxsize=10000)
        self.running: bool = False
        self._batch_task: Optional[asyncio.Task] = None
        self._idle_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    async def start(self):
        self.running = True
        self._batch_task = asyncio.create_task(self._batch_flusher())
        self._idle_task = asyncio.create_task(self._idle_checker())
        logger.info("Telemetry ingestion worker started.")

    async def stop(self):
        self.running = False
        if self._batch_task:
            self._batch_task.cancel()
        if self._idle_task:
            self._idle_task.cancel()
        # Flush remaining frames
        await self._flush_queue()
        # Close any active session
        if self.active_session_id is not None:
            await self.close_active_session()
        logger.info("Telemetry ingestion worker stopped.")

    def register_client(self, ws: WebSocket):
        self.live_clients.add(ws)

    def unregister_client(self, ws: WebSocket):
        self.live_clients.discard(ws)

    async def broadcast_live(self, data: Dict[str, Any]):
        if not self.live_clients:
            return
        dead = []
        msg = json.dumps(data)
        for client in self.live_clients:
            try:
                await client.send_text(msg)
            except Exception:
                dead.append(client)
        for d in dead:
            self.live_clients.discard(d)

    def parse_packet(self, data_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize various ACC/acs_ packet formats into standard fields."""
        speed = float(data_dict.get("speed") or data_dict.get("speedKmh") or data_dict.get("speed_kmh") or 0.0)
        rpm = int(data_dict.get("rpm") or data_dict.get("engineRPM") or data_dict.get("engine_rpm") or 0)
        max_rpm = int(data_dict.get("maxRpm") or data_dict.get("max_rpm") or 8500)
        gear = int(data_dict.get("gear") or data_dict.get("current_gear") or data_dict.get("gearInputsNormal") or 0)
        throttle = float(data_dict.get("throttle") or data_dict.get("gas") or data_dict.get("throttle_input") or 0.0)
        brake = float(data_dict.get("brake") or data_dict.get("brake_input") or 0.0)
        clutch = float(data_dict.get("clutch") or 0.0)
        steer = float(data_dict.get("steer") or data_dict.get("steerAngle") or data_dict.get("steering") or 0.0)
        lap = int(data_dict.get("lap") or data_dict.get("lap_number") or data_dict.get("currentLap") or 1)
        
        # Lap time: can be given in seconds or ms
        raw_lap_time = data_dict.get("lapTimeMs") or data_dict.get("lap_time_ms") or data_dict.get("lapTime") or 0
        if isinstance(raw_lap_time, float) and raw_lap_time < 3600.0:
            lap_time_ms = int(raw_lap_time * 1000)
        else:
            lap_time_ms = int(raw_lap_time)

        raw_last_lap = data_dict.get("last_lap_ms") or data_dict.get("lastLapMs") or data_dict.get("lastLapTimeMS")
        if isinstance(raw_last_lap, float) and raw_last_lap < 3600.0:
            last_lap_ms = int(raw_last_lap * 1000)
        elif raw_last_lap is not None:
            last_lap_ms = int(raw_last_lap)
        else:
            last_lap_ms = None

        session_time = float(data_dict.get("sessionTime") or data_dict.get("session_time") or 0.0)
        track_pos = float(data_dict.get("normalizedCarPosition") or data_dict.get("track_pos") or data_dict.get("trackPosition") or 0.0)

        # Coordinates
        coords = data_dict.get("carCoordinates") or data_dict.get("carCoordH") or data_dict.get("coordinates") or data_dict.get("position")
        coord_x, coord_y, coord_z = 0.0, 0.0, 0.0
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            coord_x = float(coords[0])
            coord_y = float(coords[1])
            coord_z = float(coords[2]) if len(coords) >= 3 else 0.0
        elif isinstance(coords, dict):
            coord_x = float(coords.get("x", 0.0))
            coord_y = float(coords.get("y", 0.0))
            coord_z = float(coords.get("z", 0.0))
        else:
            coord_x = float(data_dict.get("coord_x") or data_dict.get("x") or 0.0)
            coord_y = float(data_dict.get("coord_y") or data_dict.get("y") or 0.0)
            coord_z = float(data_dict.get("coord_z") or data_dict.get("z") or 0.0)

        if coord_z == 0.0 and coord_y != 0.0:
            coord_z = coord_y

        yaw_rate = float(data_dict.get("yawRate") or data_dict.get("yaw_rate") or data_dict.get("yaw") or 0.0)

        # G-Forces
        g_force = data_dict.get("gForce") or data_dict.get("accG") or data_dict.get("g_force")
        g_lat, g_lon = 0.0, 0.0
        if isinstance(g_force, (list, tuple)) and len(g_force) >= 2:
            g_lat = float(g_force[0])
            g_lon = float(g_force[1])
        elif isinstance(g_force, dict):
            g_lat = float(g_force.get("lat") or g_force.get("x") or 0.0)
            g_lon = float(g_force.get("lon") or g_force.get("y") or 0.0)
        else:
            g_lat = float(data_dict.get("g_force_lat") or 0.0)
            g_lon = float(data_dict.get("g_force_lon") or 0.0)

        # Tyres: [FL, FR, RL, RR]
        def extract_4(key_list, fallback_keys):
            val = None
            for k in key_list:
                if k in data_dict:
                    val = data_dict[k]
                    break
            if isinstance(val, (list, tuple)) and len(val) >= 4:
                return [float(x) for x in val[:4]]
            elif isinstance(val, dict):
                return [
                    float(val.get("fl", 0.0)),
                    float(val.get("fr", 0.0)),
                    float(val.get("rl", 0.0)),
                    float(val.get("rr", 0.0))
                ]
            else:
                return [float(data_dict.get(k, 0.0)) for k in fallback_keys]

        tp = extract_4(["tyrePressure", "tyre_pressure", "tyre_pressures"], ["tyre_press_fl", "tyre_press_fr", "tyre_press_rl", "tyre_press_rr"])
        tt = extract_4(["tyreTemp", "tyreCoreTemperature", "tyre_temp", "tyre_temps"], ["tyre_temp_fl", "tyre_temp_fr", "tyre_temp_rl", "tyre_temp_rr"])
        bt = extract_4(["brakeTemp", "brake_temp", "brake_temps"], ["brake_temp_fl", "brake_temp_fr", "brake_temp_rl", "brake_temp_rr"])

        fuel = float(data_dict.get("fuel") or data_dict.get("fuel_liters") or 0.0)
        car = str(data_dict.get("car") or data_dict.get("carModel") or data_dict.get("car_model") or "GT3 Car")
        track = str(data_dict.get("track") or data_dict.get("trackName") or data_dict.get("track_name") or "spa")
        driver = str(data_dict.get("driver") or data_dict.get("driverName") or data_dict.get("driver_name") or "Driver")

        return {
            "speed": speed, "rpm": rpm, "max_rpm": max_rpm, "gear": gear,
            "throttle": throttle, "brake": brake, "clutch": clutch, "steer": steer,
            "lap": lap, "lap_time_ms": lap_time_ms, "last_lap_ms": last_lap_ms, "session_time": session_time,
            "track_pos": track_pos,
            "coord_x": coord_x, "coord_y": coord_y, "coord_z": coord_z,
            "yaw_rate": yaw_rate, "g_force_lat": g_lat, "g_force_lon": g_lon,
            "tyre_press_fl": tp[0], "tyre_press_fr": tp[1], "tyre_press_rl": tp[2], "tyre_press_rr": tp[3],
            "tyre_temp_fl": tt[0], "tyre_temp_fr": tt[1], "tyre_temp_rl": tt[2], "tyre_temp_rr": tt[3],
            "brake_temp_fl": bt[0], "brake_temp_fr": bt[1], "brake_temp_rl": bt[2], "brake_temp_rr": bt[3],
            "fuel": fuel, "car": car, "track": track, "driver": driver,
            "raw": data_dict
        }

    async def handle_packet_dict(self, packet_dict: Dict[str, Any]):
        now_ts = time.time()
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        parsed = self.parse_packet(packet_dict)

        async with self._lock:
            # Check if we should start a new session
            is_idle = (self.last_packet_time > 0 and (now_ts - self.last_packet_time) > SESSION_IDLE_TIMEOUT)
            if self.active_session_id is None or is_idle:
                if self.active_session_id is not None:
                    await self._close_active_session_locked()
                await self._start_new_session_locked(parsed, now_dt)

            self.last_packet_time = now_ts
            self.frame_count += 1
            self.lap_frame_count += 1
            self.lap_speeds.append(parsed["speed"])

            # Lap transition check
            lap_num = parsed["lap"]
            if self.current_lap == 0:
                self.current_lap = lap_num
                self.lap_start_time = now_dt
            elif lap_num > self.current_lap:
                # Completed lap!
                await self._finalize_lap_locked(self.current_lap, parsed, now_dt)
                self.current_lap = lap_num
                self.lap_start_time = now_dt
                self.lap_frame_count = 0
                self.lap_speeds = [parsed["speed"]]

            # Prepare tuple for bulk insertion into DB
            session_id = self.active_session_id
            record = (
                session_id,
                parsed["lap"],
                now_dt,
                parsed["session_time"],
                parsed["lap_time_ms"],
                parsed["track_pos"],
                parsed["speed"],
                parsed["rpm"],
                parsed["max_rpm"],
                parsed["gear"],
                parsed["throttle"],
                parsed["brake"],
                parsed["clutch"],
                parsed["steer"],
                parsed["coord_x"],
                parsed["coord_y"],
                parsed["coord_z"],
                parsed["yaw_rate"],
                parsed["g_force_lat"],
                parsed["g_force_lon"],
                parsed["tyre_press_fl"],
                parsed["tyre_press_fr"],
                parsed["tyre_press_rl"],
                parsed["tyre_press_rr"],
                parsed["tyre_temp_fl"],
                parsed["tyre_temp_fr"],
                parsed["tyre_temp_rl"],
                parsed["tyre_temp_rr"],
                parsed["brake_temp_fl"],
                parsed["brake_temp_fr"],
                parsed["brake_temp_rl"],
                parsed["brake_temp_rr"],
                parsed["fuel"],
                json.dumps(parsed["raw"])
            )

            # Store latest frame for live polling / WebSocket
            self.latest_frame = {
                "type": "telemetry",
                "session_id": session_id,
                "track": parsed["track"],
                "car": parsed["car"],
                "driver": parsed["driver"],
                "timestamp": now_dt.isoformat(),
                "frame_count": self.frame_count,
                "lap": parsed["lap"],
                "lap_time_ms": parsed["lap_time_ms"],
                "last_lap_ms": parsed.get("last_lap_ms"),
                "speed": parsed["speed"],
                "rpm": parsed["rpm"],
                "max_rpm": parsed["max_rpm"],
                "gear": parsed["gear"],
                "throttle": parsed["throttle"],
                "brake": parsed["brake"],
                "clutch": parsed["clutch"],
                "steer": parsed["steer"],
                "track_pos": parsed["track_pos"],
                "coord_x": parsed["coord_x"],
                "coord_y": parsed["coord_y"],
                "coord_z": parsed["coord_z"],
                "g_lat": parsed["g_force_lat"],
                "g_lon": parsed["g_force_lon"],
                "tyre_press": [parsed["tyre_press_fl"], parsed["tyre_press_fr"], parsed["tyre_press_rl"], parsed["tyre_press_rr"]],
                "tyre_temp": [parsed["tyre_temp_fl"], parsed["tyre_temp_fr"], parsed["tyre_temp_rl"], parsed["tyre_temp_rr"]],
                "brake_temp": [parsed["brake_temp_fl"], parsed["brake_temp_fr"], parsed["brake_temp_rl"], parsed["brake_temp_rr"]],
                "fuel": parsed["fuel"],
                "best_lap_time_ms": self.best_lap_time_ms
            }

        # Queue record for bulk insert without holding manager lock
        try:
            self.queue.put_nowait(record)
        except asyncio.QueueFull:
            logger.warning("Telemetry frame queue full, dropping frame.")

        # Broadcast live frame asynchronously
        if self.live_clients:
            asyncio.create_task(self.broadcast_live(self.latest_frame))

    async def handle_packet(self, raw_data: bytes):
        try:
            packet_dict = json.loads(raw_data.decode("utf-8", errors="replace"))
        except Exception as e:
            logger.debug(f"Invalid JSON packet received: {e}")
            return
        await self.handle_packet_dict(packet_dict)

    async def _start_new_session_locked(self, parsed: Dict[str, Any], start_dt: datetime.datetime):
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO sessions (track, car, driver, started_at, is_active, frame_count, duration_seconds)
                VALUES ($1, $2, $3, $4, TRUE, 0, 0.0)
                RETURNING id;
            """, parsed["track"], parsed["car"], parsed["driver"], start_dt)
            self.active_session_id = row["id"]

        self.session_started_at = start_dt
        self.frame_count = 0
        self.current_lap = parsed["lap"]
        self.lap_frame_count = 0
        self.lap_speeds = []
        self.lap_start_time = start_dt
        self.best_lap_time_ms = None
        self.total_laps = 0
        logger.info(f"Auto-started new session #{self.active_session_id} on track '{parsed['track']}' ({parsed['car']})")

    async def _finalize_lap_locked(self, lap_num: int, parsed: Dict[str, Any], end_dt: datetime.datetime):
        if not self.active_session_id:
            return
        
        # Calculate lap time: prefer last_lap_ms or lastLapTimeMS before falling back to lap_time_ms
        raw_last = (
            parsed.get("last_lap_ms")
            or (parsed.get("raw") or {}).get("last_lap_ms")
            or (parsed.get("raw") or {}).get("lastLapTimeMS")
            or (parsed.get("raw") or {}).get("lastLap")
            or parsed.get("lap_time_ms")
            or 0
        )
        if isinstance(raw_last, float) and raw_last < 3600.0:
            lap_time_ms = int(raw_last * 1000)
        else:
            lap_time_ms = int(raw_last)

        if lap_time_ms <= 0 and self.lap_start_time:
            delta = (end_dt - self.lap_start_time).total_seconds()
            lap_time_ms = int(delta * 1000)

        max_spd = max(self.lap_speeds) if self.lap_speeds else 0.0
        avg_spd = sum(self.lap_speeds) / len(self.lap_speeds) if self.lap_speeds else 0.0

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            # Upsert into laps table
            await conn.execute("""
                INSERT INTO laps (session_id, lap_number, lap_time_ms, max_speed, avg_speed, frame_count, started_at, ended_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (session_id, lap_number) DO UPDATE SET
                    lap_time_ms = EXCLUDED.lap_time_ms,
                    max_speed = EXCLUDED.max_speed,
                    avg_speed = EXCLUDED.avg_speed,
                    frame_count = EXCLUDED.frame_count,
                    ended_at = EXCLUDED.ended_at;
            """, self.active_session_id, lap_num, lap_time_ms, max_spd, avg_spd, self.lap_frame_count, self.lap_start_time, end_dt)

            self.total_laps += 1
            if lap_time_ms > 0 and (self.best_lap_time_ms is None or lap_time_ms < self.best_lap_time_ms):
                self.best_lap_time_ms = lap_time_ms

            await conn.execute("""
                UPDATE sessions SET
                    total_laps = $1,
                    best_lap_time_ms = $2,
                    updated_at = NOW()
                WHERE id = $3;
            """, self.total_laps, self.best_lap_time_ms, self.active_session_id)

        logger.info(f"Recorded Lap #{lap_num} for session #{self.active_session_id}: {lap_time_ms / 1000:.3f}s (Top Speed: {max_spd:.1f} km/h)")

    async def _close_active_session_locked(self):
        if not self.active_session_id:
            return
        
        session_id = self.active_session_id
        end_dt = datetime.datetime.now(datetime.timezone.utc)
        duration = (end_dt - self.session_started_at).total_seconds() if self.session_started_at else 0.0

        # Also finalize current lap if it has frames
        if self.current_lap > 0 and self.lap_frame_count > 10:
            lap_time_ms = int((end_dt - self.lap_start_time).total_seconds() * 1000) if self.lap_start_time else 0
            max_spd = max(self.lap_speeds) if self.lap_speeds else 0.0
            avg_spd = sum(self.lap_speeds) / len(self.lap_speeds) if self.lap_speeds else 0.0
            
            pool = await get_db_pool()
            async with pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO laps (session_id, lap_number, lap_time_ms, max_speed, avg_speed, frame_count, started_at, ended_at)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (session_id, lap_number) DO UPDATE SET
                        lap_time_ms = EXCLUDED.lap_time_ms,
                        max_speed = EXCLUDED.max_speed,
                        avg_speed = EXCLUDED.avg_speed,
                        frame_count = EXCLUDED.frame_count,
                        ended_at = EXCLUDED.ended_at;
                """, session_id, self.current_lap, lap_time_ms, max_spd, avg_spd, self.lap_frame_count, self.lap_start_time, end_dt)

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sessions SET
                    ended_at = $1,
                    is_active = FALSE,
                    frame_count = $2,
                    duration_seconds = $3,
                    updated_at = NOW()
                WHERE id = $4;
            """, end_dt, self.frame_count, duration, session_id)

        logger.info(f"Auto-closed session #{session_id} (Duration: {duration:.1f}s, Frames: {self.frame_count})")
        self.active_session_id = None
        self.last_packet_time = 0.0

    async def close_active_session(self):
        async with self._lock:
            await self._close_active_session_locked()

    async def _flush_queue(self):
        records = []
        while not self.queue.empty():
            try:
                records.append(self.queue.get_nowait())
                self.queue.task_done()
            except asyncio.QueueEmpty:
                break

        if not records:
            return

        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.copy_records_to_table("telemetry_frames", records=records, columns=COLS)

    async def _batch_flusher(self):
        """Continuously write queued telemetry frames to PostgreSQL in batches."""
        last_meta_update = time.time()
        while self.running:
            try:
                records = []
                # Wait for at least one item or timeout
                try:
                    first = await asyncio.wait_for(self.queue.get(), timeout=0.1)
                    records.append(first)
                    self.queue.task_done()
                except asyncio.TimeoutError:
                    pass

                # Drain up to 200 items
                while len(records) < 200 and not self.queue.empty():
                    try:
                        records.append(self.queue.get_nowait())
                        self.queue.task_done()
                    except asyncio.QueueEmpty:
                        break

                if records:
                    pool = await get_db_pool()
                    async with pool.acquire() as conn:
                        await conn.copy_records_to_table("telemetry_frames", records=records, columns=COLS)

                # Periodically update session frame count & duration in DB
                now = time.time()
                if now - last_meta_update > 2.0 and self.active_session_id is not None:
                    last_meta_update = now
                    async with self._lock:
                        if self.active_session_id and self.session_started_at:
                            dur = (datetime.datetime.now(datetime.timezone.utc) - self.session_started_at).total_seconds()
                            pool = await get_db_pool()
                            async with pool.acquire() as conn:
                                await conn.execute("""
                                    UPDATE sessions SET
                                        frame_count = $1,
                                        duration_seconds = $2,
                                        updated_at = NOW()
                                    WHERE id = $3 AND is_active = TRUE;
                                """, self.frame_count, dur, self.active_session_id)

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in batch flusher: {e}", exc_info=True)
                await asyncio.sleep(0.5)

    async def _idle_checker(self):
        """Checks every 1s if active session timed out after ~30s of silence."""
        while self.running:
            try:
                await asyncio.sleep(1.0)
                now_ts = time.time()
                if self.active_session_id is not None and self.last_packet_time > 0:
                    if (now_ts - self.last_packet_time) > SESSION_IDLE_TIMEOUT:
                        logger.info(f"Session idle timeout ({SESSION_IDLE_TIMEOUT}s) reached with no UDP packets. Closing session.")
                        await self.close_active_session()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in idle checker: {e}", exc_info=True)

class TelemetryUDPProtocol(asyncio.DatagramProtocol):
    def __init__(self, manager: TelemetryManager):
        self.manager = manager
        self.transport = None

    def connection_made(self, transport):
        self.transport = transport
        logger.info(f"UDP listener bound to {UDP_HOST}:{UDP_PORT}")

    def datagram_received(self, data: bytes, addr):
        # Fire-and-forget processing into asyncio event loop
        asyncio.create_task(self.manager.handle_packet(data))

    def error_received(self, exc):
        logger.warning(f"UDP error received: {exc}")

telemetry_manager = TelemetryManager()
