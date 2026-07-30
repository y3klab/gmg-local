"""Protocol constants for Green Mountain Grills Wi-Fi controllers.

Offsets are into the status frame returned by the ``UR001!`` poll. They are
facts about the wire format, established by observation and corroborated across
several independent implementations - see README.md for provenance.
"""

from __future__ import annotations

#: UDP port the grill listens on.
UDP_PORT = 8080

# --- commands -------------------------------------------------------------

CODE_SERIAL = b"UL!"
CODE_STATUS = b"UR001!"
CODE_POWER_ON = b"UK001!"
CODE_POWER_ON_COLD_SMOKE = b"UK002!"
CODE_POWER_OFF = b"UK004!"

# --- temperature bounds ---------------------------------------------------

MIN_TEMP_F = 150
MAX_TEMP_F = 500

MIN_TEMP_F_PROBE = 32
MAX_TEMP_F_PROBE = 257

#: Sent as a probe target to mean "no target" rather than a real temperature.
#: Deliberately below :data:`MIN_TEMP_F_PROBE`, so range checks must allow it
#: explicitly.
#:
#: .. warning::
#:    UNVERIFIED against hardware - whether the grill treats 0 as "clear" or
#:    simply ignores it has not been tested.
PROBE_TARGET_CLEAR = 0

# --- status frame layout --------------------------------------------------

OFFSET_GRILL_TEMP = 2  # + 3 high byte
OFFSET_PROBE_1_TEMP = 4  # + 5 high byte
OFFSET_GRILL_SET_TEMP = 6  # + 7 high byte
OFFSET_API_VERSION = 8
OFFSET_PROBE_2_TEMP = 16  # + 17 high byte
OFFSET_PROBE_2_SET_TEMP = 18  # + 19 high byte
OFFSET_WARN_STATE = 24  # 4-byte little-endian, 24..27
OFFSET_PROBE_1_SET_TEMP = 28  # + 29 high byte
OFFSET_POWER_STATE = 30
OFFSET_FIRE_STATE = 32
OFFSET_FIRE_STATE_PROGRESS = 33

#: Shortest frame the parser can read, given the highest offset it touches (33).
#:
#: A healthy grill answers ``UR001!`` with **52** bytes. Anything shorter is a
#: truncated or stray datagram, not data: retry it like a timeout rather than
#: parsing it. Making the parser strict without this guard once turned a rare
#: short packet into "every entity unavailable".
STATUS_MIN_LEN = 34

#: Frame length actually observed from a healthy grill. Bytes 34..51 are
#: received and currently undecoded; ``gmg`` 0.0.4 on PyPI labels offsets 48
#: and 50 as pellet alarms, which is unverified here.
STATUS_OBSERVED_LEN = 52

# --- enumerations ---------------------------------------------------------

#: Byte 30. Values confirmed against hardware.
POWER_STATE = {
    0: "Off",
    1: "On",
    2: "Fan",
    3: "Cold Smoke",
}

#: Byte 32. Matches the enumeration in brandenc40/green-mountain-grill, which
#: is validated there (unlike byte 33).
FIRE_STATE = {
    0: "Default",
    1: "Off",
    2: "Startup",
    3: "Running",
    4: "Cool Down",
    5: "Fail",
    198: "Cold Smoke",
}

# --- polling --------------------------------------------------------------

#: Seconds between polls while the grill is doing something.
POLL_ACTIVE = 10

#: Seconds between polls while the grill is off. A cooking grill is worth
#: watching closely; an idle one is not worth a round-trip every 10s for hours.
POLL_IDLE = 60
