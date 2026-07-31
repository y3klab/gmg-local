"""Protocol tests.

The status frames here are **reconstructed**, not captured: the decoded values
are real observations from an instrumented cook on 2026-07-25, encoded back into
frames at the documented offsets. That distinction matters - these prove the
parser is self-consistent with observed behaviour, not that the offsets are
right. Offsets are corroborated across four independent implementations.

A genuinely captured frame has not been preserved. Capturing one is the
prerequisite for decoding bytes 34..51, and should replace these fixtures when
it exists.
"""

from __future__ import annotations

import pytest

from gmg_local import (
    POLL_ACTIVE,
    POLL_IDLE,
    STATUS_MIN_LEN,
    STATUS_OBSERVED_LEN,
    GmgError,
    model_for,
    parse_firmware,
    parse_status,
    poll_interval_for,
    u16,
    u32,
)


def build_frame(
    *,
    grill_temp: int = 65,
    probe_1_temp: int = 607,
    grill_set_temp: int = 150,
    api_version: int = 1,
    probe_2_temp: int = 607,
    probe_2_set_temp: int = 0,
    warn_state: int = 0,
    probe_1_set_temp: int = 0,
    power_state: int = 1,
    fire_state: int = 2,
    fire_state_progress: int = 25,
    length: int = STATUS_OBSERVED_LEN,
) -> bytes:
    """Encode values into a status frame at the documented offsets."""
    f = bytearray(length)

    def put16(offset: int, value: int) -> None:
        f[offset] = value & 0xFF
        f[offset + 1] = (value >> 8) & 0xFF

    put16(2, grill_temp)
    put16(4, probe_1_temp)
    put16(6, grill_set_temp)
    f[8] = api_version
    put16(16, probe_2_temp)
    put16(18, probe_2_set_temp)
    for i in range(4):
        f[24 + i] = (warn_state >> (8 * i)) & 0xFF
    put16(28, probe_1_set_temp)
    f[30] = power_state
    f[32] = fire_state
    f[33] = fire_state_progress
    return bytes(f)


# --- the bug that matters -------------------------------------------------


def test_grill_temp_above_255_does_not_wrap():
    """A 350 F grill must read 350, not 94.

    GMG temperatures are 16-bit little-endian. Reading only the low byte wraps
    anything above 255, so a hot grill reports as barely warm. This is the
    defect still present in the most-installed public integration.
    """
    frame = parse_status(build_frame(grill_temp=350))
    assert frame["temp"] == 350

    # The failure mode, stated explicitly so the test documents it:
    # the low byte alone would have been 94.
    assert 350 & 0xFF == 94


@pytest.mark.parametrize("temp", [0, 1, 150, 255, 256, 350, 500, 550])
def test_u16_round_trips(temp):
    assert u16(temp & 0xFF, (temp >> 8) & 0xFF) == temp


def test_u32_is_little_endian():
    assert u32(0x01, 0x02, 0x03, 0x04) == 0x04030201
    assert u32(0, 0, 0, 0) == 0
    assert u32(0xFF, 0xFF, 0xFF, 0xFF) == 0xFFFFFFFF


# --- byte 33, the observed cycle ------------------------------------------

# From the instrumented cook of 2026-07-25. Fire state 2 = Startup,
# 3 = Running, 4 = Cool Down, 1 = Off.
OBSERVED_CYCLE = [
    ("10:50:29", 85, 2, 25),
    ("10:53:59", 86, 2, 50),
    ("11:01:59", 126, 2, 75),
    ("11:03:49", 150, 3, 100),
    ("11:04:43", 154, 4, 75),
    ("11:06:13", 171, 4, 50),
    ("11:07:27", 167, 1, 0),
]


@pytest.mark.parametrize("stamp,pit,fire_state,progress", OBSERVED_CYCLE)
def test_observed_cycle_decodes(stamp, pit, fire_state, progress):
    state = parse_status(
        build_frame(grill_temp=pit, fire_state=fire_state, fire_state_progress=progress)
    )
    assert state["temp"] == pit, stamp
    assert state["fireState"] == fire_state, stamp
    assert state["fireStatePercentage"] == progress, stamp


def test_fire_state_progress_is_quantised_to_25():
    """Every observed value is a multiple of 25, across a full cycle.

    Two cooks (2026-07-24 and 2026-07-25) produced only 0/25/50/75/100 across
    ~78 polls at a 10s cadence. This guards the "step N of 4" display against a
    future change that starts emitting intermediate values.
    """
    for _, _, _, progress in OBSERVED_CYCLE:
        assert progress % 25 == 0
        assert 0 <= progress <= 100


def test_progress_peaks_exactly_at_the_startup_to_running_edge():
    """100 lands on the Startup -> Running transition, not before or after."""
    startup = [row for row in OBSERVED_CYCLE if row[2] == 2]
    assert all(row[3] < 100 for row in startup), "progress hit 100 while still Startup"
    running = next(row for row in OBSERVED_CYCLE if row[2] == 3)
    assert running[3] == 100


# --- failure handling -----------------------------------------------------


def test_short_frame_raises_rather_than_returning_partial_data():
    """A partial dict is indistinguishable from a grill reporting those values."""
    with pytest.raises(GmgError):
        parse_status(bytes(STATUS_MIN_LEN - 1))


def test_empty_frame_raises():
    with pytest.raises(GmgError):
        parse_status(b"")


def test_minimum_length_frame_parses():
    """34 bytes is the shortest usable frame: the parser reads through byte 33."""
    state = parse_status(build_frame(length=STATUS_MIN_LEN))
    assert state["fireStatePercentage"] == 25


# --- firmware -------------------------------------------------------------


def test_firmware_reply_is_returned_verbatim():
    """The exact reply observed from hardware on 2026-07-30.

    The leading ``UN`` may be a command echo, but ``UL!`` does not echo, so
    stripping it would be a guess. Verbatim until proven otherwise.
    """
    assert parse_firmware(b"UNJB02SUF0_2.3") == "UNJB02SUF0_2.3"


def test_firmware_rejects_non_utf8():
    with pytest.raises(GmgError):
        parse_firmware(b"\xff\xfe\x00")


def test_firmware_rejects_empty():
    with pytest.raises(GmgError):
        parse_firmware(b"")


@pytest.mark.parametrize(
    "firmware,model",
    [
        ("UNJB02SUF0_2.3", "Jim Bowie"),  # verified on hardware 2026-07-30
        ("UNDB02SUF0_2.3", "Daniel Boone"),  # corroborated designator, unseen
        ("UNXX02SUF0_2.3", None),  # unknown prefix must not become a guess
        ("UN", None),
        ("", None),
    ],
)
def test_model_is_conservative(firmware, model):
    assert model_for(firmware) == model


def test_firmware_rejects_unprintable():
    """Binary junk (e.g. a stray status frame) must not become a version string."""
    with pytest.raises(GmgError):
        parse_firmware(b"\x0c\x142\x16\x19\x15\x19")


# --- polling cadence ------------------------------------------------------


@pytest.mark.parametrize(
    "state,expected",
    [
        ({"powerState": 0}, POLL_IDLE),
        ({"powerState": 1}, POLL_ACTIVE),
        ({"powerState": 2}, POLL_ACTIVE),
        ({"powerState": 3}, POLL_ACTIVE),
        ({"powerState": None}, POLL_ACTIVE),
        ({}, POLL_ACTIVE),
        (None, POLL_ACTIVE),
    ],
)
def test_poll_interval(state, expected):
    """Unknown state polls sooner: if we do not know, look again quickly."""
    assert poll_interval_for(state) == expected
