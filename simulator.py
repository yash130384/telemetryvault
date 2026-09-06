#!/usr/bin/env python3
"""
TelemetryVault ACC Telemetry Simulator.
Generates realistic Assetto Corsa Competizione (ACC) UDP JSON frames
for hotlaps around Circuit de Spa-Francorchamps (or other tracks).
"""

import argparse
import json
import math
import socket
import time
from typing import List, Tuple

# Waypoints representing the 7.004 km Spa-Francorchamps layout (X, Z in meters)
SPA_WAYPOINTS: List[Tuple[float, float]] = [
    (0.0, 0.0),       # Start/Finish
    (120.0, 15.0),    # Approaching La Source
    (180.0, 80.0),    # La Source braking
    (210.0, 110.0),   # La Source hairpin apex (slow, 65 km/h)
    (170.0, 200.0),   # Downhill to Eau Rouge
    (140.0, 320.0),   # Bottom of Eau Rouge
    (120.0, 420.0),   # Raidillon climb
    (110.0, 520.0),   # Raidillon crest (high speed)
    (100.0, 750.0),   # Kemmel Straight 1
    (90.0, 1100.0),   # Kemmel Straight 2 (270 km/h)
    (75.0, 1400.0),   # Kemmel Straight braking zone
    (50.0, 1530.0),   # Les Combes entry (braking to 130 km/h)
    (10.0, 1610.0),   # Les Combes right
    (-50.0, 1660.0),  # Les Combes left
    (-110.0, 1620.0), # Malmedy exit
    (-170.0, 1500.0), # Downhill to Bruxelles
    (-240.0, 1370.0), # Bruxelles 180° hairpin entry
    (-270.0, 1300.0), # Bruxelles apex (tight right, 105 km/h)
    (-230.0, 1220.0), # Bruxelles exit
    (-190.0, 1120.0), # Speakers Corner (fast left)
    (-230.0, 950.0),  # Approaching Pouhon
    (-310.0, 830.0),  # Pouhon entry (double-left, 190 km/h)
    (-340.0, 730.0),  # Pouhon apex 1
    (-335.0, 640.0),  # Pouhon apex 2
    (-290.0, 550.0),  # Pouhon exit
    (-260.0, 440.0),  # Fagnes entry
    (-220.0, 360.0),  # Fagnes right-left chicane
    (-190.0, 260.0),  # Campus corner
    (-150.0, 140.0),  # Stavelot entry
    (-80.0, 80.0),    # Stavelot acceleration
    (-20.0, 10.0),    # Towards Blanchimont
    (20.0, -120.0),   # Blanchimont 1 (flat out, 250 km/h)
    (50.0, -280.0),   # Blanchimont 2
    (65.0, -440.0),   # Approaching Bus Stop
    (55.0, -560.0),   # Bus Stop heavy braking (75 km/h)
    (15.0, -580.0),   # Bus Stop right
    (5.0, -510.0),    # Bus Stop left
    (-5.0, -320.0),   # Main straight acceleration
    (-5.0, -100.0),   # Pit straight
    (0.0, 0.0)        # Back to Start/Finish line
]

