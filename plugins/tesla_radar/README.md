# Tesla Radar (OEM / ARS408)

`source:radar` plugin exposing the sunnypilot radar backends. ARS408 replaces the port's Tesla radar interface; OEM explicitly defers to it:

| Setting | Result |
|---|---|
| `Factory radar` (default) | returns a host marker that defers to the port's own Tesla radar |
| `ARS408 radar` | Continental ARS408 object list on bus 1 (`0x60A`..`0x60D`), tracked into `RadarData.points` |
| `Radar off` | the silent base interface, so `radarTracks` goes empty instead of stale |
| `Radar triangle display` | on by default; radar leads are gold and vision leads are white on the road view |

## Claims and limits

- Claims only `source:radar` and is read only: it parses radar CAN, it never sends a frame.
- Factory mode sets `uses_port_radar = True` on its interface; the host then returns the port radar's same-cycle result when the plugin update is `None`. Radar off uses the base interface's explicit empty `RadarData` and cannot be mistaken for factory mode.
- ARS408 configuration frames (`0x200`/`0x300`/`0x301`) are **not** sent yet. That needs `can.tx` claims plus panda
  runtime rules in the host repository, so the radar has to be configured outside xpilot (factory object output).
- The port radar runs alongside and takes over for good if this plugin raises, per XPILOT.md section 7.
- If the host has no `radarUnavailable` port radar (other brands), the host never calls this hook.
- Triangle rendering is an optional `RoadOverlay`. It reads fresh `radarState` leads from the current trip: radar-sourced leads are gold
  (`255,215,0`) and vision leads are white (`255,255,255`), matching the pre-xpilot display the owner requested.
- The source colors and marker intent are ported from
  `a19917773333-stack/slgame@6b5dc07f892d24111dbcd67bbf7a890183ba02b7:openpilot/selfdrive/ui/onroad/model_renderer.py`
  and adapted to the host's public `road.polygon()` projection instead of accessing the model transform.

## Tests

    cd <xpilot-plugins>
    PYTHONPATH=<xpilot>:<xpilot>/opendbc_repo python3 -m pytest -q plugins/tesla_radar/tests

`tests/` covers the ported parser, cycle assembler, tracker, diagnostics, the radar interface and the backend
selection. The backend selection needs the host's `Plugin`, so it skips (rather than stubbing `sys.modules`) when
xpilot is not on PYTHONPATH. Validation status: unit tests pass, **no on-car run yet**; ARS408 hardware was not
connected.
## Parity with the C3

Every module of the C3's `opendbc/sunnypilot/car/tesla/ars408/` package is here, byte for byte apart from imports
(`opendbc.sunnypilot.car.tesla.ars408.x` -> `.x`) and two deliberate differences:

| C3 | Here |
|---|---|
| `selector.py` picks by `TeslaFlagsSP.ARS408_RADAR` / `RADAR_DISABLED` | `plugin.py` picks by `XpilotTeslaRadarBackend`, the plugin's own switch |
| `constants.ARS408_DBC = "ARS408"` (opendbc ships the DBC) | the DBC is vendored beside the package and addressed by path |
| `transmitter.py` is wired into the car's CAN send | `transmitter.py` only builds frames; nothing here sends (see Claims and limits) |

The C3's `opendbc/car/tesla/radar_interface.py` also carries a local fix (`aRel`, `yvRel`, `measured` under
`RadarPoint.deprecated`). That is opendbc's Tesla car code, which XPILOT.md section 2 forbids editing from a
plugin: check it against the opendbc revision this branch pins instead.
