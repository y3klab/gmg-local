"""Pure protocol functions: no sockets, no clock, no I/O.

Everything here is a deterministic function of its input, so it can be tested
without a grill, without a network, and without Home Assistant.
"""

from __future__ import annotations

import logging
from typing import Any, Sequence

from .const import (
    OFFSET_API_VERSION,
    OFFSET_FIRE_STATE,
    OFFSET_FIRE_STATE_PROGRESS,
    OFFSET_GRILL_SET_TEMP,
    OFFSET_GRILL_TEMP,
    OFFSET_POWER_STATE,
    OFFSET_PROBE_1_SET_TEMP,
    OFFSET_PROBE_1_TEMP,
    OFFSET_PROBE_2_SET_TEMP,
    OFFSET_PROBE_2_TEMP,
    OFFSET_WARN_STATE,
    POLL_ACTIVE,
    POLL_IDLE,
)

_LOGGER = logging.getLogger(__name__)


class GmgError(Exception):
    """The grill could not be reached, or answered with something unusable."""


def u16(low: int, high: int) -> int:
    """Combine a little-endian 16-bit pair.

    GMG temperatures are 16-bit little-endian (low byte + high byte * 256).
    Reading only the low byte wraps anything above 255 - a 350 F grill reports
    as 94 F - which is the single most consequential bug in the older public
    implementations.
    """
    return ((int(high) & 0xFF) << 8) | (int(low) & 0xFF)


def u32(b0: int, b1: int, b2: int, b3: int) -> int:
    """Combine a little-endian 32-bit quad. Used by ``warnState`` (24..27)."""
    return (
        ((int(b3) & 0xFF) << 24)
        | ((int(b2) & 0xFF) << 16)
        | ((int(b1) & 0xFF) << 8)
        | (int(b0) & 0xFF)
    )


def parse_status(frame: Sequence[int]) -> dict[str, Any]:
    """Decode a status frame into a flat dict.

    :param frame: the raw bytes of a ``UR001!`` response, as a sequence of ints.
    :raises GmgError: if the frame is too short or otherwise unreadable.

    **A partial dict is never returned.** A short or garbled packet that decoded
    into ``{field: None, ...}`` would be indistinguishable from a grill genuinely
    reporting those values, so the whole parse fails instead and the caller keeps
    its last known-good reading.
    """
    try:
        state: dict[str, Any] = {
            # PowerState: 0 Off, 1 On, 2 Fan, 3 Cold Smoke.
            # 'on' is a legacy alias for 'powerState'; both are the same byte.
            "on": frame[OFFSET_POWER_STATE],
            "powerState": frame[OFFSET_POWER_STATE],
            "temp": u16(frame[OFFSET_GRILL_TEMP], frame[OFFSET_GRILL_TEMP + 1]),
            "grill_set_temp": u16(
                frame[OFFSET_GRILL_SET_TEMP], frame[OFFSET_GRILL_SET_TEMP + 1]
            ),
            "probe1_temp": u16(
                frame[OFFSET_PROBE_1_TEMP], frame[OFFSET_PROBE_1_TEMP + 1]
            ),
            "probe1_set_temp": u16(
                frame[OFFSET_PROBE_1_SET_TEMP], frame[OFFSET_PROBE_1_SET_TEMP + 1]
            ),
            "probe2_temp": u16(
                frame[OFFSET_PROBE_2_TEMP], frame[OFFSET_PROBE_2_TEMP + 1]
            ),
            "probe2_set_temp": u16(
                frame[OFFSET_PROBE_2_SET_TEMP], frame[OFFSET_PROBE_2_SET_TEMP + 1]
            ),
            "fireState": frame[OFFSET_FIRE_STATE],
            # Byte 33. GMG's own cloud API names this field `fireStateProgress`.
            # `fireStatePercentage` is retained as the emitted key for
            # compatibility with existing consumers.
            "fireStatePercentage": frame[OFFSET_FIRE_STATE_PROGRESS],
            "warnState": u32(
                frame[OFFSET_WARN_STATE],
                frame[OFFSET_WARN_STATE + 1],
                frame[OFFSET_WARN_STATE + 2],
                frame[OFFSET_WARN_STATE + 3],
            ),
            "apiVersion": frame[OFFSET_API_VERSION],
        }
    except Exception as err:
        raise GmgError(f"could not parse status frame: {err}") from err

    _LOGGER.debug("Parsed status: %s", state)
    return state


def parse_firmware(raw: bytes) -> str:
    """Decode a ``UN!`` reply into the grill's firmware string, verbatim.

    :param raw: the raw bytes of a ``UN!`` response.
    :raises GmgError: if the reply is empty or not printable UTF-8.

    Observed on hardware (Jim Bowie, 2026-07-30): ``b"UNJB02SUF0_2.3"``. The
    leading ``UN`` matches the command bytes and may be an echo, but ``UL!``
    does not echo its command, so stripping it would be a guess - the string is
    returned exactly as the grill sent it. The status frame's bytes 9-15,
    labelled ``FirmwareDetails`` upstream, are binary and unrelated on the
    hardware observed; ``UN!`` is the firmware source.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as err:
        raise GmgError(f"firmware reply is not UTF-8: {raw!r}") from err
    if not text or not text.isprintable():
        raise GmgError(f"firmware reply is empty or unprintable: {raw!r}")
    return text


#: Model prefixes at bytes 2-3 of the ``UN!`` reply (after the ``UN``).
#: Conservative on purpose: JB is verified against hardware (an owner-confirmed
#: Jim Bowie reporting ``UNJB02SUF0_2.3``, 2026-07-30); DB is corroborated by
#: GMG's own ``DBWF`` app-manual designator but has not been seen on hardware.
#: Anything else returns ``None`` rather than a guess.
_MODEL_PREFIXES = {
    "JB": "Jim Bowie",
    "DB": "Daniel Boone",
}


def model_for(firmware: str) -> str | None:
    """The grill model implied by a firmware string, or ``None`` if unknown.

    Pure and conservative: an unrecognised prefix is ``None``, never a guess.
    """
    if len(firmware) < 4:
        return None
    return _MODEL_PREFIXES.get(firmware[2:4])


def poll_interval_for(state: dict[str, Any] | None) -> int:
    """Seconds to wait before the next poll, given a parsed status dict.

    Active means the grill is doing something (On / Fan / Cold Smoke); Off is
    idle. A missing or unparsable ``powerState`` counts as active: if we do not
    know what the grill is doing, look again sooner rather than later.
    """
    if not state:
        return POLL_ACTIVE
    power = state.get("powerState")
    if power is None:
        return POLL_ACTIVE
    return POLL_IDLE if power == 0 else POLL_ACTIVE
