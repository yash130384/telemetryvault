import json
import logging
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, Query, WebSocket, WebSocketDisconnect
from server.db import get_db_pool
from server.ingest import telemetry_manager
from server.config import UDP_PORT, UDP_HOST

logger = logging.getLogger("telemetryvault.api")

router = APIRouter(prefix="/api")

@router.get("/health")
async def health_check():
    pool = await get_db_pool()
    db_ok = False
    try:
        async with pool.acquire() as conn:
            val = await conn.fetchval("SELECT 1;")
            db_ok = (val == 1)
    except Exception as e:
        logger.error(f"DB health check error: {e}")

    return {
        "status": "online",
        "database": "connected" if db_ok else "error",
        "udp_listener": {
            "host": UDP_HOST,
            "port": UDP_PORT
        },
        "active_session": {
            "session_id": telemetry_manager.active_session_id,
            "is_active": telemetry_manager.active_session_id is not None,
            "frame_count": telemetry_manager.frame_count,
            "current_lap": telemetry_manager.current_lap,
            "last_packet_time": telemetry_manager.last_packet_time
        }
    }

@router.get("/tracks")
async def list_tracks():
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT track, COUNT(*) as session_count, MAX(started_at) as last_session
            FROM sessions
            GROUP BY track
            ORDER BY last_session DESC;
        """)
        return [dict(r) for r in rows]

@router.get("/sessions")
async def list_sessions(
    track: Optional[str] = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0)
):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if track:
            rows = await conn.fetch("""
                SELECT id, track, car, driver, started_at, ended_at, is_active,
                       frame_count, duration_seconds, total_laps, best_lap_time_ms, created_at
                FROM sessions
                WHERE track = $1
                ORDER BY started_at DESC
                LIMIT $2 OFFSET $3;
            """, track, limit, offset)
        else:
            rows = await conn.fetch("""
                SELECT id, track, car, driver, started_at, ended_at, is_active,
                       frame_count, duration_seconds, total_laps, best_lap_time_ms, created_at
                FROM sessions
                ORDER BY started_at DESC
                LIMIT $1 OFFSET $2;
            """, limit, offset)

        return [dict(r) for r in rows]

@router.get("/sessions/{session_id}")
async def get_session(session_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        session = await conn.fetchrow("""
            SELECT id, track, car, driver, started_at, ended_at, is_active,
                   frame_count, duration_seconds, total_laps, best_lap_time_ms, created_at
            FROM sessions
            WHERE id = $1;
        """, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")

        laps = await conn.fetch("""
            SELECT id, session_id, lap_number, lap_time_ms, is_valid,
                   started_at, ended_at, sector1_ms, sector2_ms, sector3_ms,
                   max_speed, avg_speed, frame_count
            FROM laps
            WHERE session_id = $1
            ORDER BY lap_number ASC;
        """, session_id)

        res = dict(session)
        res["laps"] = [dict(l) for l in laps]
        return res

@router.get("/sessions/{session_id}/laps")
async def get_session_laps(session_id: int):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        laps = await conn.fetch("""
            SELECT id, session_id, lap_number, lap_time_ms, is_valid,
                   started_at, ended_at, sector1_ms, sector2_ms, sector3_ms,
                   max_speed, avg_speed, frame_count
            FROM laps
            WHERE session_id = $1
            ORDER BY lap_number ASC;
        """, session_id)
        return [dict(l) for l in laps]

@router.get("/sessions/{session_id}/telemetry")
async def get_telemetry(
    session_id: int,
    lap_number: Optional[int] = None,
    step: int = Query(default=1, ge=1, le=50),
    limit: int = Query(default=15000, ge=10, le=50000)
):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        if lap_number is not None:
            rows = await conn.fetch("""
                SELECT id, lap_number, timestamp, session_time, lap_time_ms, track_pos,
                       speed, rpm, max_rpm, gear, throttle, brake, steer,
                       coord_x, coord_y, coord_z, g_force_lat, g_force_lon,
                       tyre_press_fl, tyre_press_fr, tyre_press_rl, tyre_press_rr,
                       tyre_temp_fl, tyre_temp_fr, tyre_temp_rl, tyre_temp_rr,
                       brake_temp_fl, brake_temp_fr, brake_temp_rl, brake_temp_rr, fuel
                FROM (
                    SELECT *, ROW_NUMBER() OVER (ORDER BY timestamp ASC) as rn
                    FROM telemetry_frames
                    WHERE session_id = $1 AND lap_number = $2
                ) sub
                WHERE rn % $3 = 0
                ORDER BY timestamp ASC
                LIMIT $4;
            """, session_id, lap_number, step, limit)
        else:
            rows = await conn.fetch("""
                SELECT id, lap_number, timestamp, session_time, lap_time_ms, track_pos,
                       speed, rpm, max_rpm, gear, throttle, brake, steer,
                       coord_x, coord_y, coord_z, g_force_lat, g_force_lon,
                       tyre_press_fl, tyre_press_fr, tyre_press_rl, tyre_press_rr,
                       tyre_temp_fl, tyre_temp_fr, tyre_temp_rl, tyre_temp_rr,
                       brake_temp_fl, brake_temp_fr, brake_temp_rl, brake_temp_rr, fuel
                FROM (
                    SELECT *, ROW_NUMBER() OVER (ORDER BY timestamp ASC) as rn
                    FROM telemetry_frames
                    WHERE session_id = $1
                ) sub
                WHERE rn % $2 = 0
                ORDER BY timestamp ASC
                LIMIT $3;
            """, session_id, step, limit)

        return [dict(r) for r in rows]

@router.get("/sessions/{session_id}/trackmap")
async def get_trackmap(session_id: int, lap_number: Optional[int] = None):
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        # If lap_number not specified, pick best lap or first lap with frames
        if lap_number is None:
            best_lap = await conn.fetchval("""
                SELECT lap_number FROM laps
                WHERE session_id = $1 AND lap_time_ms > 0
                ORDER BY lap_time_ms ASC LIMIT 1;
            """, session_id)
            if best_lap is not None:
                lap_number = best_lap
            else:
                lap_number = await conn.fetchval("""
                    SELECT lap_number FROM telemetry_frames
                    WHERE session_id = $1 LIMIT 1;
                """, session_id) or 1

        rows = await conn.fetch("""
            SELECT coord_x, coord_z, coord_y, speed, throttle, brake, gear, track_pos, lap_time_ms
            FROM telemetry_frames
            WHERE session_id = $1 AND lap_number = $2
            ORDER BY timestamp ASC;
        """, session_id, lap_number)

        # Downsample if too dense to keep map snappy
        data = [dict(r) for r in rows]
        if len(data) > 1500:
            step = max(1, len(data) // 1500)
            data = data[::step]

        return {
            "session_id": session_id,
            "lap_number": lap_number,
            "points": data
        }

@router.get("/sessions/{session_id}/compare")
async def compare_laps(
    session_id: int,
    lap1: int = Query(..., description="First lap number (e.g. Best Lap)"),
    lap2: int = Query(..., description="Second lap number (e.g. Selected Lap)"),
    samples: int = Query(default=400, ge=50, le=2000)
):
    """
    Interpolates both laps along normalized track position (0.0 to 1.0)
    to calculate speed delta, throttle/brake deltas, and time delta (Delta-T in seconds).
    """
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        rows1 = await conn.fetch("""
            SELECT track_pos, lap_time_ms, speed, throttle, brake, gear, steer, rpm
            FROM telemetry_frames
            WHERE session_id = $1 AND lap_number = $2
            ORDER BY track_pos ASC, timestamp ASC;
        """, session_id, lap1)

        rows2 = await conn.fetch("""
            SELECT track_pos, lap_time_ms, speed, throttle, brake, gear, steer, rpm
            FROM telemetry_frames
            WHERE session_id = $1 AND lap_number = $2
            ORDER BY track_pos ASC, timestamp ASC;
        """, session_id, lap2)

    if not rows1 or not rows2:
        raise HTTPException(status_code=404, detail="One or both laps have no telemetry frames")

    # Interpolate along samples normalized points: 0.0, 1/samples, ..., 1.0
    def resample(frames):
        # Filter strictly ascending track_pos
        cleaned = []
        last_pos = -1.0
        for f in frames:
            pos = float(f["track_pos"])
            if pos >= last_pos:
                cleaned.append(f)
                last_pos = pos
        return cleaned

    c1 = resample(rows1)
    c2 = resample(rows2)

    def sample_at(frames, pos):
        # Binary search / linear scan
        if not frames:
            return None
        if pos <= frames[0]["track_pos"]:
            return frames[0]
        if pos >= frames[-1]["track_pos"]:
            return frames[-1]
        
        # Linear search since samples are ascending
        for i in range(len(frames) - 1):
            p0 = frames[i]["track_pos"]
            p1 = frames[i+1]["track_pos"]
            if p0 <= pos <= p1:
                t = (pos - p0) / (p1 - p0 + 1e-7)
                return {
                    "track_pos": pos,
                    "lap_time_ms": frames[i]["lap_time_ms"] + t * (frames[i+1]["lap_time_ms"] - frames[i]["lap_time_ms"]),
                    "speed": frames[i]["speed"] + t * (frames[i+1]["speed"] - frames[i]["speed"]),
                    "throttle": frames[i]["throttle"] + t * (frames[i+1]["throttle"] - frames[i]["throttle"]),
                    "brake": frames[i]["brake"] + t * (frames[i+1]["brake"] - frames[i]["brake"]),
                    "gear": frames[i+1]["gear"] if t > 0.5 else frames[i]["gear"],
                    "steer": frames[i]["steer"] + t * (frames[i+1]["steer"] - frames[i]["steer"]),
                    "rpm": int(frames[i]["rpm"] + t * (frames[i+1]["rpm"] - frames[i]["rpm"]))
                }
        return frames[-1]

    aligned = []
    for i in range(samples):
        pos = i / float(samples - 1)
        s1 = sample_at(c1, pos)
        s2 = sample_at(c2, pos)
        if s1 and s2:
            time_delta_sec = (s2["lap_time_ms"] - s1["lap_time_ms"]) / 1000.0
            aligned.append({
                "pos": round(pos, 4),
                "speed1": round(s1["speed"], 1),
                "speed2": round(s2["speed"], 1),
                "throttle1": round(s1["throttle"], 2),
                "throttle2": round(s2["throttle"], 2),
                "brake1": round(s1["brake"], 2),
                "brake2": round(s2["brake"], 2),
                "gear1": s1["gear"],
                "gear2": s2["gear"],
                "steer1": round(s1["steer"], 1),
                "steer2": round(s2["steer"], 1),
                "time1_s": round(s1["lap_time_ms"] / 1000.0, 3),
                "time2_s": round(s2["lap_time_ms"] / 1000.0, 3),
                "delta_t_s": round(time_delta_sec, 3)
            })

    return {
        "session_id": session_id,
        "lap1": lap1,
        "lap2": lap2,
        "samples_count": len(aligned),
        "data": aligned
    }

@router.post("/sessions/{session_id}/close")
async def close_session(session_id: int):
    if telemetry_manager.active_session_id == session_id:
        await telemetry_manager.close_active_session()
        return {"status": "closed", "session_id": session_id}
    else:
        pool = await get_db_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE sessions SET is_active = FALSE, ended_at = NOW(), updated_at = NOW()
                WHERE id = $1;
            """, session_id)
        return {"status": "marked_closed", "session_id": session_id}

@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int):
    if telemetry_manager.active_session_id == session_id:
        await telemetry_manager.close_active_session()
    pool = await get_db_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM sessions WHERE id = $1;", session_id)
    return {"status": "deleted", "session_id": session_id}

@router.post("/telemetry/inject")
async def inject_frame(frame: Dict[str, Any]):
    raw_bytes = json.dumps(frame).encode("utf-8")
    await telemetry_manager.handle_packet(raw_bytes)
    return {"status": "accepted"}
