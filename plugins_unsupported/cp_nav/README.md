# Independent CP navigation — local candidate 0.2.0

Current release 0.2.2 requires host c1f33cf2f4a2eaa287025369a930e4a468888999 (or compatible descendant) and qualified Panda ABI-2 firmware. Explicit per-rule primary_or_lateral guard preserves native MADS-only lamp permission without changing any ABI-1 rule. Brake, relay, template, counter, checksum, time and session gates still apply. Never install this archive onto the old deployed host/firmware alone.


This is a standalone store plugin with BOOL master `ExtCpNavEnabled`, its own
settings, process, data receiver and vehicle hooks. TesNav remains integrated
under `navassist` / `ExtNavAssistEnabled`; exclusive route, lane-policy and CAN
claims make the host switch off the other implementation when one is selected.
Use the parked Plugins page; applying a process/source change requires restart.
Installing a phone app cannot enable either plugin.

## Implemented

- Original CP navigation-v2 WebSocket ingress on 7714, bounded session/peer lease,
  source timestamps, replay rejection and route withdrawal. No TesNav package
  dependency. Source age is never renewed by an unchanged heartbeat.
- Original Carrot navigation decision kernel, pinned to jixiexiaoge/carrot
  `3615bf4bf40016f102e7d4af3745455a3791faa2`. The 37 retained method ASTs match
  provenance.json. Original MIT notice is in CARROT-LICENSE. Explicit CP-only
  Params and private output adapters replace live native services/OS mutation.
- Native turn/fork and road/camera/bump/section speed arbitration; bounded
  physical Tesla lamp transport under the existing hardware-checked 0x3E9
  policy. Route-turn lamps carry turn intent. Fork lamps can remain in
  preparation while OEM/BSM blocks crossing; SP automatic-mode and lane gates
  still decide whether a change starts. Observed completion consumes a maneuver.
- Optional bounded cruise increases, driver-setpoint/override cancellation,
  ceilings and scoped targets. TN 1.0.1 now receives all host plugin targets;
  other SP/model/lead caps remain effective. Effective planner target is not
  misrepresented as the OEM cruise setpoint.
- Dedicated parked settings in X-Pilot, Chinese labels via zh_cn 1.1.8, floating
  CP status HUD and one preparation chime per request. No camera client/JPEG
  encoder/image stream is started by this plugin.
- CP7000 native BSM compact telemetry. Original App-compatible `values` API and
  effectful navigation parameter aliases only. Writes require the bound CP
  peer, enabled master, fresh zero-speed/P state, type/range checks and a second
  state check after receipt. Global/experimental/master settings are rejected.

## Automatic passing: retained source, not available on this host yet

User explicitly reauthorized CP passing on 2026-10-28; stereo remains removed.
The candidate retains a source-derived CP state/threshold adapter: slow-lead
confirmation, styles/TBT priority, 2.5s preparation, cooldown, original-lane memory
and continuous return confirmation. Only observed start/finish/off records a
completed change. A new command is not completion.

The paired standard SP host has no CP `leadLeft`/`leadRight` and no qualified
pass-complete/return-efficiency feed. Production observations therefore declare
passing unavailable; it **does not initiate automatic passing or return** merely
because factory BSM is not triggered. The original phone manager likewise lacks
its full active/model telemetry on this adapter. The mode remains a development
setting; selecting it displays unavailable until real evidence is implemented.

This is not the complete original Kotlin AutoOvertakeManager, complete Carrot
longitudinal/traffic-light planner, CP vehicle firmware, full CP settings API,
CP camera/MNN execution, or a rebuilt/licence-bypassed phone App. Native UDP
SPEED/LANECHANGE commands, curve input and spoken countdown are not advertised
as available. Unsupported CP App settings are explicitly rejected.

## Host compatibility and activation

Requires the synchronized Sniper-Eon/xpilot host and runtime-rule ABI 1 firmware.
The plugin declares the canonical NAV template rule; the older safety_provider
and feature-bit system is no longer supported by this release. Keep host, store
packages and validated firmware together. Source synchronization alone does not
change the running device or grant signal/steering authority.

Default master is off. Prepared CP/TesNav profiles select one data source in
observation mode, with physical lamps, crossing, speed control, increases and
passing initially off. They preserve other plugins and Chinese localization.

Local package and source checks are separate from device/road evidence. No
C3/phone access, installation, restart, parameter mutation, firmware build,
actual MNN execution or road test was performed for this candidate.

## Validation

See REPORT.md for commands, outcomes and the remaining integration limits.
Factory-lane vetoes retain the DS two-frame confirmation and bounded release.
`tools/cp_upstream_probe/run.py --independent` runs the author's unchanged
Kotlin wire client/mapper through this receiver and native Carrot kernel using
loopback synthetic observations. It is not a full Android build or road replay.

## 0.1.1 — onroad message publication repair

Requires a paired host with `openpilot.tesla.plugin_msgd` and the broker send API.
Install the host transport backport before upgrading cp_nav or navassist. The
entry refuses to import on old single-publisher hosts. Both navigation producers
now use the host broker without constructing a cereal pluginMsg publisher.
This fixes the real onroad crash where card's OEM-lane publisher displaced
cp_navd, causing a process-not-running cruise entry block. No safety checks or
required-process checks are bypassed. Existing navigation settings and firmware
permissions remain unchanged. Phone connection and road behavior still require
a post-update device check; loopback protocol tests are not phone validation.

Required broker host commit: `fc9afa643497a334f7d69df637042bcaca03777b` or a compatible descendant.

## Upstream runtime-rule migration 0.2.0

Requires the synchronized host f451a13b219930e26d316b8997dafda93fc6784f (or a compatible descendant) and qualified runtime-rule ABI 1 firmware. The old per-feature safetyParam bit/policy reference is retired. Ship a coherent host/store/firmware set; do not copy this package onto the old device host. Existing navigation settings and integration remain, but active physical signal requests now require primary cruise engagement; the earlier MADS-only permission is not equivalent and remains a pre-deployment compatibility item. No device or phone was updated by source synchronization.
