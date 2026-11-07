# CP snapshot candidate compatibility

Reference: [jixiexiaoge/navipilot latest-snapshot](https://github.com/jixiexiaoge/navipilot/tree/91d77de4fd7650ebc76c38cf4b47ede503f6d0dc), App8.1.10. User authorized examination and adaptation of the author's shared code. The author snapshot and its bundled third-party model/runtime files are not copied into this plugin archive.

## Verified locally

The **original, unchanged** Kotlin `NaviWebSocketV2Client`, `NaviDataModels`, `AmapManeuver` and `CompactStateDecoder` were compiled with only Android logging replaced by a JVM shim. They negotiate all28 catalog entries/13 JSON sockets against this Python adapter on loopback. Synthetic right-turn, CP16 sharp-left, CP101 exit-right and model-observation payloads arrive with their intended meanings. The original compact decoder reads synthetic native BSM, gear, speed and blinkers correctly. Missing services are still unavailable, rather than populated with invented control/side-radar state.

The preexisting adapter could reject streams that arrived before the control socket's manifest-applied frame. The client opens those independent sockets immediately; the receiver now waits at most750ms for a matching leased session and retains peer/session validation. The bounded accept backlog supports the original13 simultaneous sockets. Explicit route withdrawal removes the previous route's guidance/lanes; old source observations cannot update the new route's clock.

## Capability boundaries

| Capability | Candidate status |
| --- | --- |
| AMap current/next maneuvers, map lane recommendations | Receiver plus original sender/serializer exercised locally |
| Tesla native BSM display | Original compact decoder compatibility verified with synthetic state; actual device not contacted |
| Native X-Pilot navigation signals / preparation | Existing integrated NavAssist coordinator; native SP/OEM/BSM/paint/driver gates unchanged; no road test |
| CP smart-speed / acceleration engine | Not ported; current turn-speed coordinator retained, no CP7706 command authority |
| Phone lane-count models | Diagnostic `modelLaneEstimate` accepted and bounded; not map-associated absolute ego-lane position |
| Full phone MNN inference | Not executed; no new camera/video endpoint provided |
| Carrot-only telemetry, remote settings, downloads / automatic passing | Unavailable; no fabricated service readiness |

The bundled models are `vlaneDay.mnn`, `vlaneNight.mnn`, `multitask.mnn`, used for phone lane estimation with an ARM64 JNI wrapper and the bundled `libVAE.so` runtime. They are not a replacement for X-Pilot's driving model or a vehicle-speed/side-BSM estimator. The App's lane fusion additionally needs a foreground road video session plus fresh7000 model geometry/lane-change telemetry; this adapter presently returns native `carState` only. Observation deserialization does not establish that inference or fusion runs. No camera transport, stereo speed or automatic passing is restored by this candidate.

Author8.1.10 defaults to suppressing highway left-fork guidance, including some genuine left exits; it also deliberately withholds unsupported Auto icons4/5. A receiver cannot reconstruct source-withdrawn navigation. Keep these App policies visible when comparing with TesNav. The CP broadcast source does not provide a complete route polyline here; no geometry or ego-lane identity is invented.

## Reproduce

Clone the pinned author snapshot outside this repository; use a JDK17+ and the existing Gradle compiler/dependency cache. The helper downloads only the author's declared org.json JVM test dependency when absent.

```sh
python3 tools/cp_upstream_probe/build.py /path/to/navipilot --output /tmp/cp-probe
python3 tools/cp_upstream_probe/run.py --build-dir /tmp/cp-probe
PYTHONPATH=plugins python3 -m pytest -q plugins/navassist/tests/test_cp_snapshot_contract.py plugins/navassist/tests/test_cp_negotiation_order.py
```

These commands bind ephemeral **127.0.0.1** sockets, use synthetic source observations, do not open device ADB/SSH, and do not publish live CAN/navigation messages. The probe is not an APK build and supplies no substitute implementation for the author's protocol classes. Original sources are hash-checked against the pinned Git commit before compilation.

1.5.7 is a local candidate; no C3/phone installation, source switch, firmware update or real-road validation is implied. Keep `ExtNavAssistEnabled` and the existing internal switches. Select CP source only deliberately at a future parked activation; TesNav and CP do not run concurrent ingress or silently fall back to each other.
