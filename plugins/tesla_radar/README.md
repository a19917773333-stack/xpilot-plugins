# Tesla Radar (OEM / ARS408)

`source:radar` plugin. It replaces the port's Tesla radar interface with the sunnypilot backends:

| Setting | Result |
|---|---|
| `OEM` | returns nothing, so the port's own Tesla radar keeps running |
| `ARS408` | Continental ARS408 object list on bus 1 (`0x60A`..`0x60D`), tracked into `RadarData.points` |
| `Off` | the silent base interface, so `radarTracks` goes empty instead of stale |

## Claims and limits

- Claims only `source:radar` and is read only: it parses radar CAN, it never sends a frame.
- ARS408 configuration frames (`0x200`/`0x300`/`0x301`) are **not** sent yet. That needs `can.tx` claims plus panda
  runtime rules in the host repository, so the radar has to be configured outside xpilot (factory object output).
- The port radar runs alongside and takes over for good if this plugin raises, per XPILOT.md section 7.
- If the host has no `radarUnavailable` port radar (other brands), the host never calls this hook.

## Tests

    cd <xpilot-plugins>
    PYTHONPATH=<xpilot>:<xpilot>/opendbc_repo python3 -m pytest -q plugins/tesla_radar/tests

`tests/` covers the ported parser, cycle assembler, tracker, diagnostics, the radar interface and the backend
selection. Validation status: unit tests pass, **no on-car run yet**; ARS408 hardware was not connected.