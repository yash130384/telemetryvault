import asyncio
import struct
import unittest
from unittest.mock import AsyncMock, MagicMock

from server.acc_protocol import (
    PROTOCOL_VERSION,
    REGISTER_COMMAND_APPLICATION,
    UNREGISTER_COMMAND_APPLICATION,
    REQUEST_ENTRY_LIST,
    REQUEST_TRACK_DATA,
    REGISTRATION_RESULT,
    REALTIME_UPDATE,
    REALTIME_CAR_UPDATE,
    ENTRY_LIST_CAR,
    TRACK_DATA,
    _GEAR_OFFSET,
    RegistrationResult,
    RealtimeUpdate,
    RealtimeCarUpdate,
    TrackData,
    CarEntry,
    write_string,
    build_registration_request,
    build_request_track_data,
    build_request_entry_list,
    parse_packet,
)
from server.acc_client import ACCClient


def pack_lap(laptime: int, splits: list[int], is_invalid: bool = False, is_valid_for_best: bool = True) -> bytes:
    b = struct.pack("<iHHB", laptime, 0, 0, len(splits))
    for s in splits:
        b += struct.pack("<i", s)
    b += struct.pack("<BBBB", int(is_invalid), int(is_valid_for_best), 0, 0)
    return b


class TestACCProtocol(unittest.TestCase):
    def test_build_registration_request(self):
        req = build_registration_request(display_name="TelemetryVault", update_interval_ms=100)
        self.assertIsInstance(req, bytes)
        # Check op code and version
        cmd, version = struct.unpack_from("<BB", req, 0)
        self.assertEqual(cmd, REGISTER_COMMAND_APPLICATION)
        self.assertEqual(version, PROTOCOL_VERSION)

        # String unpacking: 2-byte len + utf-8
        name_len = struct.unpack_from("<H", req, 2)[0]
        name = req[4 : 4 + name_len].decode("utf-8")
        self.assertEqual(name, "TelemetryVault")

    def test_build_request_track_data(self):
        req = build_request_track_data(connection_id=123)
        cmd, conn_id = struct.unpack("<Bi", req)
        self.assertEqual(cmd, REQUEST_TRACK_DATA)
        self.assertEqual(conn_id, 123)

    def test_build_request_entry_list(self):
        req = build_request_entry_list(connection_id=456)
        cmd, conn_id = struct.unpack("<Bi", req)
        self.assertEqual(cmd, REQUEST_ENTRY_LIST)
        self.assertEqual(conn_id, 456)

    def test_parse_registration_result_success(self):
        raw = struct.pack("<BiBB", REGISTRATION_RESULT, 42, 1, 0) + write_string("")
        packet = parse_packet(raw)
        self.assertIsInstance(packet, RegistrationResult)
        self.assertEqual(packet.connection_id, 42)
        self.assertTrue(packet.success)
        self.assertFalse(packet.read_only)
        self.assertEqual(packet.error, "")

    def test_parse_registration_result_failure(self):
        raw = struct.pack("<BiBB", REGISTRATION_RESULT, -1, 0, 1) + write_string("Server full")
        packet = parse_packet(raw)
        self.assertIsInstance(packet, RegistrationResult)
        self.assertEqual(packet.connection_id, -1)
        self.assertFalse(packet.success)
        self.assertTrue(packet.read_only)
        self.assertEqual(packet.error, "Server full")

    def test_parse_track_data(self):
        raw = struct.pack("<Bi", TRACK_DATA, 42) + write_string("spa") + struct.pack("<ii", 1, 7004)
        packet = parse_packet(raw)
        self.assertIsInstance(packet, TrackData)
        self.assertEqual(packet.track_name, "spa")
        self.assertEqual(packet.track_id, 1)
        self.assertEqual(packet.track_meters, 7004)

    def test_parse_realtime_update(self):
        raw = struct.pack("<BHHBBffi", REALTIME_UPDATE, 1, 2, 0, 3, 12500.0, 60000.0, 7)
        packet = parse_packet(raw)
        self.assertIsInstance(packet, RealtimeUpdate)
        self.assertEqual(packet.event_index, 1)
        self.assertEqual(packet.session_index, 2)
        self.assertEqual(packet.session_phase, 3)
        self.assertAlmostEqual(packet.session_time_ms, 12500.0)
        self.assertEqual(packet.focused_car_index, 7)

    def test_parse_entry_list_car(self):
        raw = (
            struct.pack("<BHB", ENTRY_LIST_CAR, 7, 29)
            + write_string("Manthey EMA")
            + struct.pack("<iBBHB", 911, 0, 0, 1, 2)
            + write_string("Kevin")
            + write_string("Estre")
            + write_string("EST")
            + struct.pack("<BH", 0, 1)
            + write_string("Laurens")
            + write_string("Vanthoor")
            + write_string("VAN")
            + struct.pack("<BH", 0, 2)
        )
        packet = parse_packet(raw)
        self.assertIsInstance(packet, CarEntry)
        self.assertEqual(packet.car_index, 7)
        self.assertEqual(packet.car_model_type, 29)
        self.assertEqual(packet.team_name, "Manthey EMA")
        self.assertEqual(packet.race_number, 911)
        self.assertEqual(len(packet.drivers), 2)
        self.assertEqual(packet.drivers[0].first_name, "Kevin")
        self.assertEqual(packet.drivers[0].last_name, "Estre")
        self.assertEqual(packet.drivers[1].first_name, "Laurens")
        self.assertEqual(packet.drivers[1].last_name, "Vanthoor")

    def test_parse_realtime_car_update(self):
        best_lap = pack_lap(135000, [45000, 45000, 45000], False, True)
        last_lap = pack_lap(136500, [45500, 45500, 45500], False, False)
        current_lap = pack_lap(60000, [45200], False, False)

        raw = (
            struct.pack(
                "<BHHBBfffBHHHHfHi",
                REALTIME_CAR_UPDATE,
                7,  # car_index
                0,  # driver_index
                2,  # driver_count
                4 + _GEAR_OFFSET,  # gear (4)
                120.5,  # world_x
                340.2,  # world_y
                0.8,  # yaw
                0,  # car_location
                245,  # kmh
                1,  # official_pos
                1,  # cup_pos
                1,  # track_pos
                0.62,  # spline
                5,  # laps
                -250,  # delta
            )
            + best_lap
            + last_lap
            + current_lap
        )
        packet = parse_packet(raw)
        self.assertIsInstance(packet, RealtimeCarUpdate)
        self.assertEqual(packet.car_index, 7)
        self.assertEqual(packet.gear, 4)
        self.assertEqual(packet.kmh, 245)
        self.assertAlmostEqual(packet.world_pos_x, 120.5, places=2)
        self.assertAlmostEqual(packet.world_pos_y, 340.2, places=2)
        self.assertAlmostEqual(packet.spline_position, 0.62, places=2)
        self.assertEqual(packet.laps, 5)
        self.assertEqual(packet.delta_ms, -250)
        self.assertEqual(packet.best_lap.laptime_ms, 135000)
        self.assertEqual(packet.current_lap.laptime_ms, 60000)

    def test_parse_empty_or_unknown(self):
        self.assertIsNone(parse_packet(b""))
        self.assertIsNone(parse_packet(b"\xff\x00\x00"))


