from follow.band_protocol import BandStatus, encode_manufacturer_data, parse_manufacturer_data
from follow.safety import BandButton


def test_roundtrip():
    s = BandStatus(band_id=1, battery_pct=77, button=BandButton.PAUSE, uptime_s=12345)
    assert parse_manufacturer_data(encode_manufacturer_data(s)) == s


def test_rejects_other_manufacturer_and_version():
    s = BandStatus(1, 50, BandButton.NONE, 0)
    data = bytearray(encode_manufacturer_data(s))
    data[0] = 0x4C  # Apple-ish id
    assert parse_manufacturer_data(bytes(data)) is None
    data = bytearray(encode_manufacturer_data(s))
    data[2] = 9  # future protocol version
    assert parse_manufacturer_data(bytes(data)) is None


def test_short_payload():
    assert parse_manufacturer_data(b"\xff\xff\x01") is None


def test_unknown_button_maps_to_none():
    data = bytearray(encode_manufacturer_data(BandStatus(1, 50, BandButton.NONE, 0)))
    data[5] = 42
    assert parse_manufacturer_data(bytes(data)).button == BandButton.NONE
