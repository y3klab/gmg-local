# gmg-local

Local UDP client for **Green Mountain Grills** Wi-Fi pellet grills.

No cloud account, no vendor API, no internet. It talks to the grill on your LAN
and nothing else - just delicious data.

```python
from gmg_local import discover

for grill in discover():
    state = grill.status()
    print(grill.serial_number, state["temp"], "F")
```

## Install

```bash
pip install gmg-local
```

Requires Python 3.11+. No dependencies.

## API

| | |
|---|---|
| `discover(timeout=1, ip_bind_address="0.0.0.0", target=None)` | Broadcast for grills. Pass `target` to unicast across VLANs, where broadcast dies at the L2 edge. |
| `Grill.status(retries=5)` | One poll, decoded. Retries on silence **and** on junk. |
| `Grill.firmware(retries=5)` | The firmware string (`UN!`), verbatim - e.g. `UNJB02SUF0_2.3`. Same retry contract as `status()`. |
| `model_for(firmware)` | Pure. `"Jim Bowie"` for a `JB` firmware prefix, `None` for anything unrecognized. |
| `Grill.set_temp(f)` / `set_temp_probe(f, n)` | Targets, in Fahrenheit. |
| `Grill.power_on()` / `power_on_cool()` / `power_off()` | Cold smoke is `power_on_cool`. |
| `parse_status(frame)` | Pure. No sockets, no clock - testable without a grill. |
| `poll_interval_for(state)` | 10s while cooking, 60s while off. |

## What the status frame contains

A healthy grill answers `UR001!` with **52 bytes**; this library decodes through
byte 33. Rows marked *not parsed* are documented here but not returned by
`parse_status()`.

Temperatures are **16-bit little-endian pairs**. Reading only the low byte wraps
anything above 255, so a 350 °F grill reports as 94 °F - `u16(94, 1) == 350`.

| offset | field | notes |
|---|---|---|
| 2, 4, 6 | grill temp, probe 1, setpoint | 16-bit LE pairs |
| 8 | API version | |
| 9-15 | stored settings, *inferred* | not parsed; binary, not firmware text; see below |
| 16, 18 | probe 2 temp and setpoint | |
| 20-23 | profile time remaining | not parsed; GMG's `profileRemainingTime`; see below |
| 24-27 | warn state | 32-bit LE; GMG's `warningCode`; byte 24 `0x80` is **low pellet**, see below |
| 28 | probe 1 setpoint | |
| 30 | power state | 0 Off, 1 On, 2 Fan, 3 Cold Smoke |
| 31 | grill mode | not parsed; GMG's `grillMode`; see below |
| 32 | fire state | 0 Default, 1 Off, 2 Startup, 3 Running, 4 Cool Down, 5 Fail, 198 Cold Smoke |
| 33 | **fire state progress** | see below |
| 34 | profile end mode | not parsed; GMG's `profileEndMode`; see below |
| 35 | **undecoded** | `0x03` on `SUF0_2.3` firmware, zero on `DB020002_1.2` |
| 36-40 | **undecoded** | zero, except byte 40 is `0x03` on `DB020002_1.2` |
| 41-51 | **firmware text** | ASCII; not parsed; see below |

### Byte 24: low pellet

Bytes 24-27 are GMG's own field, not a community guess: GMG's decompiled
Android app reads them as `mWarnCode`, and GMG's cloud API calls the field
`warningCode`. This library returns it as `warnState`.

