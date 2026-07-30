# Notice: origin and attribution

## Where this came from

This library began as the protocol half of a `gmg` Home Assistant custom
integration, itself a fork of
[`jwhitby91/gmg_home_assistant`](https://github.com/jwhitby91/gmg_home_assistant)
by **Jason (jwhitby91)**. That work came first and made everything here possible.

**That repository carries no licence** - no file, no header, no mention anywhere,
and GitHub's metadata reports `licenseInfo: null`. Under default copyright that
is all rights reserved, so a derivative work could not be redistributed. It has
been inactive since 2023-01-27, with no public activity on the account since
2023-12-04 and no contact channel published, so asking was unlikely to resolve it.

## How that was addressed

By rewriting, not by asking. Measured 2026-07-29 against the original file:

| | |
|---|---|
| Substantive lines in `gmg-local` | **403** |
| Appearing verbatim in the original | **39 (10%)** |
| Of those, non-trivial | **8** |

All eight remaining are lines with exactly one reasonable form in Python:

```python
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)      # x2
sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
data, _ = sock.recvfrom(1024)
if not ipaddress.ip_address(ip):
self._serial_number = serial_number
return self._serial_number                                    # x2
```

There is no alternative way to open a UDP socket, enable broadcast, or receive a
datagram. Code whose expression is dictated by the operation it performs, and
short phrases, are not protectable - so no original expression from the upstream
work remains here.

**The protocol itself was never the issue.** Byte offsets, command strings and
port numbers are facts about a device, not authorship, and they are independently
corroborated across four implementations.

Everything of substance in this package is original: the 16-bit temperature fix,
the short-packet retry, the I/O lock, the adaptive poll cadence, the pure/impure
module split, the parser's refusal to return partial data, and every test.

**This is a practical assessment, not legal advice.**

## Attribution stands regardless

Rewriting removes a licensing constraint; it does not remove a debt. Jason's
integration is why this device is usable from Home Assistant at all, and the
credit belongs in the README as long as this package exists.

Protocol reference cross-checked against
[`brandenc40/green-mountain-grill`](https://github.com/brandenc40/green-mountain-grill)
(Go) and `gmg` 0.0.4 on PyPI by **Christopher McKay**. Both independently place
the fire-state progress value at byte 33; `gmg` 0.0.4 additionally labels offsets
48 and 50 as pellet alarms, bytes this library receives but does not yet decode.

## Still worth doing

Send Jason a courteous note - not to ask permission, but because his repository
is the one 26-starred result people find, it has a temperature bug that makes hot
grills read cold, and he may want to know a maintained successor exists. Costs
nothing, and it is the decent thing.