def catmull_rom_spline(p0, p1, p2, p3, t: float) -> Tuple[float, float]:
    """Evaluates cubic Catmull-Rom spline at parameter t in [0, 1]."""
    t2 = t * t
    t3 = t2 * t
    x = 0.5 * ((2 * p1[0]) +
               (-p0[0] + p2[0]) * t +
               (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
               (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3)
    z = 0.5 * ((2 * p1[1]) +
               (-p0[1] + p2[1]) * t +
               (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
               (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3)
    return (x, z)

def generate_track_spline(waypoints: List[Tuple[float, float]], num_samples: int = 2000):
    n = len(waypoints) - 1
    dense_track = []
    for i in range(n):
        p0 = waypoints[(i - 1) % n]
        p1 = waypoints[i]
        p2 = waypoints[(i + 1) % n]
        p3 = waypoints[(i + 2) % n]
        sub_steps = num_samples // n
        for s in range(sub_steps):
            t = s / sub_steps
            dense_track.append(catmull_rom_spline(p0, p1, p2, p3, t))
    return dense_track

def calculate_curvature(p_prev, p_curr, p_next) -> float:
    """Calculates approximate track curvature (1 / radius)."""
    dx1 = p_curr[0] - p_prev[0]
    dz1 = p_curr[1] - p_prev[1]
    dx2 = p_next[0] - p_curr[0]
    dz2 = p_next[1] - p_curr[1]
    
    a1 = math.atan2(dz1, dx1)
    a2 = math.atan2(dz2, dx2)
    da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
    ds = math.hypot(dx1, dz1) + 1e-5
    return da / ds

def main():
    parser = argparse.ArgumentParser(description="TelemetryVault ACC UDP Simulator")
    parser.add_argument("--host", default="127.0.0.1", help="UDP target host")
    parser.add_argument("--port", type=int, default=20000, help="UDP target port")
    parser.add_argument("--laps", type=int, default=2, help="Number of laps to simulate")
    parser.add_argument("--hz", type=float, default=20.0, help="Packets per second")
    parser.add_argument("--fast", action="store_true", help="Send as fast as possible (for quick test data load)")
    parser.add_argument("--speed-multiplier", type=float, default=1.0, help="Simulation speed multiplier")
    parser.add_argument("--car", default="Ferrari 296 GT3", help="Car model name")
    parser.add_argument("--track", default="spa", help="Track name")
    parser.add_argument("--driver", default="Yash (Race Engineer)", help="Driver name")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    track_points = generate_track_spline(SPA_WAYPOINTS, num_samples=2500)
    total_points = len(track_points)

    # Precalculate track distance and curvatures
    curvatures = []
    distances = [0.0]
    for i in range(total_points):
        p_prev = track_points[(i - 1) % total_points]
        p_curr = track_points[i]
        p_next = track_points[(i + 1) % total_points]
        c = calculate_curvature(p_prev, p_curr, p_next)
        curvatures.append(abs(c))
        if i > 0:
            d = math.hypot(p_curr[0] - p_prev[0], p_curr[1] - p_prev[1])
            distances.append(distances[-1] + d)

    total_track_length = distances[-1]

    # Precalculate ideal corner speeds based on curvature (grip limit ~1.8G)
    # v_corner = sqrt(a_lat / curvature)
    ideal_speeds = []
    for c in curvatures:
        if c < 0.0005:
            ideal_speeds.append(275.0)  # Max straight speed km/h
        else:
            # Lat G limit ~ 1.85G -> 1.85 * 9.81 m/s^2
            radius = 1.0 / max(c, 1e-4)
            v_ms = math.sqrt(1.85 * 9.81 * radius)
            v_kmh = min(275.0, max(65.0, v_ms * 3.6))
            ideal_speeds.append(v_kmh)

    # Backward-forward pass for realistic braking and acceleration limits
    accel_limit = 5.5  # m/s^2 acceleration (~0.55G)
    brake_limit = 16.0 # m/s^2 braking (~1.6G)
    target_speeds = [s for s in ideal_speeds]

    # Backward pass for braking distance
    for i in range(total_points - 1, 0, -1):
        ds = distances[i] - distances[i - 1]
        v_next_ms = target_speeds[i] / 3.6
        v_curr_max_ms = math.sqrt(v_next_ms**2 + 2 * brake_limit * ds)
        target_speeds[i - 1] = min(target_speeds[i - 1], v_curr_max_ms * 3.6)

    # Forward pass for engine acceleration
    for i in range(total_points - 1):
        ds = distances[i + 1] - distances[i]
        v_curr_ms = target_speeds[i] / 3.6
        v_next_max_ms = math.sqrt(v_curr_ms**2 + 2 * accel_limit * ds)
        target_speeds[i + 1] = min(target_speeds[i + 1], v_next_max_ms * 3.6)

    print(f"===========================================================")
    print(f"  🏎️  TelemetryVault ACC UDP Simulator")
    print(f"  Target:     {args.host}:{args.port}")
    print(f"  Track:      {args.track} (~{total_track_length:.0f}m)")
    print(f"  Car:        {args.car}")
    print(f"  Driver:     {args.driver}")
    print(f"  Laps:       {args.laps}")
    print(f"  Mode:       {'FAST (Bulk Ingest)' if args.fast else f'{args.hz} Hz ({args.speed_multiplier}x speed)'}")
    print(f"===========================================================")

    dt = 1.0 / args.hz
    packet_id = 1
    session_start = time.time()
    fuel = 48.0

    # Best lap tracking for packets
    best_lap_ms = None
    last_lap_ms = 0

    tyre_temps = [78.0, 78.0, 76.0, 76.0]
    tyre_press = [26.8, 26.8, 26.4, 26.4]

    for lap in range(1, args.laps + 1):
        # Introduce slight variations between laps so lap comparison shows real deltas:
        # Lap 2 is slightly faster (~1.5s faster at Les Combes and Bus Stop)
        lap_speed_factor = 0.985 if lap == 1 else 1.000
        lap_start_time = time.time()
        curr_dist = 0.0
        idx = 0

        print(f"\n🟢 Starting Lap {lap}/{args.laps}...")

        while curr_dist < total_track_length:
            frame_start = time.time()
            norm_pos = min(0.9999, curr_dist / total_track_length)
            idx = int(norm_pos * (total_points - 1))

            target_spd = target_speeds[idx] * lap_speed_factor
            pt = track_points[idx]
            pt_next = track_points[(idx + 1) % total_points]
            heading = math.atan2(pt_next[1] - pt[1], pt_next[0] - pt[0])

            # Determine throttle vs brake
            next_spd = target_speeds[min(total_points - 1, idx + 10)] * lap_speed_factor
            if next_spd < target_spd - 4.0:
                # Heavy braking zone
                throttle = 0.0
                brake = min(1.0, (target_spd - next_spd) / 25.0)
                lon_g = -1.6 * brake
            else:
                # Acceleration or maintenance
                brake = 0.0
                throttle = min(1.0, target_spd / 200.0 + 0.3)
                lon_g = 0.6 * throttle

            # Steering angle from curvature
            curv = curvatures[idx]
            lat_g = (target_spd / 3.6)**2 * curv / 9.81
            steer_angle = math.degrees(math.atan(curv * 2.8)) * (1.0 if idx % 2 == 0 else -1.0)
            steer_angle = max(-35.0, min(35.0, steer_angle * 8.0))

            # Realistic gear selection based on speed
            if target_spd < 75.0:
                gear = 1
                rpm = int(4500 + (target_spd / 75.0) * 3500)
            elif target_spd < 115.0:
                gear = 2
                rpm = int(5000 + ((target_spd - 75.0) / 40.0) * 3300)
            elif target_spd < 155.0:
                gear = 3
                rpm = int(5500 + ((target_spd - 115.0) / 40.0) * 2800)
            elif target_spd < 205.0:
                gear = 4
                rpm = int(6000 + ((target_spd - 155.0) / 50.0) * 2300)
            elif target_spd < 245.0:
                gear = 5
                rpm = int(6500 + ((target_spd - 205.0) / 40.0) * 1900)
            else:
                gear = 6
                rpm = int(6800 + ((target_spd - 245.0) / 35.0) * 1600)
            rpm = min(8450, max(3800, rpm))

            # Dynamic tyre temps & pressures
            heat_factor = (target_spd / 250.0) * 0.01 + brake * 0.05
            tyre_temps[0] = min(96.0, tyre_temps[0] + heat_factor * 1.1)
            tyre_temps[1] = min(94.0, tyre_temps[1] + heat_factor * 0.9)
            tyre_temps[2] = min(92.0, tyre_temps[2] + heat_factor * 1.0)
            tyre_temps[3] = min(91.0, tyre_temps[3] + heat_factor * 0.9)

            tyre_press[0] = 26.8 + (tyre_temps[0] - 78.0) * 0.05
            tyre_press[1] = 26.8 + (tyre_temps[1] - 78.0) * 0.05
            tyre_press[2] = 26.4 + (tyre_temps[2] - 76.0) * 0.05
            tyre_press[3] = 26.4 + (tyre_temps[3] - 76.0) * 0.05

            brake_temp_fl = 350.0 + brake * 350.0
            brake_temp_fr = 345.0 + brake * 340.0
            brake_temp_rl = 280.0 + brake * 250.0
            brake_temp_rr = 280.0 + brake * 250.0

            fuel = max(5.0, fuel - 0.0004)

            # Lap time calculation
            current_lap_ms = int((time.time() - lap_start_time) * 1000) if not args.fast else int((curr_dist / total_track_length) * (138000 if lap == 2 else 140500))

            # ACC out-car acs_ JSON packet
            packet = {
                "packetId": packet_id,
                "speedKmh": round(target_spd, 1),
                "rpm": rpm,
                "maxRpm": 8500,
                "gear": gear,
                "throttle": round(throttle, 2),
                "brake": round(brake, 2),
                "clutch": 0.0,
                "steerAngle": round(steer_angle, 1),
                "lap": lap,
                "lapTimeMs": current_lap_ms,
                "lastLapTimeMS": last_lap_ms,
                "bestLapTimeMS": best_lap_ms or 0,
                "normalizedCarPosition": round(norm_pos, 4),
                "carCoordinates": [round(pt[0], 2), 12.5, round(pt[1], 2)],
                "velocity": [round(target_spd / 3.6 * math.cos(heading), 2), 0.0, round(target_spd / 3.6 * math.sin(heading), 2)],
                "yawRate": round(lat_g * 0.05, 3),
                "driftNormalized": 0.0,
                "gForce": [round(lat_g, 2), round(lon_g, 2), 1.0],
                "tyrePressure": [round(p, 2) for p in tyre_press],
                "tyreTemp": [round(t, 1) for t in tyre_temps],
                "brakeTemp": [round(brake_temp_fl, 1), round(brake_temp_fr, 1), round(brake_temp_rl, 1), round(brake_temp_rr, 1)],
                "fuel": round(fuel, 2),
                "car": args.car,
                "track": args.track,
                "driver": args.driver,
                "sessionTime": round(time.time() - session_start, 2)
            }

            raw_bytes = json.dumps(packet).encode("utf-8")
            sock.sendto(raw_bytes, (args.host, args.port))

            packet_id += 1
            spd_ms = target_spd / 3.6
            curr_dist += spd_ms * (dt * args.speed_multiplier if not args.fast else 0.15)

            if not args.fast:
                elapsed = time.time() - frame_start
                sleep_time = max(0.0, (dt / args.speed_multiplier) - elapsed)
                if sleep_time > 0:
                    time.sleep(sleep_time)
            else:
                # Slight micro-sleep so socket buffer doesn't overflow
                time.sleep(0.002)

        last_lap_ms = current_lap_ms
        if best_lap_ms is None or last_lap_ms < best_lap_ms:
            best_lap_ms = last_lap_ms
        print(f"🏁 Lap {lap} finished! Lap Time: {last_lap_ms / 1000:.3f}s")

    sock.close()
    print(f"\n✅ Simulation completed successfully! Sent {packet_id - 1} frames.")

if __name__ == "__main__":
    main()