class TestACCClient(unittest.IsolatedAsyncioTestCase):
    async def test_acc_client_lifecycle_and_packet_flow(self):
        mock_manager = MagicMock()
        mock_manager.handle_packet_dict = AsyncMock()

        client = ACCClient(host="127.0.0.1", port=20000, manager=mock_manager)

        # Mock transport for sending verification
        mock_transport = MagicMock()
        client.transport = mock_transport

        # 1. Receive RegistrationResult
        reg_raw = struct.pack("<BiBB", REGISTRATION_RESULT, 999, 1, 0) + write_string("")
        await client.handle_raw_packet(reg_raw)
        self.assertEqual(client.connection_id, 999)
        # Should have sent track data request and entry list request
        self.assertEqual(mock_transport.sendto.call_count, 2)

        # 2. Receive TrackData
        track_raw = struct.pack("<Bi", TRACK_DATA, 999) + write_string("nurburgring") + struct.pack("<ii", 2, 5148)
        await client.handle_raw_packet(track_raw)
        self.assertEqual(client.track_name, "nurburgring")

        # 3. Receive EntryListCar
        car_raw = (
            struct.pack("<BHB", ENTRY_LIST_CAR, 3, 29)
            + write_string("Manthey EMA")
            + struct.pack("<iBBHB", 911, 0, 0, 1, 1)
            + write_string("Kevin")
            + write_string("Estre")
            + write_string("EST")
            + struct.pack("<BH", 0, 1)
        )
        await client.handle_raw_packet(car_raw)
        self.assertIn(3, client.cars)

        # 4. Receive RealtimeUpdate focusing car 3
        rt_raw = struct.pack("<BHHBBffi", REALTIME_UPDATE, 1, 1, 0, 0, 0.0, 0.0, 3)
        await client.handle_raw_packet(rt_raw)
        self.assertEqual(client.focused_car_index, 3)

        # 5. Receive RealtimeCarUpdate for car 3
        lap_b = pack_lap(115000, [38000, 38000, 39000], False, True)
        car_update_raw = (
            struct.pack(
                "<BHHBBfffBHHHHfHi",
                REALTIME_CAR_UPDATE,
                3,  # car_index
                0,
                1,
                3 + _GEAR_OFFSET,  # gear 3
                10.0,
                20.0,
                0.0,
                0,
                180,  # kmh
                1,
                1,
                1,
                0.25,
                2,  # laps completed (so lap 3)
                -50,
            )
            + lap_b
            + lap_b
            + lap_b
        )
        await client.handle_raw_packet(car_update_raw)

        self.assertEqual(mock_manager.handle_packet_dict.call_count, 1)
        telemetry = mock_manager.handle_packet_dict.call_args[0][0]
        self.assertEqual(telemetry["speed"], 180.0)
        self.assertEqual(telemetry["gear"], 3)
        self.assertEqual(telemetry["lap"], 3)
        self.assertEqual(telemetry["track"], "nurburgring")
        self.assertEqual(telemetry["driver"], "Kevin Estre")
        self.assertEqual(telemetry["car"], "Porsche 992 GT3 R")
        self.assertEqual(telemetry["lap_time_ms"], 115000)

        # 6. RealtimeCarUpdate for a different car should be ignored
        car_other_raw = (
            struct.pack(
                "<BHHBBfffBHHHHfHi",
                REALTIME_CAR_UPDATE,
                88,  # car_index 88 != 3
                0,
                1,
                1 + _GEAR_OFFSET,
                0.0,
                0.0,
                0.0,
                0,
                100,
                2,
                2,
                2,
                0.1,
                1,
                0,
            )
            + lap_b
            + lap_b
            + lap_b
        )
        await client.handle_raw_packet(car_other_raw)
        # Call count should still be 1
        self.assertEqual(mock_manager.handle_packet_dict.call_count, 1)


if __name__ == "__main__":
    unittest.main()
