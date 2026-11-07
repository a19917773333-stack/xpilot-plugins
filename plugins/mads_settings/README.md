# MADS Settings

A separate plugin front end for the host MADS switches, so they can be changed without the Toggles page:

| Plugin switch | Host param |
|---|---|
| MADS enabled | `Mads` |
| Steering on brake | `MadsSteeringMode` (0 remain active / 1 pause / 2 disengage) |
| Unified engagement | `MadsUnifiedEngagementMode` |
| Tesla screen button | `TeslaMadsScreenButton` (0 off / 1 three finger / 2 four finger / 3 five finger) |

`MadsMainCruiseAllowed` moved to the separate **Cruise Settings** plugin.

The worker (`mads_settingsd`) copies the switch values into the host params once per second **only while parked**.
It does not touch steering, acceleration or CAN. Turning this plugin off stops the mirroring; the host keeps the
last values.

## Tile and page

The plugin adds a small **MADS** tile. Tapping it offroad opens a native page with one row per switch (the same rows
the Plugins page shows). The tile shows ON/OFF and the brake-steering mode, and it is hidden while the plugin switch
is off.

## Tesla notes

- `MadsMainCruiseAllowed` is owned by the Cruise Settings plugin; on Tesla it is absent and that plugin leaves it absent.
- With the screen button at Off, MADS is limited and the host forces `MadsSteeringMode = 2`; pick Three finger or
  above if you want to keep steering through a brake press.
- MADS still needs the host's own gates (stalk/cruise engagement, car state); this plugin only changes settings.

## Checks

`python -m pytest plugins/mads_settings/tests` covers the mapping and the Tesla main-cruise case.
