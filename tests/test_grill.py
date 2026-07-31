"""Tests for the I/O half - retries, guards, and what goes on the wire."""

from __future__ import annotations

import socket

import pytest

from gmg_local import Grill, GmgError
from gmg_local.const import (
    CODE_FIRMWARE,
    CODE_POWER_OFF,
    CODE_POWER_ON,
    CODE_POWER_ON_COLD_SMOKE,
    CODE_SERIAL,
    CODE_STATUS,
    MAX_TEMP_F,
    MAX_TEMP_F_PROBE,
    MIN_TEMP_F,
    MIN_TEMP_F_PROBE,
    PROBE_TARGET_CLEAR,
    STATUS_MIN_LEN,
    UDP_PORT,
)



def _grill() -> Grill:
    return Grill("10.0.0.9", "GMG12345678")


# --- construction ---------------------------------------------------------


def test_rejects_a_non_address():
    with pytest.raises(ValueError):
        Grill("not-an-ip")


@pytest.mark.parametrize("addr", ["10.0.0.9", "127.0.0.1", "::1"])
def test_accepts_valid_addresses(addr):
    assert Grill(addr).ip == addr


def test_public_accessors_expose_what_consumers_need():
    """Consumers must not have to reach for `_serial_number` or `_ip`."""
    g = Grill("10.0.0.9", "GMG12345678")
    assert g.serial_number == "GMG12345678"
    assert g.ip == "10.0.0.9"


# --- status(): the retry contract ----------------------------------------


def test_status_parses_a_good_frame(fake_socket, frame):
    fake_socket(lambda msg: frame(grill_temp=350) if msg == CODE_STATUS else None)
    state = _grill().status()
    assert state["temp"] == 350
    assert state["fireStatePercentage"] == 100


def test_status_retries_through_silence_then_succeeds(fake_socket, frame):
    """Two timeouts then a good frame must still return a reading."""
    calls = {"n": 0}

    def replies(msg):
        calls["n"] += 1
        return None if calls["n"] <= 2 else frame()

    fake_socket(replies)
    assert _grill().status()["temp"] == 225
    assert calls["n"] == 3


def test_status_retries_short_packets_rather_than_parsing_them(fake_socket, frame):
    """A truncated datagram is a transport artifact, not data.

    Parsing one would either raise or invent fields. Before this behaviour
    existed, a single stray packet took every consumer's entities offline.
    """
    calls = {"n": 0}

    def replies(msg):
        calls["n"] += 1
        return bytes(STATUS_MIN_LEN - 1) if calls["n"] == 1 else frame()

    fake_socket(replies)
    assert _grill().status()["temp"] == 225
    assert calls["n"] == 2


def test_status_gives_up_after_retries_and_says_why(fake_socket):
    fake_socket(lambda msg: None)
    with pytest.raises(GmgError) as err:
        _grill().status(retries=3)
    assert "3 silent" in str(err.value)


def test_status_reports_short_packet_lengths_in_the_error(fake_socket):
    """The error must distinguish silence from junk - they have different causes."""
    fake_socket(lambda msg: bytes(10))
    with pytest.raises(GmgError) as err:
        _grill().status(retries=2)
    msg = str(err.value)
    assert "0 silent" in msg and "2 too short" in msg and "[10, 10]" in msg


def test_status_never_returns_a_partial_dict(fake_socket):
    """All-or-nothing: a half-filled dict is indistinguishable from real data."""
    fake_socket(lambda msg: bytes(STATUS_MIN_LEN - 1))
    with pytest.raises(GmgError):
        _grill().status(retries=1)


# --- what actually goes on the wire ---------------------------------------


def test_status_polls_the_right_port_and_command(fake_socket, frame):
    created = fake_socket(lambda msg: frame())
    _grill().status()
    data, addr = created[0].sent[0]
    assert data == CODE_STATUS
    assert addr == ("10.0.0.9", UDP_PORT)


@pytest.mark.parametrize(
    "method,code",
    [("power_on", CODE_POWER_ON), ("power_off", CODE_POWER_OFF), ("power_on_cool", CODE_POWER_ON_COLD_SMOKE)],
)
def test_power_commands_send_their_codes(fake_socket, method, code):
    created = fake_socket(lambda msg: b"OK")
    getattr(_grill(), method)()
    assert created[0].sent[0][0] == code


def test_set_temp_formats_the_command(fake_socket):
    created = fake_socket(lambda msg: b"OK")
    _grill().set_temp(225)
    assert created[0].sent[0][0] == b"UT225!"


@pytest.mark.parametrize("probe,prefix", [(1, b"UF"), (2, b"Uf")])
def test_probe_targets_use_a_different_command_per_probe(fake_socket, probe, prefix):
    """Probe 1 and 2 differ only by letter case - easy to get wrong silently."""
    created = fake_socket(lambda msg: b"OK")
    _grill().set_temp_probe(203, probe)
    assert created[0].sent[0][0] == prefix + b"203!"


