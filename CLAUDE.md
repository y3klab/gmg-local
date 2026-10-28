# CLAUDE.md

## What this is

A Python client for Green Mountain Grills Wi-Fi pellet grills, speaking their UDP
protocol on the local network. Published to PyPI as **`gmg-local`**; the import name is
`gmg_local`.

**It is not a Home Assistant library.** It imports nothing from Home Assistant and returns
plain dicts. The HA integration ([`y3klab/gmg-ha`](https://github.com/y3klab/gmg-ha)) is a
consumer, not the point. Anything that would only make sense inside Home Assistant belongs
there, not here.

## Structure

Split by testability, not by topic:

| module | holds | rule |
|---|---|---|
| `protocol.py` | parsing, `u16`/`u32`, `poll_interval_for` | **pure** - no sockets, no clock, no I/O |
| `grill.py` | the `Grill` class, all network calls | |
| `discovery.py` | UDP broadcast/unicast discovery | |
| `const.py` | wire format - offsets, enums, commands, bounds | |

Keeping `protocol.py` pure is what lets the parser be tested without a grill, a network, or
Home Assistant. Don't put I/O in it.

## Conventions

- **Never return a partial status dict.** A short or garbled frame must fail the whole
  parse. A dict of `{field: None}` is indistinguishable from a grill genuinely reporting
  those values, and the caller can keep its last known-good reading instead.
- **Short datagrams are retried, not parsed.** They are a transport artifact. Parsing one
  either raises or invents fields.
- **All I/O is serialized behind a lock.** The grill answers one client at a time;
  concurrent conversations lose messages.
- **The `Grill` class exposes bounds as class attributes** (`MIN_TEMP_F`, `MAX_TEMP_F`,
  `MAX_TEMP_F_PROBE`, `PROBE_TARGET_CLEAR`). Consumers read them off the instance - moving
  them breaks callers silently.
- Public API is re-exported from `__init__.py`. `grills` is a back-compat alias for
  `discover`, and `grill` for `Grill`.
- **Commit subjects are plain imperative, at most 72 characters.** The subject is one
  plain, clear sentence describing the change, with no prefix of any kind: no emoji, no
  type word such as `docs:` or `fix:`, and no scope or area word such as `grill:`. PR
  titles follow the same rule. Example: "Fix the probe target readback". Everything else
  goes in the body. 72 is where GitHub folds a subject and where `git log --oneline`
  truncates on an 80-column terminal.

## Gotchas

- **Byte 33 is `fireStateProgress`, not a pellet level.** It is a four-step progress marker
  through the *current fire state*: 25/50/75/100 up through Startup, hitting 100 exactly at
  the switch to Running, then back down through Cool Down to 0 as the fan stops. At least
  one other public implementation labels it `hopper_pct` and ships a pellet gauge - a hopper
  does not fill during ignition and empty when the fan stops. **What each 25% step
  physically means is unknown. Do not invent labels for it.**
- **Temperatures are 16-bit little-endian.** Reading only the low byte wraps anything above
  255, so a 350 °F grill reports as 94 °F. This is the defect in most public
  implementations; `u16` exists because of it.
- **Probe writes are silently discarded while the grill is off.** Write 203, read back 0,
  no error. Callers must not display a target the grill never accepted.
- **Test fixtures are reconstructed, not captured** - real decoded observations re-encoded
  at the documented offsets. They prove the parser is self-consistent with observed
  behavior, **not** that the offsets are right. Four genuine frames have been captured
  (three from the Daniel Boone Prime, `UNDB020002_1.2`: 2026-10-18 plus a low pellet
  tripped/clear pair from a separate session; one from the Jim Bowie, `UNJB02SUF0_2.3`,
  2026-10-25; all grill off) and are recorded in the README; the fixtures are not yet
  built from them.
- **Firmware comes from `UN!`, not from status bytes 9-15.** Upstream
  (brandenco) labels status bytes 9-15 `FirmwareDetails`; on real hardware
  (Jim Bowie, 2026-07-30) those bytes are binary (`0c 14 32 16 19 15 19`), not
  text. `UN!` answers `b"UNJB02SUF0_2.3"`. The leading `UN` matches the command
  bytes and may be an echo - but `UL!` does not echo, so it is surfaced
  **verbatim** rather than stripped on a guess. If the echo question is ever
  settled, `parse_firmware` is the one place to change.
- **Bytes 34-51 arrive and are discarded.** A healthy grill answers with ~52 bytes and this
  decodes through 33. On both captured frames (Daniel Boone Prime and Jim Bowie), 41-51
  are the firmware string in ASCII: the `UN!` reply minus `UN` and the underscore.
  `gmg` 0.0.4's `pelletAlarm1 = 48` and `pelletAlarm2 = 50` are hex-string positions, not
  byte offsets; position 48 is byte 24, the warn field. A lone `0x03` sits at byte 35 on
  `SUF0_2.3` firmware and at byte 40 on `DB020002_1.2`, so its position follows firmware,
  not model; it has no known meaning.
- **PyPI blocks confusably-similar names.** `pygmg` was rejected because `Py-GMG` exists.
  The rule strips `.`, `_`, `-`, maps `l`/`i` → `1` and `o` → `0`, then lowercases. A
  404 from the JSON API does **not** mean a name is free - it 404s for projects with no
  releases.

## Releasing

Trusted Publishing (OIDC) - **there is no API token anywhere**, not in the repo and not in
Actions secrets.

```
bump version in pyproject.toml → tag vX.Y.Z → push tag → create a GitHub Release
```

The release fires `publish.yml`, which builds and then **waits for approval** at the `pypi`
environment before uploading. **PyPI versions can never be reused**, even after deletion.

Release notes are **informative, succinct, friendly**: the tagline names what changed in
plain words; the body opens by naming the thing, states facts declaratively with real
commands and numbers, names any manual step plainly without softening it, and cuts process
trivia (test counts, internal mechanics). Always state upgrade impact.

## Don't

- **Don't add Home Assistant imports, or anything HA-shaped.** That is what makes this
  reusable and what lets HA core accept it as a dependency.
- **Don't put I/O in `protocol.py`.**
- **Don't label byte 33's steps** without a manufacturer statement or two independent
  cold-start observations.
- **Don't trust an absence-of-signal check on an idle grill.** "No event" means both "not
  polling" and "polling, nothing changed." Wait for a signal that must appear.

## Origin

Inspired by `jwhitby91/gmg_home_assistant`, rewritten from scratch (measured: 8
non-trivial verbatim lines remained); credit stays in the README for the package's
lifetime. Protocol cross-checked against `brandenco/green-mountain-grill` (Go) and
`gmg` on PyPI.
