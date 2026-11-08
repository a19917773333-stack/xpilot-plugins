# Jetlink (phone model)

`perception_model` plugin. It owns `role:perception.model`, so the host stops SP's `models_manager`/`modeld` and
runs this plugin's three processes instead:

| Process | What it does |
|---|---|
| `jetlinkd` | runs whenever the link is enabled, including offroad provisioning, and holds the USB gadget |
| `jetlink_modeld` | openpilot's modeld with a model-source mailbox attached (`run_with_model_source`) |
| `jetlink_peer` | warps the camera frame modeld published, sends it over the link, writes the phone's output back |

`jetlinkd` runs while parked so the phone can connect and prepare its model. The two inference processes wait for a
drive and stop when parked.

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
- The adapter points Jetlink's LFS lookup at `/dev/shm/jetlink/lfs/.lfsconfig`, where `hf-mirror.com` is the
  first endpoint. This keeps the host checkout clean and avoids the blocked canonical HuggingFace host on
  networks where the mirror is reachable; Jetlink's built-in LFS endpoints remain as fallbacks.
- A warp build for this camera (`openpilot/selfdrive/modeld/models/big_driving_warp_*_tinygrad.pkl`), the same
  file modeld loads.
- Settings: `XpilotJetlink` on, `XpilotJetlinkMode` = `USB host` (Jetson/Mac/Linux) or `iPhone`.

## Claims and limits

- Claims `role:perception.model` and one `process:` per process above; nothing else. No CAN, no panda rules.
- The peer is **not verified on a car or against a real phone** in this release: the mailbox side is tested
  end to end against modeld's own `ModelSource`, the link and warp sides are not. `XpilotJetlinkStatus` and the
  Jetlink tile say how many frames were served.
- The upstream Jetlink hardware support is C3X/C4. Running it on a C3 is experimental; process and USB gadget
  evidence does not by itself prove that the phone app has completed its protocol handshake.
- The phone's model must answer with the head layout `openpilot/tesla/model_source.py` expects (2066 floats);
  a stateful model that keeps its history on the phone cannot, and its frames are refused.

## Tests

    cd <xpilot-plugins>
    PYTHONPATH=<xpilot>:<xpilot>/opendbc_repo python3 -m pytest -q plugins/jetlink/tests

`tests/test_mailbox.py` publishes a frame through `ModelSource`, reads it with the peer, writes the reply back and
asserts modeld adopts it — and that a stale, foreign-session or malformed reply is refused.
