"""A fake UDP socket, so the I/O half can be tested without a grill.

`grill.py` and `discovery.py` are the modules most likely to break on a network
change and the hardest to debug remotely, which is exactly why they should not
be the untested half. Everything here substitutes for the real socket at the
module level; no packets leave the machine.
"""

from __future__ import annotations

import socket
from typing import Any, Callable

import pytest


class FakeSocket:
    """Stands in for ``socket.socket``, scripted by a reply function.

    ``replies`` is called with each outgoing message and returns either bytes
    (delivered to the next ``recvfrom``), or ``None`` to raise
    ``socket.timeout`` - which is how both real silence and the end of a
    discovery sweep are signalled.
    """

    def __init__(self, replies: Callable[[bytes], bytes | None]) -> None:
        self._replies = replies
        self._inbox: list[bytes] = []
        self.sent: list[tuple[bytes, tuple[str, int]]] = []
        self.closed = False
        self.timeout: float | None = None
        self.bound: tuple[str, int] | None = None
        self.sockopts: list[tuple[int, int, int]] = []

    # --- the socket API actually exercised -------------------------------

    def settimeout(self, value: float) -> None:
        self.timeout = value

    def setsockopt(self, level: int, opt: int, value: int) -> None:
        self.sockopts.append((level, opt, value))

    def bind(self, addr: tuple[str, int]) -> None:
        self.bound = addr

    def sendto(self, data: bytes, addr: tuple[str, int]) -> int:
        self.sent.append((data, addr))
        reply = self._replies(data)
        if reply is not None:
            self._inbox.append(reply)
        return len(data)

    def recvfrom(self, _bufsize: int) -> tuple[bytes, tuple[str, int]]:
        if not self._inbox:
            raise socket.timeout("no reply")
        return self._inbox.pop(0), ("10.0.0.9", 8080)

    def close(self) -> None:
        self.closed = True


@pytest.fixture
def fake_socket(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[FakeSocket]]:
    """Install a FakeSocket factory; returns every socket that gets created.

    Also pins ``getaddrinfo``/``gethostname`` so discovery sees one predictable
    interface instead of whatever the test machine happens to have.
    """

    def install(replies: Callable[[bytes], bytes | None], interfaces: int = 1):
        created: list[FakeSocket] = []

        def factory(*_args: Any, **_kwargs: Any) -> FakeSocket:
            sock = FakeSocket(replies)
            created.append(sock)
            return sock

        monkeypatch.setattr(socket, "socket", factory)
        monkeypatch.setattr(socket, "gethostname", lambda: "testhost")
        monkeypatch.setattr(
            socket,
            "getaddrinfo",
            lambda **_kw: [
                (None, None, None, None, (f"10.0.0.{n + 1}", 0)) for n in range(interfaces)
            ],
        )
        return created

    return install


def _status_frame(
    *,
    grill_temp: int = 225,
    power_state: int = 1,
    fire_state: int = 3,
    progress: int = 100,
    length: int = 52,
) -> bytes:
    """A status frame at the documented offsets."""
    f = bytearray(length)
    f[2] = grill_temp & 0xFF
    f[3] = (grill_temp >> 8) & 0xFF
    f[30] = power_state
    f[32] = fire_state
    f[33] = progress
    return bytes(f)


@pytest.fixture
def frame():
    """Builds a status frame at the documented offsets."""
    return _status_frame
