import datetime
import unittest
from unittest.mock import AsyncMock, MagicMock

from server.analysis_service import (
    get_track_sector_boundaries,
    calculate_lap_sectors,
    calculate_optimal_lap,
    analyze_braking_zones,
    calculate_stint_consistency,
    calculate_tyre_and_brake_stats,
    generate_debriefing_text,
    generate_session_report,
    format_lap_time,
    format_sector_time,
)


class TestAnalysisService(unittest.TestCase):
    def test_track_sector_boundaries(self):
        # Bathurst / Mount Panorama
        bathurst_bounds = get_track_sector_boundaries("bathurst")
        self.assertAlmostEqual(bathurst_bounds["s1"], 0.285)
        self.assertAlmostEqual(bathurst_bounds["s2"], 0.655)
        self.assertAlmostEqual(bathurst_bounds["s3"], 1.0)

        mp_bounds = get_track_sector_boundaries("Mount Panorama")
        self.assertAlmostEqual(mp_bounds["s1"], 0.285)
        self.assertAlmostEqual(mp_bounds["s2"], 0.655)

        # Standard tracks
        spa_bounds = get_track_sector_boundaries("spa")
        self.assertAlmostEqual(spa_bounds["s1"], 0.333)
        self.assertAlmostEqual(spa_bounds["s2"], 0.666)
        self.assertAlmostEqual(spa_bounds["s3"], 1.0)

    def test_calculate_lap_sectors_bathurst(self):
        # Create synthetic lap frames spanning 0.0 to 1.0 over 120,000 ms
        frames = []
        total_time_ms = 120000
        for i in range(101):
            pos = i / 100.0
            lap_ms = int(pos * total_time_ms)
            frames.append({
                "track_pos": pos,
                "lap_time_ms": lap_ms,
                "speed": 200.0,
                "timestamp": datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(milliseconds=lap_ms)
            })

        # Bathurst boundaries: 0.285, 0.655
        sectors = calculate_lap_sectors(frames, s1_end=0.285, s2_end=0.655, lap_time_ms=total_time_ms)
        self.assertIsNotNone(sectors["sector1_ms"])
        self.assertIsNotNone(sectors["sector2_ms"])
        self.assertIsNotNone(sectors["sector3_ms"])

        s1 = sectors["sector1_ms"]
        s2 = sectors["sector2_ms"]
        s3 = sectors["sector3_ms"]

        # Expected:
        # S1 ~ 0.285 * 120000 = 34200 ms
        # S2 ~ (0.655 - 0.285) * 120000 = 44400 ms
        # S3 ~ 120000 - 34200 - 44400 = 41400 ms
        self.assertAlmostEqual(s1, 34200, delta=100)
        self.assertAlmostEqual(s2, 44400, delta=100)
        self.assertEqual(s1 + s2 + s3, total_time_ms)

    def test_calculate_lap_sectors_insufficient_frames(self):
        empty_res = calculate_lap_sectors([], s1_end=0.333, s2_end=0.666)
        self.assertIsNone(empty_res["sector1_ms"])
        self.assertIsNone(empty_res["sector2_ms"])

        few_frames = [{"track_pos": 0.1, "lap_time_ms": 1000}]
        few_res = calculate_lap_sectors(few_frames, s1_end=0.333, s2_end=0.666)
        self.assertIsNone(few_res["sector1_ms"])

    def test_calculate_optimal_lap(self):
        laps = [
            {
                "lap_number": 1,
                "lap_time_ms": 110000,
                "sector1_ms": 30000,
                "sector2_ms": 45000,
                "sector3_ms": 35000,
                "is_valid": True,
            },
            {
                "lap_number": 2,
                "lap_time_ms": 111000,
                "sector1_ms": 31000,
                "sector2_ms": 44000,  # Best S2
                "sector3_ms": 36000,
                "is_valid": True,
            },
            {
                "lap_number": 3,
                "lap_time_ms": 112000,
                "sector1_ms": 32000,
                "sector2_ms": 46000,
                "sector3_ms": 34000,  # Best S3
                "is_valid": True,
            },
            {
                "lap_number": 4,
                "lap_time_ms": 125000,
                "sector1_ms": 28000,  # Invalid lap should not be counted
                "sector2_ms": 40000,
                "sector3_ms": 30000,
                "is_valid": False,
            },
        ]

        result = calculate_optimal_lap(laps)

        self.assertEqual(result["best_s1_ms"], 30000)
        self.assertEqual(result["best_s1_lap"], 1)

        self.assertEqual(result["best_s2_ms"], 44000)
        self.assertEqual(result["best_s2_lap"], 2)

        self.assertEqual(result["best_s3_ms"], 34000)
        self.assertEqual(result["best_s3_lap"], 3)

        # Optimal lap = 30000 + 44000 + 34000 = 108000
        self.assertEqual(result["optimal_lap_ms"], 108000)
        self.assertEqual(result["best_lap_ms"], 110000)
        self.assertEqual(result["best_lap_number"], 1)

        # Potential gain = 110000 - 108000 = 2000 ms
        self.assertEqual(result["potential_gain_ms"], 2000)

    def test_analyze_braking_zones_known_track(self):
        # Create synthetic frames for Bathurst: simulate braking into Hell Corner (track_pos ~0.06)
        # and The Chase (track_pos ~0.84)
        best_frames = []
        compare_frames = []

        for i in range(200):
            pos = i / 200.0
            # Default speed 240
            spd = 240.0
            # Braking into Hell Corner (pos 0.04 to 0.07)
            if 0.04 <= pos <= 0.06:
                spd = 240.0 - (pos - 0.04) / 0.02 * 140.0  # decelerates to 100
            elif 0.06 < pos <= 0.08:
                spd = 100.0 + (pos - 0.06) / 0.02 * 80.0
            # Braking into The Chase (pos 0.81 to 0.84)
            elif 0.81 <= pos <= 0.84:
                spd = 280.0 - (pos - 0.81) / 0.03 * 160.0  # decelerates to 120
            elif 0.84 < pos <= 0.87:
                spd = 120.0 + (pos - 0.84) / 0.03 * 60.0

            best_frames.append({
                "track_pos": pos,
                "speed": spd,
                "brake": 0.8 if (0.04 <= pos <= 0.06 or 0.81 <= pos <= 0.84) else 0.0,
                "coord_x": pos * 6000.0,
                "coord_z": 0.0,
                "lap_time_ms": int(pos * 125000),
            })

            # Compare lap is 5 km/h slower in apex
            compare_frames.append({
                "track_pos": pos,
                "speed": max(40.0, spd - 5.0) if (0.05 <= pos <= 0.07 or 0.83 <= pos <= 0.85) else spd,
                "brake": 0.8 if (0.04 <= pos <= 0.06 or 0.81 <= pos <= 0.84) else 0.0,
                "coord_x": pos * 6000.0,
                "coord_z": 0.0,
                "lap_time_ms": int(pos * 126000),
            })

        zones = analyze_braking_zones(best_frames, compare_frames, track_name="bathurst")
        self.assertTrue(len(zones) >= 2)

        # Check Hell Corner and The Chase presence
        corner_names = [z["corner"] for z in zones]
        self.assertTrue(any("Hell Corner" in name for name in corner_names))
        self.assertTrue(any("The Chase" in name for name in corner_names))

        hell_corner = next(z for z in zones if "Hell Corner" in z["corner"])
        self.assertAlmostEqual(hell_corner["apex_speed"], 100.0, delta=5.0)
        self.assertTrue(hell_corner["entry_speed"] > hell_corner["apex_speed"])
        self.assertTrue(hell_corner["braking_distance_m"] > 0)
        self.assertTrue(hell_corner["braking_duration_s"] > 0)

        # Delta should show best lap was faster at apex (+5 km/h)
        if hell_corner["delta_apex_speed"] is not None:
            self.assertTrue(hell_corner["delta_apex_speed"] >= 0)

    def test_calculate_stint_consistency(self):
        # 5 consistent laps (all within ~0.2s)
        consistent_laps = [
            {"lap_number": 1, "lap_time_ms": 120500, "is_valid": True},  # outlap
            {"lap_number": 2, "lap_time_ms": 120000, "is_valid": True},
            {"lap_number": 3, "lap_time_ms": 120150, "is_valid": True},
            {"lap_number": 4, "lap_time_ms": 120080, "is_valid": True},
            {"lap_number": 5, "lap_time_ms": 120220, "is_valid": True},
        ]

        summary = calculate_stint_consistency(consistent_laps, best_lap_time_ms=120000)
        self.assertEqual(summary["total_laps"], 5)
        self.assertTrue(summary["consistency_score"] >= 98.0)
        self.assertEqual(summary["consistency_rating"], "High Consistency")
        self.assertTrue(summary["std_dev_s"] < 0.2)

        # Outlier filtering: Lap 6 is inlap / spun lap (160,000 ms)
        inlap_laps = consistent_laps + [{"lap_number": 6, "lap_time_ms": 160000, "is_valid": True}]
        summary_outlier = calculate_stint_consistency(inlap_laps, best_lap_time_ms=120000)
        # Lap 6 should be filtered out from flying laps count
        self.assertEqual(summary_outlier["flying_laps_count"], summary["flying_laps_count"])

    def test_calculate_tyre_and_brake_stats(self):
        frames = [
            {
                "tyre_press_fl": 26.8, "tyre_press_fr": 27.0, "tyre_press_rl": 26.5, "tyre_press_rr": 26.6,
                "tyre_temp_fl": 82.0, "tyre_temp_fr": 83.0, "tyre_temp_rl": 79.0, "tyre_temp_rr": 80.0,
                "brake_temp_fl": 450.0, "brake_temp_fr": 460.0, "brake_temp_rl": 320.0, "brake_temp_rr": 310.0
            },
            {
                "tyre_press_fl": 27.0, "tyre_press_fr": 27.2, "tyre_press_rl": 26.7, "tyre_press_rr": 26.8,
                "tyre_temp_fl": 84.0, "tyre_temp_fr": 85.0, "tyre_temp_rl": 81.0, "tyre_temp_rr": 82.0,
                "brake_temp_fl": 580.0, "brake_temp_fr": 590.0, "brake_temp_rl": 350.0, "brake_temp_rr": 340.0
            }
        ]
        stats = calculate_tyre_and_brake_stats(frames)
        self.assertAlmostEqual(stats["tyre_pressures_avg"]["fl"], 26.9)
        self.assertAlmostEqual(stats["tyre_temps_avg"]["fr"], 84.0)
        self.assertEqual(stats["brake_temps_max"]["fl"], 580.0)
        self.assertEqual(stats["brake_temps_max"]["fr"], 590.0)

    def test_generate_debriefing_text(self):
        session_meta = {
            "id": 42,
            "track": "bathurst",
            "car": "Ferrari 296 GT3",
            "driver": "Yash",
            "started_at": datetime.datetime(2026, 9, 23, 14, 30)
        }
        optimal_data = {
            "best_lap_ms": 122145,
            "best_lap_number": 3,
            "optimal_lap_ms": 121483,
            "potential_gain_ms": 662,
            "best_s1_ms": 34210,
            "best_s1_lap": 3,
            "best_s2_ms": 52810,
            "best_s2_lap": 4,
            "best_s3_ms": 34463,
            "best_s3_lap": 3
        }
        stint_data = {
            "flying_laps_count": 5,
            "total_laps": 6,
            "average_pace_ms": 122850,
            "consistency_score": 98.2,
            "consistency_rating": "High Consistency",
            "std_dev_s": 0.285
        }
        braking_zones = [
            {
                "corner": "The Chase (T22)",
                "entry_speed": 284.0,
                "apex_speed": 122.0,
                "braking_distance_m": 142.5,
                "braking_duration_s": 2.65
            }
        ]
        tyre_brake_data = {
            "tyre_pressures_avg": {"fl": 26.8, "fr": 27.1, "rl": 26.5, "rr": 26.7},
            "tyre_temps_avg": {"fl": 82.5, "fr": 84.1, "rl": 79.2, "rr": 80.0},
            "brake_temps_max": {"fl": 580.0, "fr": 565.0, "rl": 420.0, "rr": 410.0}
        }

        text = generate_debriefing_text(session_meta, optimal_data, stint_data, braking_zones, tyre_brake_data)
        self.assertIn("TELEMETRYVAULT RACE ENGINEER DEBRIEFING", text)
        self.assertIn("BATHURST", text)
        self.assertIn("Ferrari 296 GT3", text)
        self.assertIn("2:02.145", text)
        self.assertIn("2:01.483", text)
        self.assertIn("-0.662s", text)
        self.assertIn("98.2%", text)
        self.assertIn("The Chase", text)
        self.assertIn("284.0 km/h", text)
        self.assertIn("FL 26.8", text)
        self.assertIn("RENNINGENIEUR FAZIT", text)


