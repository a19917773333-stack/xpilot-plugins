# Jetlink (phone model)

`perception_model` plugin. It owns `role:perception.model`, so the host stops SP's `models_manager`/`modeld` and
runs this plugin's three processes instead:

| Process | What it does |
|---|---|
| `jetlinkd` | runs whenever the link is enabled, including offroad provisioning, and holds the USB gadget |
| `jetlink_modeld` | openpilot's modeld with a model-source mailbox attached (`run_with_model_source`) |
| `jetlink_peer` | keeps the phone protocol connected offroad, then warps and sends modeld's camera frames onroad |

`jetlinkd` runs while parked so the phone can connect and prepare its model. Once the ready spec names a phone
engine, `jetlink_peer` also runs offroad: it sends `hello`, passes the phone's `sleep_after` policy back to the
owner, loads the named engine, and keeps its USB lease open without sending unsupported pings.
`jetlink_modeld` still waits for a drive; when the drive mailbox appears, the already-open peer session
switches to camera frames.

The first inference may spend up to 120 seconds loading the selected engine on the phone. That request keeps the
same USB lease open while the local model drives. After the first valid reply, normal frames return to the 50 ms
mailbox deadline, so a late or dead phone still falls back locally instead of stalling the drive.
A single frame held past that deadline stays on the same session; only a sustained host stall ends the link.
When the USB transmit queue is busy, the peer skips that phone frame instead of using a short blocking send timeout,
which could abort FunctionFS and force the host to re-enumerate. Before each send it drains replies that arrived
after the previous hold, keeping late frames from accumulating in flight.

When modeld retires its mailbox or camerad stops publishing, `jetlink_peer` exits instead of replaying
an unlinked frame file. The host manager then restarts it, which reopens the USB lease and repeats the phone
handshake before the next drive.

`jetlink_modeld` always runs the local model. A phone frame is adopted per frame, only when it lands inside
`openpilot/tesla/model_source.py`'s 60 ms deadline and passes `decode.admit`; otherwise the local frame drives.
That is why a link that is off, missing, late or foreign is a normal drive on xpilot's model, never a stall.

## Requirements

- The `jetlink` python package (the `jetlink_repo` checkout the phone apps pair with) on `PYTHONPATH`. Without it
  the plugin still loads and starts nothing, and the host's own modeld keeps running.
- On this C3 deployment the API 3 runtime is kept at `/data/jetlink-runtime-491cf1ef`; the plugin adds that
  directory to both the manager process and provisioning child environment. The old `/data/openpilot/jetlink`
  checkout link is no longer a persistent storage location because host updates can remove it.
- `_boot/xpilot_ext.py` exposes installed store plugins to Jetlink's provisioning child. The manager creates that
  package dynamically, but Python subprocesses do not inherit it through normal `PYTHONPATH`.
- `XpilotJetlinkPointers`, `XpilotJetlinkProgress` and `XpilotJetlinkSpec` are JSON params. The adapter also
  decodes the Python text written by 1.0.8, so upgrading keeps the already known model pointer.
- The model comes from xpilot's model manager: Jetlink follows `ModelManager_ActiveBundleChestnut` and reads
  `ModelManager_ModelsCache_Chestnut` at the host's `REQUIRED_JSON_VERSION`. Selecting `BMRLNAP Model v6` in
  the host therefore provisions and runs that model on the phone instead of Jetlink's built-in default.
- A ready `XpilotJetlinkSpec` needs the model's `sha256` and `nbytes`. The `onnx_path` is optional: the peer asks
  the phone for that already-built engine by identity instead of skipping preparation when the comma path is gone.
- Offroad peer startup is gated on that ready spec. This avoids holding the owner's loan while the model still has to
  be provisioned. The spec must also resolve to the host's selected model; an old ready spec does not take the USB
  lease after the user switches models. If the phone reports that the engine is missing, the peer marks the stale spec
  unready and exits so `jetlinkd` can provision it again.
- The adapter points Jetlink's LFS lookup at `/dev/shm/jetlink/lfs/.lfsconfig`, where `hf-mirror.com` is the
  first endpoint. This keeps the host checkout clean and avoids the blocked canonical HuggingFace host on
  networks where the mirror is reachable; Jetlink's built-in LFS endpoints remain as fallbacks.
- The device's own QCOM warp for this camera (`openpilot/selfdrive/modeld/models/driving_warp_*_tinygrad.pkl`).
  `big_driving_warp_*` is chestnut's eGPU build and must not be loaded as the local C3 warp.
- Settings: `XpilotJetlink` on, `XpilotJetlinkMode` = `USB host` (Jetson/Mac/Linux) or `iPhone`.

## Claims and limits

- Claims `role:perception.model` and one `process:` per process above; nothing else. No CAN, no panda rules.
- The peer is **not verified on a car or against a real phone** in this release: the mailbox side is tested
  end to end against modeld's own `ModelSource`, the link and warp sides are not. `XpilotJetlinkStatus` and the
  Jetlink tile says how many frames the peer served. When the peer is not running, it reports the provisioning
  stage instead, so a ready engine is not shown as `link off` merely because `XpilotJetlinkStatus` is empty.
- The upstream Jetlink hardware support is C3X/C4. Running it on a C3 is experimental; process and USB gadget
  evidence does not by itself prove that the phone app has completed its protocol handshake.
- The phone's model must answer with the head layout `openpilot/tesla/model_source.py` expects (2066 floats);
  a stateful model that keeps its history on the phone cannot, and its frames are refused.

## Tests

    cd <xpilot-plugins>
    PYTHONPATH=<xpilot>:<xpilot>/opendbc_repo python3 -m pytest -q plugins/jetlink/tests

`tests/test_mailbox.py` publishes a frame through `ModelSource`, reads it with the peer, writes the reply back and
asserts modeld adopts it — and that a stale, foreign-session or malformed reply is refused.
