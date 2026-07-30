"""The grill itself: one device, one UDP conversation at a time."""

from __future__ import annotations

import ipaddress
import logging
import socket
import threading
from typing import Any

from .const import (
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
from .protocol import GmgError, parse_status

_LOGGER = logging.getLogger(__name__)


class Grill:
    """A single Green Mountain Grills Wi-Fi controller on the local network."""

    UDP_PORT = UDP_PORT
    MIN_TEMP_F = MIN_TEMP_F
    MAX_TEMP_F = MAX_TEMP_F
    MIN_TEMP_F_PROBE = MIN_TEMP_F_PROBE
    MAX_TEMP_F_PROBE = MAX_TEMP_F_PROBE
    PROBE_TARGET_CLEAR = PROBE_TARGET_CLEAR
    CODE_SERIAL = CODE_SERIAL
    CODE_STATUS = CODE_STATUS

    def __init__(self, ip: str, serial_number: str = "") -> None:
        if not ipaddress.ip_address(ip):
            raise ValueError(f"not a usable IPv4/IPv6 address: {ip!r}")

        _LOGGER.debug("Initializing grill %s with serial number %s", ip, serial_number)

        self._ip = ip
        self._serial_number = serial_number
        self.state: dict[str, Any] = {}

        # The grill serves ONE client at a time, so serialize our own traffic:
        # a status poll landing on top of a set_temp loses one of the two.
        self._io_lock = threading.Lock()

    @property
    def ip(self) -> str:
        """The grill's address on the network."""
        return self._ip

    @property
    def serial_number(self) -> str:
        """The serial number reported at discovery, e.g. ``GMG...``."""
        return self._serial_number

    # --- reads ------------------------------------------------------------

    def status(self, retries: int = 5) -> dict[str, Any]:
        """Poll once and return the decoded status.

        Retries on silence **and on junk**. The grill occasionally answers with a
        truncated datagram; that is a transport artifact, and parsing it would
        either raise or invent missing fields. It is treated exactly like a
        timeout.

        No caching and no stale-value grace period - the caller owns both.
        A raise means "this poll failed", not "the device is gone".
        """
        raw = None
        silent = 0
        short: list[int] = []

        for _ in range(retries):
            candidate = self.send(CODE_STATUS)
            if candidate is None:
                silent += 1
                continue
            if len(candidate) < STATUS_MIN_LEN:
                short.append(len(candidate))
                _LOGGER.debug(
                    "Short status packet from %s: %d bytes (need >= %d) - retrying",
                    self._ip,
                    len(candidate),
                    STATUS_MIN_LEN,
                )
                continue
            raw = candidate
            break

        if raw is None:
            raise GmgError(
                f"no usable status from grill at {self._ip} after {retries} tries "
                f"({silent} silent, {len(short)} too short: {short})"
            )

        self.state = parse_status(list(raw))
        return self.state

    def serial(self) -> str:
        """Ask the grill for its serial number, and cache it."""
        self._serial_number = self.send(CODE_SERIAL).decode("utf-8")
        return self._serial_number

    # --- writes -----------------------------------------------------------

    def set_temp(self, target_temp: int) -> bytes | None:
        """Set the grill's target temperature, in Fahrenheit."""
        if target_temp < MIN_TEMP_F or target_temp > MAX_TEMP_F:
            raise ValueError(
                f"grill target {target_temp}F outside {MIN_TEMP_F}-{MAX_TEMP_F}F"
            )
        return self.send(b"UT" + str(target_temp).encode() + b"!")

    def set_temp_probe(self, target_temp: int, probe_number: int) -> bytes | None:
        """Set a food probe's target temperature, in Fahrenheit.

        :data:`~gmg_local.const.PROBE_TARGET_CLEAR` (0) is allowed through as "no
        target"; every other value must be a physically valid probe temperature.

        .. warning::
           The grill **silently discards probe writes while it is off** - a write
           of 203 reads back as 0, with no error. Callers should not display a
           target the grill never accepted.
        """
        if target_temp != PROBE_TARGET_CLEAR and (
            target_temp < MIN_TEMP_F_PROBE or target_temp > MAX_TEMP_F_PROBE
        ):
            raise ValueError(
                f"probe target {target_temp}F outside "
                f"{MIN_TEMP_F_PROBE}-{MAX_TEMP_F_PROBE}F (or {PROBE_TARGET_CLEAR} to clear)"
            )

        if probe_number == 1:
            message = b"UF" + str(target_temp).encode() + b"!"
        elif probe_number == 2:
            message = b"Uf" + str(target_temp).encode() + b"!"
        else:
            raise ValueError(f"Probe number must be 1 or 2, got {probe_number}")

        return self.send(message)

    def power_on(self) -> bytes | None:
        """Power on the grill."""
        return self.send(CODE_POWER_ON)

    def power_on_cool(self) -> bytes | None:
        """Power on the grill in cold smoke mode."""
        return self.send(CODE_POWER_ON_COLD_SMOKE)

    def power_off(self) -> bytes | None:
        """Power off the grill. It runs its own cool-down afterwards."""
        return self.send(CODE_POWER_OFF)

    # --- transport --------------------------------------------------------

    def send(self, message: bytes, timeout: float = 1) -> bytes | None:
        """Send one UDP datagram and return the reply, or ``None`` on timeout.

        One grill, one conversation at a time - see ``_io_lock``.
        """
        data = None
        with self._io_lock:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                sock.settimeout(timeout)
                sock.sendto(message, (self._ip, UDP_PORT))
                data, _ = sock.recvfrom(1024)
            except socket.timeout:
                _LOGGER.debug("Timeout waiting for %s to answer %s", self._ip, message)
            except OSError as err:
                _LOGGER.debug("Error talking to %s: %s", self._ip, err)
            finally:
                sock.close()

        return data

    def __repr__(self) -> str:
        return f"<Grill {self._serial_number or 'unknown'} at {self._ip}>"
