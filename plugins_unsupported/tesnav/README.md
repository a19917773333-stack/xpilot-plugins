# TesNav Navigation / 特会开导航

Version 0.1.1 combines phone guidance, recommended-lane display and optional
turn slowdown in one plugin. It does not steer, change lanes, send CAN, control
indicators, stop at traffic lights or feed a navigation driving model.

## Pairing and compatibility

Requires the host `navigation_ingress` capability. Install/enable while parked,
restart, and start the TesNav App while still parked on a controlled private LAN.
Use the App's default UDP mode (blank explicit server URL), not WebSocket or HTTP.
The first valid phone IP is pinned for this device boot. New App sessions must
be established while parked after the previous lease expires. Restarting only
the worker preserves replay state and the phone pin; reboot clears it. Changing
phones therefore requires parking and rebooting. No token/key is exported.

Reviewed companion: `juyun86/TesNav` commit
`276ee3b6a2d9c4ada7863ed7cbc43c2f67a3435b`, branch
`navassist-v2-track-p0-20260927`. Its wire protocol is v3 despite V2 class names:
`navigation_snapshot`, UDP 4213, 8 KiB, matching session/sequence acknowledgement.
The MR.ONE APK (`ai.mrone.phone_navi` 0.2.0) uses a different protocol and is not
supported. Actual App/device interoperability remains an acceptance check.

Transport is unauthenticated IPv4 RFC1918 only. An ACK means snapshot admission,
never vehicle permission or completion. The App must show missing vehicle/lane
execution feedback as unknown. This version sends no vehicleTelemetry,
vehicleLane, laneDecision or laneAnnouncement fields; old C3XL feedback is not
fabricated. Stop the old C3XL navigation receiver before running this plugin on
the same system; port 4213 is exclusive and is never forcibly reclaimed.

## Lifecycle and freshness

`tesnavd` runs on/offroad as the `source:navigation` owner and publishes only
`navInstruction` at up to 20 Hz. It does not publish `pluginMsg`, so Starlink can
run concurrently. OSM and the existing map tile can remain enabled. This version
provides instructions, road text and recommended lanes, not basemap/route images.

Unknown/duplicate fields, nonfinite values, invalid ranges, simulation, missing
distance, unmatched/weak-GPS routes, future observations and source replay are
rejected or invalidated. Display requires real navigation, <=30 m phone accuracy,
and both location and guidance observations <=2 seconds old. This conservative
initial observation budget has not been calibrated on background/weak-GPS phone
traces; stationary guidance may therefore disappear rather than stay stale.
Wire TTL is 100–2000 ms, additionally bounded by source delivery age. Monotonic
expiry is never extended by a replay. The tile independently expires at 500 ms;
the slowdown consumer at 300 ms after the last message publication.

An atomic `/dev/shm/xpilot-tesnav-replay.json` stores only phone IP, session,
sequence and revision (max 64 session tombstones), never coordinates/credentials.
Corruption or exhaustion fails closed; park and reboot to reset. No data files
or params are deleted on uninstall; the volatile checkpoint disappears on boot.
Disable/uninstall/restart stops the worker and releases its socket; abrupt exit
still leaves consumers' timestamp expiry. No subprocess, shell, route or DNS work.

## Optional slowdown

`ExtTesNavSlowdown` defaults off. It requires Tesla openpilot longitudinal support,
fresh navigation/car/control/device messages and active longitudinal control.
It only supplies a lower cruise ceiling through `long_target`; stock following,
MPC, collision checks and vehicle/Panda limits remain authoritative. It never
requests acceleration, a stop or a higher cruise set speed.

Initial turn speeds: slight 8, normal 5, sharp 3.5, U-turn 2.5, roundabout 6 m/s.
The approach ceiling is `sqrt(turn_speed² + 2*1.2*max(distance-10,0))`, only below
both current speed and cruise speed, within 2 km. These are experimental inherited
research values, not a road-validated speed policy. Pedal/steering override,
loss of route or longitudinal authority after use latches slowdown off until an
observed offroad state. Changing a toggle does not clear that latch.

## Source and checks

The strict wire parser/types derive from the supplied
`official-navigation-research-20261026` source snapshot's
`sunnypilot/navassist/protocol.py`, split into `wire.py` and `protocol.py` without
the old system's store/network/control integration. Remaining logic is plugin-local.
No full system diff, private keys, SDK keys, weights or recordings are shipped.

Failure cases are listed before implementation in `tests/test_navigation.py`.
Run `python -m pytest plugins/tesnav/tests` and the host navigation ingress check,
then the repository's archive/index and store checks. Static/host checks do not
establish actual phone operation, performance, vehicle execution or road safety.

## Local fork notes (Sniper-Eon)

- Vendored unchanged from `juyun86/xpilot-plugins`; the app protocol is the same UDP 4213 v3 snapshot family
  that `navassist` uses.
- Switch: `ExtTesNavEnabled` (this plugin) vs `ExtNavAssistEnabled` (`navassist`). They are separate plugins
  with separate directories and parameters; enabling one does not touch the other.
- Both bind UDP 4213, so **only one may be enabled at a time**. Stop the other navigation plugin before
  enabling this one; the port is never forcibly reclaimed.
- Needs the host `navigation_ingress` capability (this repository's system side carries it). On a host without
  it the plugin is skipped with a load error and nothing else changes.
