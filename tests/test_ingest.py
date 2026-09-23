import datetime
import unittest
from unittest.mock import AsyncMock, patch, MagicMock
from server.ingest import TelemetryManager


class TestIngest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.manager = TelemetryManager()

    def test_parse_packet_coord_z_fallback(self):
        # coord_z is 0.0, coord_y is set -> coord_z should equal coord_y
        packet = {
            "speed": 150.0,
            "coord_x": 100.5,
            "coord_y": 200.5,
            "coord_z": 0.0,
        }
        parsed = self.manager.parse_packet(packet)
        self.assertEqual(parsed["coord_x"], 100.5)
        self.assertEqual(parsed["coord_y"], 200.5)
        self.assertEqual(parsed["coord_z"], 200.5)

    def test_parse_packet_coord_z_preserved_when_non_zero(self):
        packet = {
            "coord_x": 10.0,
            "coord_y": 20.0,
            "coord_z": 30.0,
        }
        parsed = self.manager.parse_packet(packet)
        self.assertEqual(parsed["coord_z"], 30.0)

    def test_parse_packet_last_lap_ms(self):
        packet = {
            "last_lap_ms": 118250,
            "lap_time_ms": 12000,
        }
        parsed = self.manager.parse_packet(packet)
        self.assertEqual(parsed["last_lap_ms"], 118250)
        self.assertEqual(parsed["lap_time_ms"], 12000)

    async def test_finalize_lap_locked_prefers_last_lap_ms(self):
        self.manager.active_session_id = 1
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        self.manager.lap_start_time = now_dt - datetime.timedelta(seconds=120)
        self.manager.lap_speeds = [100.0, 200.0]

        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        parsed = {
            "last_lap_ms": 118250,
            "lap_time_ms": 12000,  # Already new lap
            "raw": {"lastLapTimeMS": 118250},
        }

        with patch("server.ingest.get_db_pool", AsyncMock(return_value=mock_pool)):
            await self.manager._finalize_lap_locked(1, parsed, now_dt)

        # Check the insert call into laps
        insert_call = mock_conn.execute.call_args_list[0]
        # Parameters to INSERT INTO laps:
        # ($1 session_id, $2 lap_num, $3 lap_time_ms, $4 max_speed, $5 avg_speed, $6 frame_count, $7 started_at, $8 ended_at)
        args = insert_call[0]
        lap_time_arg = args[3]  # session_id is args[1], lap_number is args[2], lap_time_ms is args[3]
        self.assertEqual(lap_time_arg, 118250)

    async def test_finalize_lap_locked_prefers_raw_last_lap_time_ms(self):
        self.manager.active_session_id = 1
        now_dt = datetime.datetime.now(datetime.timezone.utc)
        self.manager.lap_start_time = now_dt - datetime.timedelta(seconds=120)
        self.manager.lap_speeds = [100.0, 200.0]

        mock_conn = AsyncMock()
        mock_pool = MagicMock()
        mock_pool.acquire.return_value.__aenter__.return_value = mock_conn

        parsed = {
            "lap_time_ms": 5000,  # Already new lap
            "raw": {"lastLapTimeMS": 119500},
        }

        with patch("server.ingest.get_db_pool", AsyncMock(return_value=mock_pool)):
            await self.manager._finalize_lap_locked(1, parsed, now_dt)

        insert_call = mock_conn.execute.call_args_list[0]
        args = insert_call[0]
        lap_time_arg = args[3]
        self.assertEqual(lap_time_arg, 119500)


if __name__ == "__main__":
    unittest.main()
