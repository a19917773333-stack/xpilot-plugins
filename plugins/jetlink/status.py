"""Labels for the Jetlink tile, kept free of UI, params and file I/O."""

STAGES = {
  "connect": "connecting",
  "download": "downloading model",
  "upload": "uploading model",
  "build": "building engine",
  "waiting": "waiting for phone",
}


def _mode_off(mode) -> bool:
  try:
    return int(mode) == 0
  except (TypeError, ValueError):
    return mode in (None, "", "off")


def tile_state(mode, status, progress, spec) -> str:
  """Say what is true now: live frames, setup state, prepared engine, or off.

  XpilotJetlinkStatus is written only while the peer serves frames. An empty value therefore does not mean the
  link is off: offroad the peer is not running, while a successful provisioning run leaves Progress/Spec ready.
  """
  if _mode_off(mode):
    return "link off"
  if isinstance(status, str) and status.strip():
    return status.strip()

  progress = progress if isinstance(progress, dict) else {}
  stage = progress.get("stage")
  stage = stage.strip().lower() if isinstance(stage, str) else ""
  if stage == "failed":
    return "setup failed"
  if stage in STAGES:
    return STAGES[stage]
  if stage == "ready":
    return "engine ready"
  if stage:
    return "preparing model"

  if isinstance(spec, dict) and spec.get("ready") is True:
    return "engine ready"
  return "waiting for phone"
