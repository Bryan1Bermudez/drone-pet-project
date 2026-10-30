"""Follow controller for the silent follow drone.

Modules
-------
config      Tunable parameters with quiet/low-power defaults.
estimator   Two-anchor UWB range -> wearer position in local NED.
controller  Wearer position -> lazy drone setpoint (deadbands, rate limits).
safety      Battery / link / fence / button -> flight mode decision.
band_protocol  Parse the wristband's BLE manufacturer data.
mavlink_io  ArduPilot adapter (pymavlink) behind a small interface.
sim         Kinematic simulator used by the tests and for desktop runs.
"""

from .config import FollowConfig  # noqa: F401
