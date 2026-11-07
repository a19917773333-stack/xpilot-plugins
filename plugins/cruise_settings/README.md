# Cruise Settings

One plugin for the cruise switches that otherwise live in the sunnypilot Toggles pages:

| Plugin switch | Host param |
|---|---|
| Intelligent cruise buttons | `IntelligentCruiseButtonManagement` |
| Smart cruise from vision | `SmartCruiseControlVision` |
| Smart cruise from map | `SmartCruiseControlMap` |
| Main cruise allowed | `MadsMainCruiseAllowed` (not recreated when the car removes it) |
| Initial set speed | `InitialCruiseSpeedKph` (clamped to 20-160) |

The worker (`cruise_settingsd`) copies the values into the host params once per second **only while parked**.
It does not touch steering, acceleration or CAN. Turning the plugin off stops the mirroring; the host keeps the last
values.

A small **CRUISE** tile opens the same switch page and shows the initial set speed (or OFF when intelligent cruise
buttons are disabled).

## Checks

`python -m pytest plugins/cruise_settings/tests` covers the mapping, the speed clamp and the Tesla main-cruise case.
