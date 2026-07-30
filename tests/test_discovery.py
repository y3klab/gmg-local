"""Tests for discovery - the broadcast sweep and what it accepts as a grill."""

from __future__ import annotations

import socket

import pytest

from gmg_local import discover, grills
from gmg_local.const import CODE_SERIAL, UDP_PORT


def test_finds_a_grill_that_answers(fake_socket):
    fake_socket(lambda msg: b"GMG12345678" if msg == CODE_SERIAL else None)
    found = discover()
    assert len(found) == 1
    assert found[0].serial_number == "GMG12345678"
    assert found[0].ip == "10.0.0.9"


def test_finds_nothing_when_nothing_answers(fake_socket):
    fake_socket(lambda msg: None)
    assert discover() == []


def test_ignores_replies_that_are_not_grills(fake_socket):
    """Anything on the LAN can answer a broadcast; only GMG serials count."""
    fake_socket(lambda msg: b"SOMETHING-ELSE")
    assert discover() == []


def test_ignores_undecodable_replies(fake_socket):
    """A binary reply must not raise UnicodeDecodeError out of the sweep."""
    fake_socket(lambda msg: b"\xff\xfe\x00\x01")
    assert discover() == []


def test_deduplicates_a_grill_answering_on_several_interfaces(fake_socket):
    """The same grill replies to every interface we probe from.

    Without dedup it would be returned once per interface, and each copy would
    poll independently - which the hardware cannot serve.
    """
    fake_socket(lambda msg: b"GMG12345678", interfaces=3)
    found = discover()
    assert len(found) == 1


def test_probes_every_local_interface(fake_socket):
    """A broadcast from the wrong interface reaches nothing, and there is no
    reliable way to know in advance which one faces the grill."""
    created = fake_socket(lambda msg: None, interfaces=3)
    discover()
    # one per interface, plus the extra ip_bind_address pass
    assert len(created) == 4
    assert [s.bound[0] for s in created] == ["10.0.0.1", "10.0.0.2", "10.0.0.3", "0.0.0.0"]


def test_broadcasts_by_default(fake_socket):
    created = fake_socket(lambda msg: None)
    discover()
    assert created[0].sent[0] == (CODE_SERIAL, ("<broadcast>", UDP_PORT))


def test_unicasts_when_given_a_target(fake_socket):
    """Required across VLANs - a broadcast dies at the L2 edge, but the grill
    still answers a directed datagram."""
    created = fake_socket(lambda msg: None)
    discover(target="10.2.10.200")
    assert created[0].sent[0] == (CODE_SERIAL, ("10.2.10.200", UDP_PORT))


def test_enables_the_broadcast_socket_option(fake_socket):
    created = fake_socket(lambda msg: None)
    discover()
    assert (socket.SOL_SOCKET, socket.SO_BROADCAST, 1) in created[0].sockopts


def test_closes_every_socket_it_opens(fake_socket):
    """The sweep opens one per interface; leaking them would be per-call."""
    created = fake_socket(lambda msg: None, interfaces=3)
    discover()
    assert all(s.closed for s in created)


def test_a_failing_interface_does_not_abort_the_sweep(fake_socket, monkeypatch):
    """One unusable interface must not hide a grill on another."""
    real = []

    class Boom:
        def __init__(self):
            self.closed = False
            self.answered = False

        def setsockopt(self, *_a):
            pass

        def bind(self, addr):
            if addr[0] == "10.0.0.1":
                raise OSError("cannot assign requested address")

        def settimeout(self, *_a):
            pass

        def sendto(self, *_a):
            real.append(1)

        def recvfrom(self, *_a):
            # Answer once, then time out - otherwise the sweep's `while True`
            # never terminates. A fake that always replies is an infinite loop.
            if real and not self.answered:
                self.answered = True
                return b"GMG12345678", ("10.0.0.9", 8080)
            raise socket.timeout

        def close(self):
            self.closed = True

    monkeypatch.setattr(socket, "socket", lambda *a, **kw: Boom())
    monkeypatch.setattr(socket, "gethostname", lambda: "testhost")
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda **_kw: [(None, None, None, None, ("10.0.0.1", 0)),
                       (None, None, None, None, ("10.0.0.2", 0))],
    )
    found = discover()
    assert len(found) == 1  # found via the second interface


def test_grills_is_a_back_compat_alias():
    assert grills is discover
