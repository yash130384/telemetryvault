import math
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import logging

logger = logging.getLogger("telemetryvault.analysis")


def format_lap_time(ms: Optional[int]) -> str:
    """Formats lap time in ms to MM:SS.mmm format."""
    if ms is None or ms <= 0:
        return "--:--.---"
    total_sec = ms / 1000.0
    mins = int(total_sec // 60)
    rem_sec = total_sec % 60
    return f"{mins}:{rem_sec:06.3f}"


def format_sector_time(ms: Optional[int]) -> str:
    """Formats sector time in ms (e.g. 34.210s or 1:04.210)."""
    if ms is None or ms <= 0:
        return "--.---s"
    if ms < 60000:
        return f"{ms / 1000.0:.3f}s"
    return format_lap_time(ms)


def get_track_sector_boundaries(track_name: str) -> Dict[str, float]:
    """
    Returns normalized track spline positions (0.0 to 1.0) for sector boundaries.
    For Mount Panorama / Bathurst:
      S1: 0.0 -> 0.285 (Start/Finish to The Cutting)
      S2: 0.285 -> 0.655 (Mountain Section to Forrest's Elbow)
      S3: 0.655 -> 1.0 (Conrod Straight to Start/Finish)
    For all other tracks:
      S1: 0.0 -> 0.333
      S2: 0.333 -> 0.666
      S3: 0.666 -> 1.0
    """
    track_lower = (track_name or "").lower().strip()
    if "bathurst" in track_lower or "mount panorama" in track_lower:
        return {"s1": 0.285, "s2": 0.655, "s3": 1.0}
    return {"s1": 0.333, "s2": 0.666, "s3": 1.0}


KNOWN_TRACK_CORNERS: Dict[str, List[Dict[str, Any]]] = {
    "bathurst": [
        {"name": "Hell Corner (T1)", "min_pos": 0.035, "max_pos": 0.085},
        {"name": "Griffin's Bend (T2)", "min_pos": 0.130, "max_pos": 0.180},
        {"name": "The Cutting (T4)", "min_pos": 0.240, "max_pos": 0.295},
        {"name": "Sulman Park (T10)", "min_pos": 0.350, "max_pos": 0.410},
        {"name": "Skyline (T13)", "min_pos": 0.450, "max_pos": 0.500},
        {"name": "The Dipper (T18)", "min_pos": 0.520, "max_pos": 0.580},
        {"name": "Forrest's Elbow (T21)", "min_pos": 0.610, "max_pos": 0.670},
        {"name": "The Chase (T22)", "min_pos": 0.800, "max_pos": 0.880},
        {"name": "Murray's Corner (T23)", "min_pos": 0.930, "max_pos": 0.990},
    ],
    "spa": [
        {"name": "La Source (T1)", "min_pos": 0.030, "max_pos": 0.080},
        {"name": "Les Combes (T5/6)", "min_pos": 0.270, "max_pos": 0.340},
        {"name": "Bruxelles (T8)", "min_pos": 0.410, "max_pos": 0.470},
        {"name": "Speakers Corner (T9)", "min_pos": 0.480, "max_pos": 0.530},
        {"name": "Pouhon (T10/11)", "min_pos": 0.560, "max_pos": 0.630},
        {"name": "Fagnes (T14/15)", "min_pos": 0.690, "max_pos": 0.750},
        {"name": "Campus / Stavelot (T16)", "min_pos": 0.780, "max_pos": 0.840},
        {"name": "Bus Stop Chicane (T18/19)", "min_pos": 0.910, "max_pos": 0.980},
    ]
}


def get_known_corners(track_name: str) -> List[Dict[str, Any]]:
    """Returns predefined corners for known tracks if available."""
    track_lower = (track_name or "").lower().strip()
    if "bathurst" in track_lower or "mount panorama" in track_lower:
        return KNOWN_TRACK_CORNERS["bathurst"]
    if "spa" in track_lower:
        return KNOWN_TRACK_CORNERS["spa"]
    return []


def calculate_lap_sectors(
    frames: List[Dict[str, Any]],
    s1_end: float,
    s2_end: float,
    lap_time_ms: Optional[int] = None
) -> Dict[str, Optional[int]]:
    """
    Calculates sector times in ms for a single lap by interpolating frame times
    at normalized track boundaries s1_end and s2_end.
    Ensures S1 + S2 + S3 == lap_time_ms if lap_time_ms is provided and positive.
    """
    if not frames or len(frames) < 3:
        return {"sector1_ms": None, "sector2_ms": None, "sector3_ms": None}

    # Sort frames chronologically or by track_pos
    sorted_frames = sorted(
        frames,
        key=lambda f: (
            f.get("lap_time_ms") or 0,
            f.get("timestamp") or 0,
            f.get("track_pos") or 0.0
        )
    )

    # Helper to extract time in milliseconds for a frame
    t0_dt = sorted_frames[0].get("timestamp")
    has_lap_time = any((f.get("lap_time_ms") or 0) > 0 for f in sorted_frames)

    def get_frame_time_ms(f: Dict[str, Any]) -> float:
        if has_lap_time and (f.get("lap_time_ms") is not None):
            return float(f["lap_time_ms"])
        if f.get("session_time") is not None:
            return float(f["session_time"]) * 1000.0
        if f.get("timestamp") is not None and isinstance(f["timestamp"], datetime) and t0_dt:
            return (f["timestamp"] - t0_dt).total_seconds() * 1000.0
        return 0.0

    # Ensure track_pos is monotonic or extract boundary crossing times
    def find_time_at_pos(target_pos: float) -> Optional[float]:
        # Linear search for target crossing
        for i in range(len(sorted_frames) - 1):
            p0 = float(sorted_frames[i].get("track_pos") or 0.0)
            p1 = float(sorted_frames[i + 1].get("track_pos") or 0.0)
            if p0 <= target_pos <= p1:
                t0 = get_frame_time_ms(sorted_frames[i])
                t1 = get_frame_time_ms(sorted_frames[i + 1])
                denom = p1 - p0
                factor = (target_pos - p0) / (denom + 1e-7) if denom > 0 else 0.0
                return t0 + factor * (t1 - t0)

        # Fallback: check closest frame if within 0.05
        closest = min(sorted_frames, key=lambda f: abs((f.get("track_pos") or 0.0) - target_pos))
        if abs((closest.get("track_pos") or 0.0) - target_pos) < 0.05:
            return get_frame_time_ms(closest)

        return None

    t_s1 = find_time_at_pos(s1_end)
    t_s2 = find_time_at_pos(s2_end)

    if t_s1 is None or t_s2 is None:
        return {"sector1_ms": None, "sector2_ms": None, "sector3_ms": None}

    # Start time
    t_start = get_frame_time_ms(sorted_frames[0])
    if t_s1 < t_start or t_s2 < t_s1:
        return {"sector1_ms": None, "sector2_ms": None, "sector3_ms": None}

    s1_ms = int(round(t_s1 - t_start))
    s2_ms = int(round(t_s2 - t_s1))

    if lap_time_ms and lap_time_ms > 0:
        s3_ms = lap_time_ms - s1_ms - s2_ms
    else:
        t_end = get_frame_time_ms(sorted_frames[-1])
        s3_ms = int(round(t_end - t_s2))

    if s1_ms <= 0 or s2_ms <= 0 or s3_ms <= 0:
        return {"sector1_ms": None, "sector2_ms": None, "sector3_ms": None}

    return {
        "sector1_ms": s1_ms,
        "sector2_ms": s2_ms,
        "sector3_ms": s3_ms
    }


def calculate_optimal_lap(laps: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Computes theoretical best time (optimal lap) by taking the minimum
    valid sector 1, sector 2, and sector 3 across the entire session.
    """
    valid_laps = [
        l for l in laps
        if l.get("is_valid", True) is not False and (l.get("lap_time_ms") or 0) > 0
    ]

    s1_candidates = [
        (l["sector1_ms"], l["lap_number"])
        for l in valid_laps
        if l.get("sector1_ms") and l["sector1_ms"] > 0
    ]
    s2_candidates = [
        (l["sector2_ms"], l["lap_number"])
        for l in valid_laps
        if l.get("sector2_ms") and l["sector2_ms"] > 0
    ]
    s3_candidates = [
        (l["sector3_ms"], l["lap_number"])
        for l in valid_laps
        if l.get("sector3_ms") and l["sector3_ms"] > 0
    ]

    best_s1, best_s1_lap = min(s1_candidates, key=lambda x: x[0]) if s1_candidates else (None, None)
    best_s2, best_s2_lap = min(s2_candidates, key=lambda x: x[0]) if s2_candidates else (None, None)
    best_s3, best_s3_lap = min(s3_candidates, key=lambda x: x[0]) if s3_candidates else (None, None)

    optimal_lap_ms = (best_s1 + best_s2 + best_s3) if (best_s1 and best_s2 and best_s3) else None

    # Actual best lap
    lap_time_candidates = [
        (l["lap_time_ms"], l["lap_number"])
        for l in valid_laps
    ]
    best_lap_ms, best_lap_number = min(lap_time_candidates, key=lambda x: x[0]) if lap_time_candidates else (None, None)

    potential_gain_ms = (best_lap_ms - optimal_lap_ms) if (best_lap_ms and optimal_lap_ms) else None
    if potential_gain_ms is not None and potential_gain_ms < 0:
        potential_gain_ms = 0

    return {
        "best_s1_ms": best_s1,
        "best_s1_lap": best_s1_lap,
        "best_s2_ms": best_s2,
        "best_s2_lap": best_s2_lap,
        "best_s3_ms": best_s3,
        "best_s3_lap": best_s3_lap,
        "optimal_lap_ms": optimal_lap_ms,
        "best_lap_ms": best_lap_ms,
        "best_lap_number": best_lap_number,
        "potential_gain_ms": potential_gain_ms
    }


def analyze_braking_zones(
    frames_best: List[Dict[str, Any]],
    frames_compare: Optional[List[Dict[str, Any]]] = None,
    track_name: str = ""
) -> List[Dict[str, Any]]:
    """
    Identifies and analyzes braking and corner apex zones on the best lap,
    comparing entry speeds, apex speeds, and braking distance/duration
    against a comparison lap.
    """
    if not frames_best or len(frames_best) < 10:
        return []

    # Sort frames along track position
    best_sorted = sorted(frames_best, key=lambda f: float(f.get("track_pos") or 0.0))
    compare_sorted = sorted(frames_compare, key=lambda f: float(f.get("track_pos") or 0.0)) if frames_compare else []

    known_corners = get_known_corners(track_name)
    zones_to_analyze: List[Dict[str, Any]] = []

    if known_corners:
        zones_to_analyze = known_corners
    else:
        # Dynamic corner detection: scan for significant local speed minima (speed drop >= 18 km/h)
        window_size = 15
        n = len(best_sorted)
        detected_minima = []
        for i in range(window_size, n - window_size, 5):
            curr_speed = float(best_sorted[i].get("speed") or 0.0)
            # Check if local minimum
            is_min = True
            for w in range(i - window_size, i + window_size):
                if float(best_sorted[w].get("speed") or 0.0) < curr_speed:
                    is_min = False
                    break
            if is_min:
                pos = float(best_sorted[i].get("track_pos") or 0.0)
                # Check speed drop from entry
                entry_w = max(float(best_sorted[w].get("speed") or 0.0) for w in range(max(0, i - window_size * 2), i))
                if entry_w - curr_speed >= 18.0:
                    detected_minima.append({
                        "name": f"Corner @ {int(pos * 100)}%",
                        "min_pos": max(0.0, pos - 0.03),
                        "max_pos": min(1.0, pos + 0.03)
                    })

        # Merge closely adjacent detected zones
        merged: List[Dict[str, Any]] = []
        for d in detected_minima:
            if not merged or (d["min_pos"] - merged[-1]["max_pos"]) > 0.04:
                merged.append(d)
        for idx, m in enumerate(merged):
            m["name"] = f"Turn {idx + 1} ({int((m['min_pos'] + m['max_pos']) / 2 * 100)}%)"
        zones_to_analyze = merged

    results: List[Dict[str, Any]] = []

    for corner in zones_to_analyze:
        c_min = corner["min_pos"] - 0.02
        c_max = corner["max_pos"] + 0.01

        # Extract frames in corner window for best lap
        c_frames = [f for f in best_sorted if c_min <= float(f.get("track_pos") or 0.0) <= c_max]
        if not c_frames or len(c_frames) < 3:
            continue

        # Find apex (minimum speed)
        apex_frame = min(c_frames, key=lambda f: float(f.get("speed") or 0.0))
        apex_speed = float(apex_frame.get("speed") or 0.0)
        apex_pos = float(apex_frame.get("track_pos") or 0.0)

        # Find entry (maximum speed before apex within window)
        frames_before_apex = [f for f in c_frames if float(f.get("track_pos") or 0.0) <= apex_pos]
        if not frames_before_apex:
            entry_frame = c_frames[0]
        else:
            entry_frame = max(frames_before_apex, key=lambda f: float(f.get("speed") or 0.0))

        entry_speed = float(entry_frame.get("speed") or 0.0)
        speed_drop = entry_speed - apex_speed

        # Skip corners with no noticeable deceleration
        if speed_drop < 8.0:
            continue

        # Calculate braking distance between entry and apex
        entry_idx = best_sorted.index(entry_frame) if entry_frame in best_sorted else 0
        apex_idx = best_sorted.index(apex_frame) if apex_frame in best_sorted else len(best_sorted) - 1

        dist_m = 0.0
        duration_s = 0.0

        if entry_idx < apex_idx:
            for k in range(entry_idx, apex_idx):
                f0 = best_sorted[k]
                f1 = best_sorted[k + 1]
                x0, z0 = float(f0.get("coord_x") or 0.0), float(f0.get("coord_z") or f0.get("coord_y") or 0.0)
                x1, z1 = float(f1.get("coord_x") or 0.0), float(f1.get("coord_z") or f1.get("coord_y") or 0.0)
                step_dist = math.hypot(x1 - x0, z1 - z0)
                if step_dist < 0.1 or step_dist > 80.0:
                    # Fallback to speed integration
                    avg_v = (float(f0.get("speed") or 0.0) + float(f1.get("speed") or 0.0)) / 2.0 / 3.6
                    # Approx dt from lap time or 0.05 (20 Hz)
                    t0 = float(f0.get("lap_time_ms") or 0.0)
                    t1 = float(f1.get("lap_time_ms") or 0.0)
                    dt = (t1 - t0) / 1000.0 if t1 > t0 else 0.05
                    step_dist = avg_v * dt
                dist_m += step_dist

            t_entry = float(entry_frame.get("lap_time_ms") or 0.0)
            t_apex = float(apex_frame.get("lap_time_ms") or 0.0)
            if t_apex > t_entry:
                duration_s = (t_apex - t_entry) / 1000.0
            else:
                duration_s = max(0.2, dist_m / (max(20.0, (entry_speed + apex_speed) / 2.0) / 3.6))

        # Compare with comparison lap if available
        comp_entry_speed = None
        comp_apex_speed = None
        delta_apex = None

        if compare_sorted:
            # Find comparison frames around apex_pos
            comp_window = [
                f for f in compare_sorted
                if abs(float(f.get("track_pos") or 0.0) - apex_pos) <= 0.04
            ]
            if comp_window:
                comp_apex_f = min(comp_window, key=lambda f: float(f.get("speed") or 0.0))
                comp_apex_speed = round(float(comp_apex_f.get("speed") or 0.0), 1)
                comp_before = [f for f in comp_window if float(f.get("track_pos") or 0.0) <= float(comp_apex_f.get("track_pos") or 0.0)]
                if comp_before:
                    comp_entry_f = max(comp_before, key=lambda f: float(f.get("speed") or 0.0))
                    comp_entry_speed = round(float(comp_entry_f.get("speed") or 0.0), 1)
                delta_apex = round(apex_speed - comp_apex_speed, 1)

        results.append({
            "corner": corner["name"],
            "track_pos": round(apex_pos, 3),
            "entry_speed": round(entry_speed, 1),
            "apex_speed": round(apex_speed, 1),
            "braking_distance_m": round(dist_m, 1),
            "braking_duration_s": round(duration_s, 2),
            "compare_entry_speed": comp_entry_speed,
            "compare_apex_speed": comp_apex_speed,
            "delta_apex_speed": delta_apex
        })

    return results


def calculate_stint_consistency(
    laps: List[Dict[str, Any]],
    best_lap_time_ms: Optional[int] = None
) -> Dict[str, Any]:
    """
    Analyzes stint pace, filters out inlap/outlap outliers, and computes
    stint consistency score (%) and standard deviation.
    """
    valid_laps = [
        l for l in laps
        if (l.get("lap_time_ms") or 0) > 0 and l.get("is_valid", True) is not False
    ]

    total_laps = len(laps)
    if not valid_laps:
        return {
            "total_laps": total_laps,
            "flying_laps_count": 0,
            "average_pace_ms": None,
            "std_dev_s": 0.0,
            "consistency_score": 0.0,
            "consistency_rating": "No Data"
        }

    benchmark_ms = best_lap_time_ms or min(l["lap_time_ms"] for l in valid_laps)

    # Filter out inlap / outlap outliers (> 120% of benchmark)
    flying = [l for l in valid_laps if l["lap_time_ms"] <= benchmark_ms * 1.20]

    # If first lap is an outlap (> 108% of benchmark) and multiple laps exist, filter it out
    if len(flying) >= 3 and flying[0].get("lap_number") == 1 and flying[0]["lap_time_ms"] > benchmark_ms * 1.08:
        flying = flying[1:]

    # Fallback if over-filtered
    if not flying:
        flying = valid_laps

    times = [l["lap_time_ms"] for l in flying]
    avg_pace_ms = int(round(sum(times) / len(times)))

    if len(times) <= 1:
        return {
            "total_laps": total_laps,
            "flying_laps_count": len(times),
            "average_pace_ms": avg_pace_ms,
            "std_dev_s": 0.0,
            "consistency_score": 100.0,
            "consistency_rating": "Baseline Lap"
        }

    variance = sum((t - avg_pace_ms) ** 2 for t in times) / len(times)
    std_dev_ms = math.sqrt(variance)
    std_dev_s = round(std_dev_ms / 1000.0, 3)

    # Consistency formula: 100% minus deviation penalty
    pct_var = std_dev_ms / avg_pace_ms
    score = max(0.0, min(100.0, 100.0 - (pct_var * 400.0)))
    consistency_score = round(score, 1)

    if consistency_score >= 97.0:
        consistency_rating = "High Consistency"
    elif consistency_score >= 92.0:
        consistency_rating = "Good Consistency"
    elif consistency_score >= 85.0:
        consistency_rating = "Moderate Consistency"
    else:
        consistency_rating = "Variable Pace"

    return {
        "total_laps": total_laps,
        "flying_laps_count": len(flying),
        "average_pace_ms": avg_pace_ms,
        "std_dev_s": std_dev_s,
        "consistency_score": consistency_score,
        "consistency_rating": consistency_rating
    }


def calculate_tyre_and_brake_stats(frames: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Computes averages and peak values for tyres and brakes across frames."""
    if not frames:
        return {
            "tyre_pressures_avg": {"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0},
            "tyre_temps_avg": {"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0},
            "brake_temps_max": {"fl": 0.0, "fr": 0.0, "rl": 0.0, "rr": 0.0}
        }

    count = len(frames)
    p_fl = sum(float(f.get("tyre_press_fl") or 0.0) for f in frames) / count
    p_fr = sum(float(f.get("tyre_press_fr") or 0.0) for f in frames) / count
    p_rl = sum(float(f.get("tyre_press_rl") or 0.0) for f in frames) / count
    p_rr = sum(float(f.get("tyre_press_rr") or 0.0) for f in frames) / count

    t_fl = sum(float(f.get("tyre_temp_fl") or 0.0) for f in frames) / count
    t_fr = sum(float(f.get("tyre_temp_fr") or 0.0) for f in frames) / count
    t_rl = sum(float(f.get("tyre_temp_rl") or 0.0) for f in frames) / count
    t_rr = sum(float(f.get("tyre_temp_rr") or 0.0) for f in frames) / count

    b_fl = max(float(f.get("brake_temp_fl") or 0.0) for f in frames)
    b_fr = max(float(f.get("brake_temp_fr") or 0.0) for f in frames)
    b_rl = max(float(f.get("brake_temp_rl") or 0.0) for f in frames)
    b_rr = max(float(f.get("brake_temp_rr") or 0.0) for f in frames)

    return {
        "tyre_pressures_avg": {
            "fl": round(p_fl, 1),
            "fr": round(p_fr, 1),
            "rl": round(p_rl, 1),
            "rr": round(p_rr, 1)
        },
        "tyre_temps_avg": {
            "fl": round(t_fl, 1),
            "fr": round(t_fr, 1),
            "rl": round(t_rl, 1),
            "rr": round(t_rr, 1)
        },
        "brake_temps_max": {
            "fl": round(b_fl, 0),
            "fr": round(b_fr, 0),
            "rl": round(b_rl, 0),
            "rr": round(b_rr, 0)
        }
    }


def generate_debriefing_text(
    session_meta: Dict[str, Any],
    optimal_data: Dict[str, Any],
    stint_data: Dict[str, Any],
    braking_zones: List[Dict[str, Any]],
    tyre_brake_data: Dict[str, Any]
) -> str:
    """
    Generates a professional, structured German race engineer debriefing text
    ready for instant Telegram / clipboard sharing.
    """
    s_id = session_meta.get("id", "--")
    track = (session_meta.get("track") or "Unbekannt").upper()
    car = session_meta.get("car") or "GT3"
    driver = session_meta.get("driver") or "Fahrer"
    started_at = session_meta.get("started_at")
    date_str = started_at.strftime("%d.%m.%Y %H:%M") if isinstance(started_at, datetime) else "Aktuell"

    best_lap_str = format_lap_time(optimal_data.get("best_lap_ms"))
    best_lap_num = optimal_data.get("best_lap_number") or "--"
    opt_lap_str = format_lap_time(optimal_data.get("optimal_lap_ms"))

    gain_ms = optimal_data.get("potential_gain_ms")
    delta_gain_str = f"-{(gain_ms / 1000.0):.3f}s" if gain_ms is not None else "--"

    s1_str = format_sector_time(optimal_data.get("best_s1_ms"))
    s1_lap = optimal_data.get("best_s1_lap") or "--"
    s2_str = format_sector_time(optimal_data.get("best_s2_ms"))
    s2_lap = optimal_data.get("best_s2_lap") or "--"
    s3_str = format_sector_time(optimal_data.get("best_s3_ms"))
    s3_lap = optimal_data.get("best_s3_lap") or "--"

    flying_laps = stint_data.get("flying_laps_count", 0)
    total_laps = stint_data.get("total_laps", 0)
    avg_pace_str = format_lap_time(stint_data.get("average_pace_ms"))
    consistency = stint_data.get("consistency_score", 0.0)
    rating = stint_data.get("consistency_rating", "N/A")
    std_dev_s = stint_data.get("std_dev_s", 0.0)

    # Top braking highlights (pick top 4 by entry speed / speed drop)
    sorted_braking = sorted(braking_zones, key=lambda b: (b.get("entry_speed", 0) - b.get("apex_speed", 0)), reverse=True)[:4]
    braking_lines = []
    for b in sorted_braking:
        braking_lines.append(
            f"• {b['corner']}: Anbremsen {b['entry_speed']} km/h → Apex {b['apex_speed']} km/h (Weg: {b['braking_distance_m']}m, {b['braking_duration_s']}s)"
        )
    if not braking_lines:
        braking_lines.append("• Keine markanten Bremsdaten erfasst.")

    # Tyres & Brakes
    tp = tyre_brake_data.get("tyre_pressures_avg", {})
    tt = tyre_brake_data.get("tyre_temps_avg", {})
    bt = tyre_brake_data.get("brake_temps_max", {})

    # Engineer conclusion summary
    conclusion_notes = []
    if gain_ms and gain_ms > 800:
        conclusion_notes.append(f"Optimal Lap zeigt deutliches Reservepotenzial von {(gain_ms/1000.0):.2f}s bei optimalem Zusammenfügen der Sektoren.")
    elif gain_ms and gain_ms > 250:
        conclusion_notes.append(f"Gute Konstanz mit weiteren {(gain_ms/1000.0):.2f}s theoretischer Reserve.")
    else:
        conclusion_notes.append("Sehr saubere Ausführung der Bestzeit nahe am Optimum.")

    avg_p = (tp.get("fl", 0) + tp.get("fr", 0) + tp.get("rl", 0) + tp.get("rr", 0)) / 4.0 if tp else 0
    if 26.5 <= avg_p <= 27.8:
        conclusion_notes.append("Reifendrücke liegen im perfekten GT3-Arbeitsfenster (26.5–27.5 PSI).")
    elif avg_p > 27.8:
        conclusion_notes.append("Reifendrücke leicht über Optimum – Heißdrücke um 0.3 PSI absenken.")
    elif avg_p > 0:
        conclusion_notes.append("Reifendrücke unterhalb Optimum – Kaltstartdrücke um 0.4 PSI erhöhen.")

    max_b = max(bt.values()) if bt else 0
    if max_b > 650:
        conclusion_notes.append(f"Hohe Bremsenspitze von {max_b:.0f}°C – Bremsbelüftung (Brake Ducts) öffnen.")

    conclusion_str = " ".join(conclusion_notes)

    text = f"""🏎️ TELEMETRYVAULT RACE ENGINEER DEBRIEFING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📍 Session #{s_id} • {track}
🏎️ {car} • Fahrer: {driver}
📅 {date_str}

⏱️ ZEITEN & SEKTOR-ANALYSE:
• Best Lap: {best_lap_str} (Lap {best_lap_num})
• Optimal Lap: {opt_lap_str} (Δ {delta_gain_str})
  - S1: {s1_str} (Lap {s1_lap})
  - S2: {s2_str} (Lap {s2_lap})
  - S3: {s3_str} (Lap {s3_lap})
• Potenzial-Gewinn: {delta_gain_str if gain_ms is not None else '--'}

📊 STINT-KONSISTENZ:
• Fliegende Runden: {flying_laps} / {total_laps}
• Durchschnitts-Pace: {avg_pace_str}
• Consistency Score: {consistency}% ({rating})
• Standardabweichung: ±{std_dev_s:.3f}s

🛑 KURVEN- & BREMS-HIGHLIGHTS:
{chr(10).join(braking_lines)}

🌡️ REIFEN & BREMSEN:
• Reifendruck (Ø): FL {tp.get('fl', 0.0):.1f} | FR {tp.get('fr', 0.0):.1f} | RL {tp.get('rl', 0.0):.1f} | RR {tp.get('rr', 0.0):.1f} PSI
• Reifentemp (Ø): FL {tt.get('fl', 0.0):.1f}°C | FR {tt.get('fr', 0.0):.1f}°C | RL {tt.get('rl', 0.0):.1f}°C | RR {tt.get('rr', 0.0):.1f}°C
• Max Bremstemp: FL {bt.get('fl', 0.0):.0f}°C | FR {bt.get('fr', 0.0):.0f}°C | RL {bt.get('rl', 0.0):.0f}°C | RR {bt.get('rr', 0.0):.0f}°C

💡 RENNINGENIEUR FAZIT:
{conclusion_str}
"""
    return text.strip()


async def generate_session_report(session_id: int, conn) -> Dict[str, Any]:
    """
    Asynchronously builds the complete Race Engineer report for a session:
    calculates sectors, updates laps in DB if needed, calculates theoretical best lap,
    apex & braking zone analysis, stint consistency, and generates the clipboard debriefing text.
    """
    session = await conn.fetchrow("""
        SELECT id, track, car, driver, started_at, ended_at, is_active,
               frame_count, duration_seconds, total_laps, best_lap_time_ms, created_at
        FROM sessions WHERE id = $1;
    """, session_id)

    if not session:
        return {}

    laps_rows = await conn.fetch("""
        SELECT id, session_id, lap_number, lap_time_ms, is_valid,
               started_at, ended_at, sector1_ms, sector2_ms, sector3_ms,
               max_speed, avg_speed, frame_count
        FROM laps WHERE session_id = $1 ORDER BY lap_number ASC;
    """, session_id)

    laps = [dict(r) for r in laps_rows]
    track_name = session["track"] or "spa"
    boundaries = get_track_sector_boundaries(track_name)
    s1_end = boundaries["s1"]
    s2_end = boundaries["s2"]

    # Calculate or verify sectors for each lap with frames
    for lap in laps:
        lap_num = lap["lap_number"]
        has_sectors = (
            lap.get("sector1_ms") is not None and lap["sector1_ms"] > 0 and
            lap.get("sector2_ms") is not None and lap["sector2_ms"] > 0 and
            lap.get("sector3_ms") is not None and lap["sector3_ms"] > 0
        )

        if not has_sectors:
            frames = await conn.fetch("""
                SELECT track_pos, lap_time_ms, timestamp, session_time, speed, brake, throttle,
                       coord_x, coord_y, coord_z
                FROM telemetry_frames
                WHERE session_id = $1 AND lap_number = $2
                ORDER BY timestamp ASC;
            """, session_id, lap_num)

            if frames:
                frame_dicts = [dict(f) for f in frames]
                sectors = calculate_lap_sectors(frame_dicts, s1_end, s2_end, lap.get("lap_time_ms"))
                if sectors.get("sector1_ms") is not None:
                    lap["sector1_ms"] = sectors["sector1_ms"]
                    lap["sector2_ms"] = sectors["sector2_ms"]
                    lap["sector3_ms"] = sectors["sector3_ms"]

                    # Persist sectors to database
                    await conn.execute("""
                        UPDATE laps SET
                            sector1_ms = $1,
                            sector2_ms = $2,
                            sector3_ms = $3
                        WHERE session_id = $4 AND lap_number = $5;
                    """, sectors["sector1_ms"], sectors["sector2_ms"], sectors["sector3_ms"], session_id, lap_num)

    # Optimal Lap (Theoretical Best)
    optimal_summary = calculate_optimal_lap(laps)

    # Braking & Apex Analysis: best lap vs second best lap
    best_lap_num = optimal_summary.get("best_lap_number")
    best_frames = []
    second_frames = []

    if best_lap_num is not None:
        best_rows = await conn.fetch("""
            SELECT track_pos, lap_time_ms, timestamp, speed, brake, throttle, coord_x, coord_y, coord_z
            FROM telemetry_frames WHERE session_id = $1 AND lap_number = $2
            ORDER BY timestamp ASC;
        """, session_id, best_lap_num)
        best_frames = [dict(r) for r in best_rows]

        # Find 2nd best valid lap
        other_laps = [
            l for l in laps
            if l.get("lap_number") != best_lap_num and l.get("is_valid", True) is not False and (l.get("lap_time_ms") or 0) > 0
        ]
        if other_laps:
            second_best_lap = min(other_laps, key=lambda l: l["lap_time_ms"])["lap_number"]
            second_rows = await conn.fetch("""
                SELECT track_pos, lap_time_ms, timestamp, speed, brake, throttle, coord_x, coord_y, coord_z
                FROM telemetry_frames WHERE session_id = $1 AND lap_number = $2
                ORDER BY timestamp ASC;
            """, session_id, second_best_lap)
            second_frames = [dict(r) for r in second_rows]

    braking_analysis = analyze_braking_zones(best_frames, second_frames, track_name)

    # Stint consistency
    stint_summary = calculate_stint_consistency(laps, optimal_summary.get("best_lap_ms"))

    # Tyres & Brakes metrics
    tyre_brake_rows = await conn.fetch("""
        SELECT tyre_press_fl, tyre_press_fr, tyre_press_rl, tyre_press_rr,
               tyre_temp_fl, tyre_temp_fr, tyre_temp_rl, tyre_temp_rr,
               brake_temp_fl, brake_temp_fr, brake_temp_rl, brake_temp_rr
        FROM telemetry_frames WHERE session_id = $1;
    """, session_id)
    tyre_brake_data = calculate_tyre_and_brake_stats([dict(r) for r in tyre_brake_rows])

    # Text debriefing
    debriefing_text = generate_debriefing_text(
        dict(session),
        optimal_summary,
        stint_summary,
        braking_analysis,
        tyre_brake_data
    )

    return {
        "session_id": session_id,
        "track": track_name,
        "car": session["car"],
        "driver": session["driver"],
        "sectors_summary": {
            "s1_boundary": s1_end,
            "s2_boundary": s2_end,
            "s3_boundary": 1.0,
            "best_s1_ms": optimal_summary.get("best_s1_ms"),
            "best_s1_lap": optimal_summary.get("best_s1_lap"),
            "best_s2_ms": optimal_summary.get("best_s2_ms"),
            "best_s2_lap": optimal_summary.get("best_s2_lap"),
            "best_s3_ms": optimal_summary.get("best_s3_ms"),
            "best_s3_lap": optimal_summary.get("best_s3_lap")
        },
        "optimal_lap": {
            "optimal_lap_ms": optimal_summary.get("optimal_lap_ms"),
            "best_lap_ms": optimal_summary.get("best_lap_ms"),
            "best_lap_number": optimal_summary.get("best_lap_number"),
            "potential_gain_ms": optimal_summary.get("potential_gain_ms"),
            "best_s1_ms": optimal_summary.get("best_s1_ms"),
            "best_s1_lap": optimal_summary.get("best_s1_lap"),
            "best_s2_ms": optimal_summary.get("best_s2_ms"),
            "best_s2_lap": optimal_summary.get("best_s2_lap"),
            "best_s3_ms": optimal_summary.get("best_s3_ms"),
            "best_s3_lap": optimal_summary.get("best_s3_lap")
        },
        "laps": laps,
        "stint_summary": stint_summary,
        "braking_analysis": braking_analysis,
        "tyres_and_brakes": tyre_brake_data,
        "debriefing_text": debriefing_text
    }