**Byte 24 reads `0x80` while the hopper's low pellet sensor is tripped**, so
`warnState` reads 128. This is confirmed on two independent firmware
generations: `UNJB02SUF0_2.3` on the Jim Bowie [below](#captured-frames), and
`UNDB020002_1.2` on the Daniel Boone captured by GitHub user `m3rrym4n`. On the
Jim Bowie, tripping the sensor moved byte 24 from `0x00` to `0x80` and changed
nothing else in the frame. On the Daniel Boone, byte 24 was `0x80` while
tripped and `0x00` after release; the two captures are a matched pair from one
session, with the grill cold and off and the integration disabled. Bytes 25-27
stayed zero.

**It clears itself.** Refilling the hopper returned byte 24 to `0x00`, so it is
the sensor's live state, not a latched alarm, and there is nothing to
acknowledge or reset. That clear was seen with the grill already switched off;
clearing mid cook is expected but not yet observed directly.

An independent 2017 tcpdump capture in
[`Aenima4six2/gmg`](https://github.com/Aenima4six2/gmg) (`doc/decode.txt`), taken
on the older 36-byte frame with the grill off, shows the same thing: byte 24
goes to `0x80` and nothing else changes. Three captures, across nine years and
two frame formats, agree.

**The cloud encodes it differently.** GMG's cloud API reports low pellet as
`warningCode` 2, not 128. The cloud re-encodes the field; on the local wire the
value is `0x80`. A check ported from a cloud client will test the wrong value.

**The other bits are unknown.** The decompiled app names eight warnings:
`FAN_OVERLOADED`, `AUGER_OVERLOADED`, `IGNITOR_OVERLOADED`, `BATTERY_LOW`,
`FAN_DISCONNECTED`, `AUGER_DISCONNECTED`, `IGNITOR_DISCONNECTED` and
`LOW_PELLET`. *Inference:* if those are bit positions in byte 24, in that order,
`LOW_PELLET` is bit 7, which is `0x80`; that is the only reading under which the
names and the observation agree. None of the other seven has been observed, and
public implementations disagree on their values. This library returns
`warnState` raw and names no bits.

### Bytes 41-51: firmware text

Bytes 41-51 hold the grill's `UN!` reply in ASCII, without the leading `UN` and
without the underscore. Both captured frames follow the rule; the Jim Bowie's
was predicted from it before that frame was taken.

| grill | `UN!` reply | bytes 41-51 |
|---|---|---|
| Daniel Boone Prime | `UNDB020002_1.2` | `DB0200021.2` |
| Jim Bowie | `UNJB02SUF0_2.3` | `JB02SUF02.3` |

Both come to exactly 11 characters, the width of the field. This library does
not parse it; `Grill.firmware()` reads `UN!` and remains the supported source.

`gmg` 0.0.4 defines `pelletAlarm1 = 48` and `pelletAlarm2 = 50`, though its own
code never reads them. Those numbers are character positions in a hex string,
carried over from `Aenima4six2/gmg`'s JavaScript client, which reads the frame
as hex. Hex position 48 is byte 24: the labels point at the warn field, where
low pellet does live. Read as byte offsets into a 52-byte frame, as this
table's offsets are, 48 and 50 fall inside the firmware string instead.

### Bytes 34-40: the wandering `0x03`

Between the fire state and the firmware text, one byte reads `0x03`. It sits at
byte 35 on `SUF0_2.3` firmware - the Jim Bowie below, and a Daniel Boone frame
on `DB02SUF0_2.3` published with `gmg` 0.0.4 - and at byte 40 on the Daniel
Boone Prime's older `DB020002_1.2`. Its position follows firmware, not model,
now evidenced by the matched tripped and clear pair from one Daniel Boone device
and session as well as the frames collected separately. What it means is unknown. The rest of 34-40 reads zero on
every 52-byte frame seen.

### Bytes 20-23, 31 and 34: profile fields

GMG's Android app and cloud API name these. A profile is GMG's programmed
multi-step cook.

| offset | app | cloud |
|---|---|---|
| 20-23 | `mCurveRemainTime` (handed to a countdown) | `profileRemainingTime` |
| 31 | `mGrillMode` | `grillMode` |
| 34 | `mProfileEnd` | `profileEndMode` |

Every capture so far, here and in other implementations, reads `ff ff ff ff`
at 20-23, and none was taken with a profile running, so a live countdown has
never been seen on the wire and its encoding is unknown. Bytes 31 and 34 read
zero in both captures below. The names are GMG's; what values they take is not
yet observed.

### Bytes 9-15: probably stored settings (inference)

Bytes 9-15 read `0b 14 32 19 19 19 19` on the Daniel Boone Prime and
`0c 14 32 16 19 15 19` on the Jim Bowie. The Jim Bowie's seven bytes are
identical, byte for byte, to a reading of the same grill 87 days earlier
(2026-07-30). They are binary, not firmware text, and they do not advance, so
they are not a clock or a counter.

*Inference, not a confirmed reading:*
[`facultymatt/gmg-js`](https://github.com/facultymatt/gmg-js) decodes them as a
stored settings block: byte 9 carries pizza mode and a mode code, byte 10 the
grill temperature adjust, and bytes 12-15 the probe adjusts. The adjusts are
stored with a bias, so a raw 20 (`0x14`) means zero for the grill and 25
(`0x19`) means zero for a probe. That fits the bytes never changing, and it
fits both grills reading `0x14` at byte 10. Nobody has yet changed a setting
and watched these bytes move.

### Captured frames

Both genuine full frames this project has. Read at the documented offsets,
every decoded field lands on a plausible value for a grill that is switched
off.

#### Daniel Boone Prime

Captured by **m3rrym4n** and posted in
[y3klab/gmg-ha#2](https://github.com/y3klab/gmg-ha/issues/2).

- **Grill:** Green Mountain Grills Daniel Boone Prime WiFi
- **Firmware:** `UNDB020002_1.2` (`UN!` reply)
- **Date:** 2026-10-18
- **Conditions:** grill off after a cook, no other client connected (Home
  Assistant integration disabled, phone app uninstalled). 29 replies to
  `UR001!` at 5 second intervals, all 52 bytes and byte-identical.

```
offset  0: 55 52 43 00 59 02 96 00 05 0b 14 32 19 19 19 19
offset 16: 59 02 00 00 ff ff ff ff 00 00 00 00 00 00 00 00
offset 32: 01 00 00 00 00 00 00 00 03 44 42 30 32 30 30 30
offset 48: 32 31 2e 32
```

Grill temp 67, setpoint 150, API version 5, warn state 0, probe setpoints 0,
power state 0 (Off), fire state 1 (Off), fire state progress 0. Power Off
alongside fire state Off, not Default, after a cook is consistent with the
enumerations above.

Low pellet sensor captures from the same grill and session, with the grill cold
and off, the integration disabled, and the hopper sensor held tripped for about
two minutes:

- **Tripped:**
```
55 52 45 00 59 02 96 00 05 0b 14 32 19 19 19 19 59 02 00 00 ff ff ff ff 80 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00 03 44 42 30 32 30 30 30 32 31 2e 32
```
- **Clear:**
```
55 52 46 00 59 02 96 00 05 0b 14 32 19 19 19 19 59 02 00 00 ff ff ff ff 00 00 00 00 00 00 00 00 01 00 00 00 00 00 00 00 03 44 42 30 32 30 30 30 32 31 2e 32
```

The only differences are byte 24 and the grill temperature in bytes 2 and 3:
69 F in the tripped frame and 70 F in the clear frame.

#### Jim Bowie

Captured from the maintainer's own grill.

- **Grill:** Green Mountain Grills Jim Bowie
- **Firmware:** `UNJB02SUF0_2.3` (`UN!` reply, read in the same session)
- **Date:** 2026-10-25
- **Conditions:** grill off.

```
offset  0: 55 52 55 00 5f 02 96 00 06 0c 14 32 16 19 15 19
offset 16: 61 02 00 00 ff ff ff ff 00 00 00 00 00 00 00 00
offset 32: 01 00 00 03 00 00 00 00 00 4a 42 30 32 53 55 46
offset 48: 30 32 2e 33
```

Grill temp 85, setpoint 150 (kept while off), API version 6, warn state 0,
probe setpoints 0, power state 0 (Off), fire state 1 (Off), fire state progress
0.

**Unplugged probes report a per-unit value, not one sentinel.** With nothing
plugged in, the Daniel Boone Prime reads **601** on both probes, and the Jim
Bowie reads **607** on probe 1 and **609** on probe 2 in the same frame. Other
implementations record 557, 601 and 608. The number is an open-circuit reading
that differs between grills and between the probe sockets of one grill. This
library returns the raw value and treats no number specially.

### Byte 33

Emitted as `fireStatePercentage`. GMG's own cloud API names this field
**`fireStateProgress`**, paired with `fireState`.

It is a four-step progress marker through *whatever fire state the grill is
currently in*. Across a full instrumented cycle it ran `25 → 50 → 75 → 100`
during Startup, hitting 100 at the exact second the grill switched to Running,
then `75 → 50 → 0` through Cool Down, hitting 0 as the fan stopped.

Two readings are ruled out by that data:

- **Not a startup-stage index.** A stage counter does not run backwards.
- **Not a pellet-hopper level.** A hopper does not fill during ignition and
  empty when the fan stops. One public implementation labels it `hopper_pct`
  and ships it as a pellet gauge; it reads 100% on a hot grill and 0% on a cold
  one.

**What each 25% step physically means is unknown**, and is not in the packet.
Display the step number; do not invent labels.

## Things the hardware does that will surprise you

- **Probe writes are silently discarded while the grill is off.** Write 203, read
  back 0. No error, no acknowledgement.
- **The grill serves one client at a time.** Concurrent conversations lose
  messages, so all I/O here is serialized behind a lock.
- **Short datagrams happen.** They are a transport artifact, not data. Parsing
  one either raises or invents fields; this library retries instead.
- **Temperature keeps rising after the fire is cut** - roughly 18 °F over a
  minute in one observed shutdown.

## Tests

```bash
pip install -e ".[dev]" && pytest
```

The fixtures are **reconstructed** - real decoded observations re-encoded at the
documented offsets - not captured frames. They prove the parser is self-consistent
with observed behavior, not that the offsets are correct. Offsets are
corroborated across four independent implementations.

Two genuine 52-byte captures now exist ([above](#captured-frames)); the
fixtures are not yet built from them.

## Credits

Inspired by
[`jwhitby91/gmg_home_assistant`](https://github.com/jwhitby91/gmg_home_assistant)
by **Jason (jwhitby91)** - the work that first connected my Green Mountain Grill
with Home Assistant - and rewritten from scratch here. Protocol cross-checked against
[`brandenco/green-mountain-grill`](https://github.com/brandenco/green-mountain-grill)
and **Christopher McKay's** `gmg` on PyPI. The first real full-frame capture is
**m3rrym4n's**, from
[y3klab/gmg-ha#2](https://github.com/y3klab/gmg-ha/issues/2). The low pellet
value was first recorded in
[`Aenima4six2/gmg`](https://github.com/Aenima4six2/gmg)'s 2017 capture, and GMG's
own field names come from the decompiled app code published in
[`FeatherKing/grillsrv`](https://github.com/FeatherKing/grillsrv).
