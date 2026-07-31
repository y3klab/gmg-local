# gmg-local

Local UDP client for **Green Mountain Grills** Wi-Fi pellet grills.

No cloud account, no vendor API, no internet. It talks to the grill on your LAN
and nothing else.

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
| `model_for(firmware)` | Pure. `"Jim Bowie"` for a `JB` firmware prefix, `None` for anything unrecognised. |
| `Grill.set_temp(f)` / `set_temp_probe(f, n)` | Targets, in Fahrenheit. |
| `Grill.power_on()` / `power_on_cool()` / `power_off()` | Cold smoke is `power_on_cool`. |
| `parse_status(frame)` | Pure. No sockets, no clock - testable without a grill. |
| `poll_interval_for(state)` | 10s while cooking, 60s while off. |

## What the status frame contains

A healthy grill answers `UR001!` with **52 bytes**; this library decodes through
byte 33.

Temperatures are **16-bit little-endian pairs**. Reading only the low byte wraps
anything above 255, so a 350 °F grill reports as 94 °F - `u16(94, 1) == 350`.

| offset | field | notes |
|---|---|---|
| 2, 4, 6 | grill temp, probe 1, setpoint | 16-bit LE pairs |
| 8 | API version | |
| 16, 18 | probe 2 temp and setpoint | |
| 24-27 | warn state | 32-bit LE |
| 28 | probe 1 setpoint | |
| 30 | power state | 0 Off, 1 On, 2 Fan, 3 Cold Smoke |
| 32 | fire state | 0 Default, 1 Off, 2 Startup, 3 Running, 4 Cool Down, 5 Fail, 198 Cold Smoke |
| 33 | **fire state progress** | see below |
| 34-51 | **undecoded** | `gmg` 0.0.4 labels 48 and 50 as pellet alarms - unverified |

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
  messages, so all I/O here is serialised behind a lock.
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
with observed behaviour, not that the offsets are correct. Offsets are
corroborated across four independent implementations.

Preserving a genuine 52-byte capture is the prerequisite for decoding bytes
34-51, and should replace these fixtures when one exists.

## Credits

Descends from
[`jwhitby91/gmg_home_assistant`](https://github.com/jwhitby91/gmg_home_assistant)
by **Jason (jwhitby91)** - the work that first made these grills usable from
Home Assistant - since substantially rewritten. Protocol cross-checked against
[`brandenc40/green-mountain-grill`](https://github.com/brandenc40/green-mountain-grill)
and **Christopher McKay's** `gmg` on PyPI.