class TestAsyncSessionReport(unittest.IsolatedAsyncioTestCase):
    async def test_generate_session_report_with_mock_conn(self):
        mock_conn = AsyncMock()

        session_row = {
            "id": 1,
            "track": "bathurst",
            "car": "Porsche 992 GT3 R",
            "driver": "Driver A",
            "started_at": datetime.datetime.now(datetime.timezone.utc),
            "ended_at": None,
            "is_active": True,
            "frame_count": 200,
            "duration_seconds": 120.0,
            "total_laps": 2,
            "best_lap_time_ms": 125000,
            "created_at": datetime.datetime.now(datetime.timezone.utc),
        }
        mock_conn.fetchrow.return_value = session_row

        laps_rows = [
            {
                "id": 10,
                "session_id": 1,
                "lap_number": 1,
                "lap_time_ms": 126000,
                "is_valid": True,
                "started_at": datetime.datetime.now(datetime.timezone.utc),
                "ended_at": None,
                "sector1_ms": 36000,
                "sector2_ms": 54000,
                "sector3_ms": 36000,
                "max_speed": 280.0,
                "avg_speed": 180.0,
                "frame_count": 100,
            },
            {
                "id": 11,
                "session_id": 1,
                "lap_number": 2,
                "lap_time_ms": 125000,
                "is_valid": True,
                "started_at": datetime.datetime.now(datetime.timezone.utc),
                "ended_at": None,
                "sector1_ms": 35000,
                "sector2_ms": 55000,
                "sector3_ms": 35000,
                "max_speed": 282.0,
                "avg_speed": 182.0,
                "frame_count": 100,
            },
        ]
        # Return laps for first fetch, then frames
        mock_conn.fetch.side_effect = [
            laps_rows,  # SELECT * FROM laps
            [],         # best_rows (telemetry frames)
            [],         # second_rows
            [],         # tyre_brake_rows
        ]

        report = await generate_session_report(session_id=1, conn=mock_conn)

        self.assertEqual(report["session_id"], 1)
        self.assertEqual(report["track"], "bathurst")
        self.assertEqual(report["optimal_lap"]["best_s1_ms"], 35000)
        self.assertEqual(report["optimal_lap"]["best_s2_ms"], 54000)
        self.assertEqual(report["optimal_lap"]["best_s3_ms"], 35000)
        self.assertEqual(report["optimal_lap"]["optimal_lap_ms"], 124000)
        self.assertEqual(report["optimal_lap"]["potential_gain_ms"], 1000)
        self.assertIn("debriefing_text", report)
        self.assertTrue(len(report["debriefing_text"]) > 50)


if __name__ == "__main__":
    unittest.main()
