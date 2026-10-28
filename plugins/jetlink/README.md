# Jetlink (phone model)

`perception_model` plugin. It owns `role:perception.model`, so the host stops SP's `models_manager`/`modeld` and
runs this plugin's three processes instead:

| Process | What it does |
|---|---|
| `jetlinkd` | holds the USB gadget for the drive and runs provisioning (jetlink's own owner) |
| `jetlink_modeld` | openpilot's modeld with a model-source mailbox attached (`run_with_model_source`) |
| `jetlink_peer` | warps the camera frame modeld published, sends it over the link, writes the phone's output back |

`jetlink_modeld` always runs the local model. A phone frame is adopted per frame, only when it lands inside
`openpilot/tesla/model_source.py`'s 60 ms deadline and passes `decode.admit`; otherwise the local frame drives.
That is why a link that is off, missing, late or foreign is a normal drive on xpilot's model, never a stall.

## Requirements

- The `jetlink` python package (the `jetlink_repo` checkout the phone apps pair with) on `PYTHONPATH`. Without it
  the plugin still loads and starts nothing, and the host's own modeld keeps running.
- A warp build for this camera (`openpilot/selfdrive/modeld/models/big_driving_warp_*_tinygrad.pkl`), the same
  file modeld loads.
- Settings: `XpilotJetlink` on, `XpilotJetlinkMode` = `USB host` (Jetson/Mac/Linux) or `iPhone`.

## Claims and limits

- Claims `role:perception.model` and one `process:` per process above; nothing else. No CAN, no panda rules.
- The peer is **not verified on a car or against a real phone** in this release: the mailbox side is tested
  end to end against modeld's own `ModelSource`, the link and warp sides are not. `XpilotJetlinkStatus` and the
  Jetlink tile say how many frames were served.
- The phone's model must answer with the head layout `openpilot/tesla/model_source.py` expects (2066 floats);
  a stateful model that keeps its history on the phone cannot, and its frames are refused.

## Tests

    cd <xpilot-plugins>
    PYTHONPATH=<xpilot>:<xpilot>/opendbc_repo python3 -m pytest -q plugins/jetlink/tests

`tests/test_mailbox.py` publishes a frame through `ModelSource`, reads it with the peer, writes the reply back and
asserts modeld adopts it — and that a stale, foreign-session or malformed reply is refused.