"""Flight controller adapter.

`FlightController` is the small interface the rest of the code depends on.
`MavlinkFlightController` implements it with pymavlink against ArduPilot (real or SITL).
`FakeFlightController` is a trivial in-memory implementation for tests.

pymavlink is imported lazily so the controller and tests run without it installed.
"""

from __future__ import annotations

import math
import time
from typing import Optional, Protocol

from .estimator import DroneState
from .geometry import Vec3
from .safety import Mode


class FlightController(Protocol):
    def read_state(self) -> Optional[DroneState]: ...
    def battery_pct(self) -> float: ...
    def send_position_setpoint(self, position: Vec3, yaw_rad: float) -> None: ...
    def set_mode(self, mode: Mode) -> None: ...


class FakeFlightController:
    def __init__(self, state: DroneState, battery_pct: float = 100.0):
        self.state = state
        self._battery = battery_pct
        self.setpoints: list[tuple[Vec3, float]] = []
        self.modes: list[Mode] = []

    def read_state(self) -> Optional[DroneState]:
        return self.state

    def battery_pct(self) -> float:
        return self._battery

    def send_position_setpoint(self, position: Vec3, yaw_rad: float) -> None:
        self.setpoints.append((position, yaw_rad))

    def set_mode(self, mode: Mode) -> None:
        self.modes.append(mode)


class MavlinkFlightController:
    """ArduPilot Copter over MAVLink 2.

    Usage:
        fc = MavlinkFlightController("/dev/serial0", 921600)   # or "udp:127.0.0.1:14550" for SITL
        fc.connect()
    """

    # ArduPilot Copter custom mode numbers.
    _COPTER_MODES = {"GUIDED": 4, "RTL": 6, "LAND": 9}

    def __init__(self, device: str, baud: int = 921600):
        self.device = device
        self.baud = baud
        self._conn = None
        self._battery = 100.0
        self._last_mode: Optional[Mode] = None

    def connect(self, timeout_s: float = 30.0) -> None:
        from pymavlink import mavutil  # lazy import

        self._conn = mavutil.mavlink_connection(self.device, baud=self.baud, source_system=1, source_component=191)
        self._conn.wait_heartbeat(timeout=timeout_s)
        # Ask for the streams we need at 20 Hz.
        for msg_id in (
            mavutil.mavlink.MAVLINK_MSG_ID_LOCAL_POSITION_NED,
            mavutil.mavlink.MAVLINK_MSG_ID_ATTITUDE,
            mavutil.mavlink.MAVLINK_MSG_ID_GLOBAL_POSITION_INT,
        ):
            self._conn.mav.command_long_send(
                self._conn.target_system, self._conn.target_component,
                mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
                msg_id, int(1e6 / 20), 0, 0, 0, 0, 0,
            )
        self._conn.mav.command_long_send(
            self._conn.target_system, self._conn.target_component,
            mavutil.mavlink.MAV_CMD_SET_MESSAGE_INTERVAL, 0,
            mavutil.mavlink.MAVLINK_MSG_ID_BATTERY_STATUS, int(1e6 / 2), 0, 0, 0, 0, 0,
        )
        self._pos = None
        self._yaw = None
        self._agl = None

    def read_state(self) -> Optional[DroneState]:
        assert self._conn is not None, "call connect() first"
        while True:
            msg = self._conn.recv_match(blocking=False)
            if msg is None:
                break
            t = msg.get_type()
            if t == "LOCAL_POSITION_NED":
                self._pos = Vec3(msg.x, msg.y, msg.z)
            elif t == "ATTITUDE":
                self._yaw = msg.yaw
            elif t == "GLOBAL_POSITION_INT":
                self._agl = msg.relative_alt / 1000.0
            elif t == "BATTERY_STATUS" and msg.battery_remaining >= 0:
                self._battery = float(msg.battery_remaining)
        if self._pos is None or self._yaw is None:
            return None
        agl = self._agl if self._agl is not None else -self._pos.z
        return DroneState(self._pos, self._yaw, agl)

    def battery_pct(self) -> float:
        return self._battery

    def send_position_setpoint(self, position: Vec3, yaw_rad: float) -> None:
        from pymavlink import mavutil

        assert self._conn is not None
        # Type mask: use position + yaw, ignore velocity, accel, yaw rate.
        type_mask = (
            (1 << 3) | (1 << 4) | (1 << 5)      # vx vy vz
            | (1 << 6) | (1 << 7) | (1 << 8)    # ax ay az
            | (1 << 11)                         # yaw rate
        )
        self._conn.mav.set_position_target_local_ned_send(
            int(time.monotonic() * 1000) & 0xFFFFFFFF,
            self._conn.target_system, self._conn.target_component,
            mavutil.mavlink.MAV_FRAME_LOCAL_NED,
            type_mask,
            position.x, position.y, position.z,
            0, 0, 0, 0, 0, 0,
            yaw_rad, 0,
        )

    def set_mode(self, mode: Mode) -> None:
        from pymavlink import mavutil

        assert self._conn is not None
        if mode == self._last_mode:
            return
        name = {"FOLLOW": "GUIDED", "HOLD": "GUIDED", "RTL": "RTL", "LAND": "LAND"}[mode.value]
        self._conn.mav.command_long_send(
            self._conn.target_system, self._conn.target_component,
            mavutil.mavlink.MAV_CMD_DO_SET_MODE, 0,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED,
            self._COPTER_MODES[name], 0, 0, 0, 0, 0,
        )
        self._last_mode = mode


def yaw_deg(yaw_rad: float) -> float:
    return math.degrees(yaw_rad) % 360.0
