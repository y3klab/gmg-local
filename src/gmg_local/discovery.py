"""Finding grills on the network."""

from __future__ import annotations

import logging
import socket

from .const import CODE_SERIAL, UDP_PORT
from .grill import Grill

_LOGGER = logging.getLogger(__name__)


def discover(
    timeout: float = 1,
    ip_bind_address: str = "0.0.0.0",
    target: str | None = None,
) -> list[Grill]:
    """Broadcast for grills and return everything that answers.

    :param timeout: seconds to wait for replies on each interface.
    :param ip_bind_address: extra address to bind, alongside every local one.
    :param target: send a **unicast** probe to this address instead of
        broadcasting. Required across VLANs, where a broadcast dies at the L2
        edge but the grill still answers a directed datagram.

    Binds every local IPv4 address in turn, because a broadcast from the wrong
    interface reaches nothing and there is no reliable way to know in advance
    which interface faces the grill.
    """
    interfaces = socket.getaddrinfo(
        host=socket.gethostname(), port=None, family=socket.AF_INET
    )
    all_ips = [ip[-1][0] for ip in interfaces]
    all_ips.append(ip_bind_address)

    found: list[Grill] = []
    seen: set[str] = set()

    for ip in all_ips:
        _LOGGER.debug("Creating socket for IP: %s", ip)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Port 0 lets the OS pick any free port.
            sock.bind((ip, 0))
            # Each recv gets the full timeout period.
            sock.settimeout(timeout)
            sock.sendto(CODE_SERIAL, (target or "<broadcast>", UDP_PORT))
            _LOGGER.debug("Probe sent from %s", ip)

            while True:
                data, (address, ret_socket) = sock.recvfrom(1024)
                try:
                    response = data.decode("utf-8")
                except UnicodeDecodeError:
                    continue

                _LOGGER.debug(
                    "Received a response %s:%s, %s", address, ret_socket, response
                )

                # A GMG serial number always starts with 'GMG'.
                if not response.startswith("GMG"):
                    continue
                if response in seen:
                    _LOGGER.debug("Grill %s is a duplicate, skipping", response)
                    continue

                seen.add(response)
                found.append(Grill(address, response))

        except socket.timeout:
            # Expected: this is how the recv loop above terminates.
            _LOGGER.debug("Socket on %s timed out", ip)
        except OSError as err:
            _LOGGER.debug("Could not probe from %s: %s", ip, err)
        finally:
            sock.close()

    _LOGGER.debug("Found %d grills", len(found))
    return found


#: Backwards-compatible alias for :func:`discover`.
grills = discover
