import asyncio
import logging
import struct
import time
from typing import Optional, Dict, Any

from server.config import ACC_HOST, ACC_PORT
from server.ingest import telemetry_manager
from server.acc_protocol import (
    RegistrationResult,
    RealtimeUpdate,
    RealtimeCarUpdate,
    TrackData,
    CarEntry,
    parse_packet,
    build_registration_request,
    build_request_track_data,
    build_request_entry_list,
    UNREGISTER_COMMAND_APPLICATION,
)

logger = logging.getLogger("telemetryvault.acc_client")

ACC_CAR_MODELS: Dict[int, str] = {
    0: "Porsche 991 GT3 R",
    1: "Mercedes-AMG GT3",
    2: "Ferrari 488 GT3",
    3: "Audi R8 LMS",
    4: "Lamborghini Huracan GT3",
    5: "McLaren 650S GT3",
    6: "Nissan GT-R Nismo GT3 2018",
    7: "BMW M6 GT3",
    8: "Bentley Continental GT3 2018",
    9: "Porsche 991.2 GT3 Cup",
    10: "Nissan GT-R Nismo GT3 2015",
    11: "Bentley Continental GT3 2015",
    12: "Aston Martin Vantage V12 GT3",
    13: "Lamborghini Huracan GT3 Evo",
    14: "Audi R8 LMS Evo",
    15: "Lexus RC F GT3",
    16: "Lamborghini Huracan Super Trofeo",
    17: "Ferrari 488 GT3 Evo",
    18: "McLaren 720S GT3",
    19: "Porsche 911 II GT3 R",
    20: "Mercedes-AMG GT3 2020",
    21: "Ferrari 488 Challenge Evo",
    22: "BMW M2 CS Racing",
    23: "Porsche 911 GT3 Cup (Type 992)",
    24: "Lamborghini Huracan Super Trofeo EVO2",
    25: "BMW M4 GT3",
    26: "Audi R8 LMS Evo II",
    27: "Ferrari 296 GT3",
    28: "Lamborghini Huracan EVO2",
    29: "Porsche 992 GT3 R",
    30: "McLaren 720S GT3 Evo",
    31: "Ford Mustang GT3",
    50: "Alpine A110 GT4",
    51: "Aston Martin Vantage AMR GT4",
    52: "Audi R8 LMS GT4",
    53: "BMW M4 GT4",
    54: "Chevrolet Camaro GT4.R",
    55: "Ginetta G55 GT4",
    56: "KTM X-Bow GT4",
    57: "Maserati Granturismo MC GT4",
    58: "McLaren 570S GT4",
    59: "Mercedes-AMG GT4",
    60: "Porsche 718 Cayman GT4 Clubsport",
}


class ACCDatagramProtocol(asyncio.DatagramProtocol):
    def __init__(self, queue: asyncio.Queue):
        self.queue = queue
        self.transport: Optional[asyncio.DatagramTransport] = None

    def connection_made(self, transport: asyncio.BaseTransport):
        self.transport = transport  # type: ignore

    def datagram_received(self, data: bytes, addr):
        self.queue.put_nowait(data)

    def error_received(self, exc: Exception):
        logger.warning(f"ACC UDP protocol error: {exc}")

    def connection_lost(self, exc: Optional[Exception]):
        pass