def test_serial_round_trips(fake_socket):
    fake_socket(lambda msg: b"GMG87654321" if msg == CODE_SERIAL else None)
    g = Grill("10.0.0.9")
    assert g.serial() == "GMG87654321"
    assert g.serial_number == "GMG87654321"


# --- firmware(): same retry contract as status() ---------------------------


def test_firmware_round_trips_and_caches(fake_socket):
    fake_socket(lambda msg: b"UNJB02SUF0_2.3" if msg == CODE_FIRMWARE else None)
    g = _grill()
    assert g.firmware() == "UNJB02SUF0_2.3"
    assert g.firmware_version == "UNJB02SUF0_2.3"


def test_firmware_starts_uncached():
    assert _grill().firmware_version == ""


def test_firmware_retries_through_silence_then_succeeds(fake_socket):
    """The grill drops the occasional datagram even when healthy (~1 in 3
    observed live on 2026-07-30) - silence must be retried, not raised."""
    calls = {"n": 0}

    def replies(msg):
        calls["n"] += 1
        return None if calls["n"] <= 2 else b"UNJB02SUF0_2.3"

    fake_socket(replies)
    assert _grill().firmware() == "UNJB02SUF0_2.3"
    assert calls["n"] == 3


def test_firmware_retries_junk_rather_than_returning_it(fake_socket):
    """Binary junk is a transport artifact, not a version string."""
    calls = {"n": 0}

    def replies(msg):
        calls["n"] += 1
        return b"\x0c\x142\x16\x19\x15\x19" if calls["n"] == 1 else b"UNJB02SUF0_2.3"

    fake_socket(replies)
    assert _grill().firmware() == "UNJB02SUF0_2.3"
    assert calls["n"] == 2


def test_firmware_gives_up_after_retries_and_says_why(fake_socket):
    fake_socket(lambda msg: None)
    with pytest.raises(GmgError) as err:
        _grill().firmware(retries=3)
    assert "3 silent" in str(err.value)


def test_firmware_sends_the_right_command(fake_socket):
    created = fake_socket(lambda msg: b"UNJB02SUF0_2.3")
    _grill().firmware()
    assert created[0].sent[0][0] == CODE_FIRMWARE


# --- range guards ---------------------------------------------------------


@pytest.mark.parametrize("temp", [MIN_TEMP_F - 1, MAX_TEMP_F + 1, 0, 1000])
def test_grill_target_out_of_range_raises(temp):
    with pytest.raises(ValueError):
        _grill().set_temp(temp)


@pytest.mark.parametrize("temp", [MIN_TEMP_F, MAX_TEMP_F])
def test_grill_target_bounds_are_inclusive(fake_socket, temp):
    fake_socket(lambda msg: b"OK")
    _grill().set_temp(temp)  # must not raise


@pytest.mark.parametrize("temp", [MIN_TEMP_F_PROBE - 1, MAX_TEMP_F_PROBE + 1, 500])
def test_probe_target_out_of_range_raises(temp):
    with pytest.raises(ValueError):
        _grill().set_temp_probe(temp, 1)


def test_probe_target_clear_is_allowed_below_the_floor(fake_socket):
    """0 means "no target" and is deliberately below MIN_TEMP_F_PROBE."""
    assert PROBE_TARGET_CLEAR < MIN_TEMP_F_PROBE
    created = fake_socket(lambda msg: b"OK")
    _grill().set_temp_probe(PROBE_TARGET_CLEAR, 1)
    assert created[0].sent[0][0] == b"UF0!"


@pytest.mark.parametrize("probe", [0, 3, -1])
def test_unknown_probe_number_raises(probe):
    with pytest.raises(ValueError):
        _grill().set_temp_probe(203, probe)


# --- transport behaviour --------------------------------------------------


def test_send_returns_none_on_timeout_rather_than_raising(fake_socket):
    fake_socket(lambda msg: None)
    assert _grill().send(b"UR001!") is None


def test_send_closes_the_socket_even_when_nothing_replies(fake_socket):
    """A leaked socket per failed poll would exhaust descriptors over days."""
    created = fake_socket(lambda msg: None)
    _grill().send(b"UR001!")
    assert created[0].closed is True


def test_send_survives_an_os_error(fake_socket, monkeypatch):
    created = fake_socket(lambda msg: None)

    def boom(*_a, **_kw):
        raise OSError("network unreachable")

    g = _grill()
    monkeypatch.setattr(socket, "socket", lambda *a, **kw: _raiser(boom))
    assert g.send(b"UR001!") is None


class _raiser:
    """A socket whose sendto fails, to prove OSError is caught not propagated."""

    def __init__(self, _boom):
        self.closed = False

    def settimeout(self, *_a):
        pass

    def sendto(self, *_a):
        raise OSError("network unreachable")

    def recvfrom(self, *_a):
        raise AssertionError("should not be reached")

    def close(self):
        self.closed = True
