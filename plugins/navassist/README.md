# Navigation Assist 2.0.1

Current release 2.0.3 requires host c1f33cf2f4a2eaa287025369a930e4a468888999 (or compatible descendant) and qualified Panda ABI-2 firmware. Explicit per-rule primary_or_lateral guard preserves native MADS-only lamp permission without changing any ABI-1 rule. Brake, relay, template, counter, checksum, time and session gates still apply. Never install this archive onto the old deployed host/firmware alone.


Personal fork: [Sniper-Eon/xpilot](https://github.com/Sniper-Eon/xpilot), branch `xpilot`.
Install this release only with the synchronized paired host and runtime-rule
ABI 1 firmware. Its canonical NAV template rule replaces the old per-feature
safetyParam bit. The historical release notes below describe older ABIs; the
current migration section is authoritative. API 1 alone is not sufficient.

## Migrated behavior

- Existing phone v3 UDP 4213, signed HTTP 7766, signed discovery 7765 and parked-only pairing.
- Strict packet/replay/TTL handling, `routeAvoid`, request-sequence ACK and display-only lane feedback.
- Navigation lane preparation retains the signal while a confirmed OEM boundary/BSM veto prevents SP starting
  or continuing a lane change. The generic host context can only restrict SP; it cannot initiate steering.
- Same-adjacent absolute/relative source changes preserve the request, reset readiness and require fresh
  observations. Missing observations and recovery confirmation have separate bounded timers.
- Turn-only lamps do not become lane-change requests; lane-position lamps do not generate a turn desire.
- Three distinct fresh model frames plus a physical right carriageway anchor are required for absolute lane
  numbering. Merely matching the visible and map lane counts is insufficient. Ambiguous geometry is unknown.
- Navigation-only chime when a valid automatic signal request begins, once per request; preparation and turn-only requests are announced, manual changes stay silent. SP's own wait/driver veto remains mandatory for lane-change initiation.
- Maneuver speed ceilings only lower the target; missing control context, poor GPS or stale guidance rejects it.
- Optional phone blind spot **extra veto**, off by default. Missing phone data never proves clearance.
- Stereo, closing-speed experiments and proactive passing have been removed.

The process reuses `modelV2` geometry. It opens no camera, converts no images and runs no neural network.
Geometry cannot identify painted solid lines: OEM rejection is used when available. The legacy explicitly
permitted unknown-paint fallback remains limited by SP's road-edge, blind-spot, speed, lateral and panda gates.
This is not proof that an unobserved boundary is safe.

## Plugin interfaces and settings

`pluginMsg`: `nav.state`, `lanes.topology`, `lanes.intent`, `oem.lanes`.
Only messages from producer `navassist` are consumed. Expired displays clear; an expired owned lamp cannot
fall through into automatic lane-change permission. Explicit disable clears coordinators immediately.

All configuration lives in the store's private parameter directory, not new core Params keys.
The master, lane positioning, physical lamp and phone-veto switches default off. Pairing identities are private;
reset is accepted only offroad. Existing keys/codes must be migrated privately during installation.
Diagnostics rotate under the device data directory; driving logs and keys are excluded from this repository.

The separate `phone_vision` plugin provides single wide-camera frames for the companion app.
It is disabled by default and not started by navigation. Dual camera, overtaking and external model control
have been removed. External model control is not supplied by this navigation plugin.

The 1.3 overlay keeps fresh linked route text visible while localization is unavailable,
marked `GUIDANCE ONLY`. This is presentation only: control validity, source expiry,
lane readiness and vehicle assistance gates are unchanged. Stale or unlinked instructions
still disappear. TesNav 21 adds CP-compatible AMap broadcast handling inside the existing
companion; selecting that app on C3 still requires the TesNav v3 profile (source 0).

## Physical lamps and firmware

Card clones a fresh idle 0x3E9 bus-1 template. Only request/reason/counter/checksum change. Driver opposite
signals/hazards take priority without a cancellation injection. The panda safety plugin checks the template,
checksum, controls_allowed for active requests, bus, size, 100 ms rate, and 200 frames per 60 seconds.
Cancel is permitted without controls_allowed because it only releases an owned lamp.
SP and Tesla remain the lane-change/steering authorities. Host checks, native safety tests, actual firmware
compilation, device build, parked validation and road validation are separate evidence.

## Turn-completion ownership repair (1.3.1)

When guidance advances while the vehicle is still turning, the bounded completion hold retains the original
physical-lamp request ID. Otherwise the wire controller treats the new instruction as a replacement and cancels
the lamp despite the coordinator requesting a hold. Stable turn completion, route/session changes, stale inputs,
driver override, disable and the existing timeout still release ownership. No lane-change permission is added.
This repair uses only the paired host's existing interfaces; it does not add runtime rules or migrate firmware.

## Validation

From `plugins/`, with the paired xpilot checkout on PYTHONPATH:

```
python3 -m pytest -q navassist/tests phone_vision/tests
```

Run `tools/sp_tesla_e2e/store_e2e.py --repo ../xpilot-plugins` in the system checkout for archive installation,
discovery and host checks. `migration-source.json` identifies the legacy coordinator source. A successful
local check does not mean this version has been installed or road-tested.

## Two X-Pilot profiles

`ExtNavAssistSource` is read once at process startup: 0 = existing TesNav v3; 1 = CPdazi8 v2.
Only the chosen transport opens sockets; there is no source fallback or simultaneous command stream.
CP uses port7714 `/api/navi/ws/v2/control/amap_auto_1.0` and bound JSON streams,
UDP7705 discovery, and read-only7000 `/api/heartbeat_status` and `/ws/compact_state`.
The CP compatibility layer is independent code based on observed protocol fields, not copied app controllers.
It subscribes only to JSON; native BSM/vehicle metadata needs no camera images.

CP compatibility is currently partial and candidate-only. Only fresh native `carState` is returned in compact
telemetry. Missing model/radar/Carrot-specific services stay unavailable; CP-only car fields are reserved padding
listed in heartbeat capabilities. A missing side radar track never means an empty safe lane.
Remote Params, CP model downloads, CP cloud authorization, destination injection and passing commands are
unsupported. The original CP app may still show its own unsupported controls. No entitlement is bypassed.
CP navigation observations expire independently of reception/heartbeat. Stale/absent GPS, route, guidance
or status cannot start a request. A new control lease resets the source. Fresh native localization and normal
SP/Tesla gates are still required by the shared coordinator.

1.5.7 checks the original `jixiexiaoge/navipilot:latest-snapshot` source at
`91d77de4fd7650ebc76c38cf4b47ede503f6d0dc`. Its unmodified Kotlin WebSocket client,
mapper, data models and compact decoder pass loopback interoperability; this is
not a full Android UI, MNN inference or vehicle validation. The receiver tolerates
bounded control/data handshake reordering, fixes the distinct sharp-left/exit/
lane-change/slight-turn codes, and clears route-scoped data on explicit route
withdrawal. Phone model estimates are bounded observations only, never map lane
identity, recommendations or crossing permission. See [CP snapshot compatibility](CP_SNAPSHOT.md).

## Local fork note: TesNav coexistence

`tesnav` (vendored from `juyun86/xpilot-plugins`) is a separate navigation plugin with its own switch
`ExtTesNavEnabled`. This plugin keeps `ExtNavAssistEnabled`. Both receive the same phone snapshot family and
both bind UDP 4213, so **enable only one at a time**; this plugin does not release or probe the other's socket.

Unnumbered navigation merges now use one bounded relative adjacent step per event, with observed neighbor, OEM/crossing, BSM and SP timing checks retained. Missing absolute numbering alone does not cancel merge/exit preparation. A completed relative merge cannot fall through to a fresh turn-only lamp. `signalPurpose` distinguishes junction lamps (SP turn intent still requires actual CarState blinker feedback) from merge/exit preparation (never a substitute for permission to cross). No direct turn-desire injection or new host API is used.

### HUD presentation (1.5.1)

The navigation overlay uses only the strip below the driving view. It distinguishes a requested signal from actual same-side carState blinker feedback and reports unavailable primary panda authority as a wait, rather than promising a turn or lane change. Recommended lanes never establish an observed ego-lane index. Inactive/replay guidance is hidden by the existing display contract. This release does not change navigation execution, CAN, steering, camera capture or safety firmware.

### Signal feedback recovery (1.5.2)

Keep up to two active lamp requests and wait for physical feedback until the original 2.5-second deadline. Exhausting retries alone no longer cancels after about 0.2 seconds. A failed event cannot restart itself; a new event may start subject to the same global frame interval, including across cancellation. Brake-held entry sends no active request. Real junction lamps remain distinct from road-edge/BSM lane-crossing vetoes. Independent MADS lateral authority requires the paired host safety repair; an APK or plugin update cannot grant that authority on older firmware.

HUD authority feedback in 1.5.3 also reads native controlsAllowedLateral with the MADS enable flag, so independent lateral operation is not falsely displayed as missing all signal permission.

### Floating guidance (1.5.4)

The bottom-strip HUD removes its card and lane-cell backgrounds. The main arrow grows from 115 to 200 screen pixels; current/next maneuver nodes move to the right. Old tile faces are erased to the screen's black canvas so they cannot show through as duplicate unknown labels. It stays outside the road viewport and critical road-view alerts. Only fresh supplied current/next instructions are shown; no route nodes or ego lane are invented. The existing host APIs and all driving/safety logic remain unchanged.

### C3XL buzzer contract (1.5.5)

The navigation notice uses the standard host warning/prompt alert. C3XL routes audio through its existing GPIO buzzer, whose host backend must map that prompt to a short pulse. The integration regression covers navigation preparation, host alert production, GPIO dispatch deduplication and unchanged critical-tone routing. Plugin actuation and chime timing are unchanged; installing this plugin alone cannot repair an older host buzzer backend.

### Phone metadata compatibility (1.5.6)

Recognize the seven optional context fields already emitted by TesNav: parallel/elevated road status, route notice type/distance/time, and turn-signal hold/countdown. Validate enums, booleans and numeric bounds instead of discarding the entire snapshot when these documented fields appear. They remain data only: no new lane index, turn, crossing permission or countdown-based actuation is inferred. All route/position freshness and SP/BSM/paint gates remain unchanged. Reject diagnostics retain a bounded field name and category without echoing packet values.

## Message transport compatibility (1.5.9)

Requires the paired host plugin_msgd broker. The receiver sends the same kinds,
payloads and TTL through the single broker instead of owning pluginMsg directly.
Deploy the compatible host first. No navigation decisions or settings changed.

Required broker host commit: `fc9afa643497a334f7d69df637042bcaca03777b` or a compatible descendant.

## Upstream runtime-rule migration 2.0.0

Requires the synchronized host f451a13b219930e26d316b8997dafda93fc6784f (or a compatible descendant) and qualified runtime-rule ABI 1 firmware. The old per-feature safetyParam bit/policy reference is retired. Ship a coherent host/store/firmware set; do not copy this package onto the old device host. Existing navigation settings and integration remain, but active physical signal requests now require primary cruise engagement; the earlier MADS-only permission is not equivalent and remains a pre-deployment compatibility item. No device or phone was updated by source synchronization.

## 2.0.1 — directional lamps and execution-only GPIO notice

Requires paired host 71e16223e8fbac00dab8d5d6975e50d9df0e483e (or a compatible descendant), including
`buzzer_policy`, plus the existing ABI-1 firmware requirement. Do not copy this
release onto the older deployed host alone.

Unknown absolute numbering no longer suppresses slight-left/right lamps. These
lamps delegate automatic admission to native SP/BSM rather than manufacturing a
map lane index; SP vetoes, road edges and driver controls remain authoritative.
Explicit merge/exit/ramp guidance can prepare one observed adjacent corridor per
event without absolute numbering. Missing corridor, paint, BSM and source gates
still block the crossing. A slight-direction lamp does not create low-speed turn
desire.

A chime needs fresh matching navigation ownership, physical lamp feedback,
lateral engagement and actual laneChangeStarting; delegated SP changes are
recognized from the real model transition, never from a clear BSM bit alone.
Manual/opposite/stale or denied preparations remain silent. While this plugin
is enabled, ordinary GPIO prompts are restricted to this navigation execution
notice; MADS on/off and emergency warnings retain the host's native tones.
The BOOL master releases this restriction when disabled.

This is a planning/admission repair, not a retrained vision model. Local tests and
replays are distinct from device activation and road validation.

## Original-car fork corroboration (2.1.0)

A read-only card-side VEH 0x238 decoder publishes `nav.map`. The navigation process
attaches `branchEvidence` to each current route event and shows a quiet fork notice in
the existing HUD. It distinguishes an observed fork, checking/consistent route evidence
and a potentially different fork. Three distinct frames and decreasing distance are
required; stale data, rerouting and disable clear the evidence. CONSISTENT is advisory,
not unique junction identification or target-lane clearance. No maneuver, lamp timing,
slowdown, unknown-lane behavior, native checks or buzzer behavior is overridden.
The standalone Tesla Map diagnostic plugin is optional and need not be enabled.

## CP phone lane model observation (2.2.0, local candidate)

Default-off `ExtNavAssistPhoneLane` consumes authenticated frame-bound `lane_cp`
observations from the independent phone_vision source. Three distinct consistent
frames provide a visible-corridor lane estimate in the existing HUD. It is not an
absolute map lane or crossing permission. Only agreement with the existing qualified
geometric position is labelled corroborated. Missing/expired/bad output, route/stream
changes and disabling clear the model estimate. No lane-change policy, lamps, sound,
phone-installed switch or original navigation decision is overridden.
See companion/tesnav/docs/CP_LANE_LOCAL.md for APK/runtime and validation boundaries.

## Single-frame mode (2.2.1, user decision 2026-10-29)

The user explicitly removed both geometric corroboration and the three-frame wait.
A valid fresh frame now displays the phone's lane estimate immediately, without
consulting the existing geometric position. Route changes still discard the old
frame; original timestamps, frame identity, model contract, disable and expiry
checks remain. Visible-corridor estimates are not relabelled absolute-map lanes.
Native BSM, paint, road-edge, driver and engagement checks are unchanged.
This supersedes the confirmation behavior described in the 2.2.0 candidate above.

## Model feedback to the companion app (2.3.0)

The HUD's phoneLaneEvidence is now also published, with its original capture time
and current navigation session/revision, to /dev/shm/phone_lane_estimate.json.
An explicitly negotiated laneEstimateVersion=1 query returns laneEstimate separately
from the legacy absolute lanePosition. Old query and ACK shapes are unchanged.
The Android client retains legacy queries for old hosts and preserves model evidence
when a legacy ACK arrives later in the same receive window. Original age reduces the
phone display lifetime; ACK receipt cannot renew old source data. The APK labels the
result as a model estimate and uses a current-lane marker only when its count matches
the displayed map lanes and route revision. This does not change C3 route planning.

Fresh CP model estimates participate in route lane alignment when their visible lane count matches the navigation lane total. This does not certify whole-road visibility or absolute position. The existing phone-lane switch controls ownership; disabling restores legacy geometry. Unknown model data uses existing unknown-position preparation rules, with all native crossing checks retained.