class ACCClient:
    def __init__(self, host: str = ACC_HOST, port: int = ACC_PORT, manager=None):
        self.host = host
        self.port = port
        self.manager = manager or telemetry_manager
        self.running: bool = False
        self.connection_id: Optional[int] = None
        self.last_packet_time: float = 0.0

        # ACC State
        self.track_name: Optional[str] = None
        self.cars: Dict[int, CarEntry] = {}
        self.focused_car_index: Optional[int] = None

        self.transport: Optional[asyncio.DatagramTransport] = None
        self.protocol: Optional[ACCDatagramProtocol] = None
        self._queue: asyncio.Queue = asyncio.Queue()
        self._task: Optional[asyncio.Task] = None

    def send_bytes(self, payload: bytes):
        if self.transport:
            self.transport.sendto(payload, (self.host, self.port))

    def send_registration(self):
        payload = build_registration_request()
        self.send_bytes(payload)

    def send_request_track_data(self, connection_id: int):
        payload = build_request_track_data(connection_id)
        self.send_bytes(payload)

    def send_request_entry_list(self, connection_id: int):
        payload = build_request_entry_list(connection_id)
        self.send_bytes(payload)

    async def start(self):
        if self.running:
            return
        self.running = True
        loop = asyncio.get_running_loop()
        try:
            transport, protocol = await loop.create_datagram_endpoint(
                lambda: ACCDatagramProtocol(self._queue),
                local_addr=("0.0.0.0", 0),
            )
            self.transport = transport  # type: ignore
            self.protocol = protocol
            logger.info(f"ACC UDP client initialized, target {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"Failed to bind ACC UDP client socket: {e}", exc_info=True)
            self.running = False
            return

        self._task = asyncio.create_task(self._receive_loop())

    async def stop(self):
        if not self.running:
            return
        self.running = False

        # Attempt to unregister cleanly
        if self.connection_id is not None:
            try:
                payload = struct.pack("<Bi", UNREGISTER_COMMAND_APPLICATION, self.connection_id)
                self.send_bytes(payload)
            except Exception:
                pass

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self.transport:
            self.transport.close()
            self.transport = None

        logger.info("ACC UDP client stopped.")

    async def _receive_loop(self):
        last_reg_time = 0.0
        while self.running:
            try:
                now = time.time()
                needs_reg = (self.connection_id is None) or (
                    self.last_packet_time > 0 and (now - self.last_packet_time > 5.0)
                )

                if needs_reg:
                    if self.last_packet_time > 0 and (now - self.last_packet_time > 5.0):
                        if self.connection_id is not None:
                            logger.info("ACC connection timed out (>5s without packet). Re-registering...")
                            self.connection_id = None

                    if now - last_reg_time >= 5.0:
                        logger.debug(f"Sending registration request to ACC {self.host}:{self.port}")
                        self.send_registration()
                        last_reg_time = now

                try:
                    data = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                    self.last_packet_time = time.time()
                    await self.handle_raw_packet(data)

                    # Drain remaining queued packets without extra delay
                    while not self._queue.empty():
                        data = self._queue.get_nowait()
                        self.last_packet_time = time.time()
                        await self.handle_raw_packet(data)
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in ACC client loop: {e}", exc_info=True)
                await asyncio.sleep(0.1)

    async def handle_raw_packet(self, data: bytes):
        try:
            packet = parse_packet(data)
        except Exception as e:
            logger.debug(f"Failed to parse ACC UDP packet: {e}")
            return

        if packet is None:
            return

        if isinstance(packet, RegistrationResult):
            if packet.success:
                self.connection_id = packet.connection_id
                logger.info(f"ACC Registration successful. Connection ID: {self.connection_id}")
                self.send_request_track_data(self.connection_id)
                self.send_request_entry_list(self.connection_id)
            else:
                logger.warning(f"ACC Registration failed: {packet.error}")

        elif isinstance(packet, TrackData):
            self.track_name = packet.track_name
            logger.info(f"ACC Track Data received: {self.track_name} (ID: {packet.track_id}, {packet.track_meters}m)")

        elif isinstance(packet, CarEntry):
            self.cars[packet.car_index] = packet
            logger.debug(f"ACC CarEntry stored for car {packet.car_index}: {packet.team_name}")

        elif isinstance(packet, RealtimeUpdate):
            self.focused_car_index = packet.focused_car_index

        elif isinstance(packet, RealtimeCarUpdate):
            if self.focused_car_index is None:
                self.focused_car_index = packet.car_index

            if packet.car_index != self.focused_car_index:
                return

            car_entry = self.cars.get(packet.car_index)
            driver_name = "Driver"
            car_name = "GT3 Car"

            if car_entry:
                car_name = (
                    ACC_CAR_MODELS.get(car_entry.car_model_type)
                    or car_entry.team_name
                    or f"Car #{car_entry.race_number}"
                )
                if car_entry.drivers:
                    if 0 <= car_entry.current_driver_index < len(car_entry.drivers):
                        d = car_entry.drivers[car_entry.current_driver_index]
                    else:
                        d = car_entry.drivers[0]
                    parts = [p for p in (d.first_name, d.last_name) if p]
                    driver_name = " ".join(parts) or d.short_name or "Driver"

            lap_time_ms = 0
            if packet.current_lap and packet.current_lap.laptime_ms:
                lap_time_ms = packet.current_lap.laptime_ms

            telemetry_dict = {
                "speed": float(packet.kmh),
                "rpm": 0,
                "max_rpm": 8500,
                "gear": packet.gear,
                "throttle": 0.0,
                "brake": 0.0,
                "clutch": 0.0,
                "steer": 0.0,
                "lap": packet.laps + 1,
                "lap_time_ms": lap_time_ms,
                "session_time": 0.0,
                "track_pos": float(packet.spline_position),
                "coord_x": float(packet.world_pos_x),
                "coord_y": float(packet.world_pos_y),
                "coord_z": 0.0,
                "yaw_rate": 0.0,
                "g_force_lat": 0.0,
                "g_force_lon": 0.0,
                "tyre_press_fl": 0.0,
                "tyre_press_fr": 0.0,
                "tyre_press_rl": 0.0,
                "tyre_press_rr": 0.0,
                "tyre_temp_fl": 0.0,
                "tyre_temp_fr": 0.0,
                "tyre_temp_rl": 0.0,
                "tyre_temp_rr": 0.0,
                "brake_temp_fl": 0.0,
                "brake_temp_fr": 0.0,
                "brake_temp_rl": 0.0,
                "brake_temp_rr": 0.0,
                "fuel": 0.0,
                "car": car_name,
                "track": self.track_name or "spa",
                "driver": driver_name,
                "raw": {},
            }
            if self.manager:
                await self.manager.handle_packet_dict(telemetry_dict)


acc_client = ACCClient()
