"""gmg-local - talk to a Green Mountain Grills Wi-Fi pellet grill on your LAN.

Local UDP only. No cloud account, no vendor API, no internet.

    from gmg_local import discover

    for grill in discover():
        print(grill.serial_number, grill.status()["temp"])
"""

from __future__ import annotations

from .const import (
    FIRE_STATE,
    MAX_TEMP_F,
    MAX_TEMP_F_PROBE,
    MIN_TEMP_F,
    MIN_TEMP_F_PROBE,
    POLL_ACTIVE,
    POLL_IDLE,
    POWER_STATE,
    PROBE_TARGET_CLEAR,
    STATUS_MIN_LEN,
    STATUS_OBSERVED_LEN,
    UDP_PORT,
)
from .discovery import discover, grills
from .grill import Grill
from .protocol import (
    GmgError,
    model_for,
    parse_firmware,
    parse_status,
    poll_interval_for,
    u16,
    u32,
)

__version__ = "0.3.0"

#: Backwards-compatible alias. The class was lowercase ``grill`` in the code
#: this was extracted from; ``Grill`` is the canonical name.
grill = Grill

__all__ = [
    "Grill",
    "GmgError",
    "discover",
    "grills",
    "grill",
    "model_for",
    "parse_firmware",
    "parse_status",
    "poll_interval_for",
    "u16",
    "u32",
    "FIRE_STATE",
    "POWER_STATE",
    "MIN_TEMP_F",
    "MAX_TEMP_F",
    "MIN_TEMP_F_PROBE",
    "MAX_TEMP_F_PROBE",
    "PROBE_TARGET_CLEAR",
    "POLL_ACTIVE",
    "POLL_IDLE",
    "STATUS_MIN_LEN",
    "STATUS_OBSERVED_LEN",
    "UDP_PORT",
    "__version__",
]
