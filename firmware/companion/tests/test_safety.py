import pytest

from follow.config import SafetyConfig
from follow.geometry import Vec3
from follow.safety import BandButton, Mode, SafetyInputs, SafetyMonitor


@pytest.fixture
def monitor():
    return SafetyMonitor(SafetyConfig())


def inputs(**kw):
    base = dict(t=100.0, battery_pct=80.0, last_band_update_t=99.9, wearer_position=Vec3(5, 0, 0))
    base.update(kw)
    return SafetyInputs(**base)


def test_nominal_follows(monitor):
    assert monitor.decide(inputs()).mode == Mode.FOLLOW


def test_battery_thresholds(monitor):
    assert monitor.decide(inputs(battery_pct=25.0)).mode == Mode.RTL
    assert monitor.decide(inputs(battery_pct=15.0)).mode == Mode.LAND


def test_battery_critical_beats_everything(monitor):
    d = monitor.decide(inputs(battery_pct=10.0, last_band_update_t=None, band_button=BandButton.PAUSE))
    assert d.mode == Mode.LAND and "battery" in d.reason


def test_link_ages(monitor):
    assert monitor.decide(inputs(last_band_update_t=97.5)).mode == Mode.FOLLOW
    assert monitor.decide(inputs(last_band_update_t=96.0)).mode == Mode.HOLD
    assert monitor.decide(inputs(last_band_update_t=89.0)).mode == Mode.RTL
    assert monitor.decide(inputs(last_band_update_t=None)).mode == Mode.RTL


def test_band_buttons(monitor):
    assert monitor.decide(inputs(band_button=BandButton.PAUSE)).mode == Mode.HOLD
    assert monitor.decide(inputs(band_button=BandButton.LAND)).mode == Mode.LAND


def test_geofence(monitor):
    assert monitor.decide(inputs(wearer_position=Vec3(200, 0, 0))).mode == Mode.HOLD
    assert monitor.decide(inputs(wearer_position=Vec3(5, 0, -40))).mode == Mode.HOLD
    assert monitor.decide(inputs(wearer_position=Vec3(5, 0, -10))).mode == Mode.FOLLOW
