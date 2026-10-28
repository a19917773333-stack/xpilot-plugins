"""Jetlink: the driving model runs on a phone, Mac or Jetson on the USB cable.

Failure cases:
- No jetlink checkout: the manifest still loads, `available()` is False and no process starts, so the host's own
  modeld keeps running (the role is claimed but nothing replaces it, which the host treats as a plugin that runs
  no process).
- Link setting Off: the same, so switching the link off needs no plugin reload.
- Peer, link or phone failing mid-drive: modeld publishes its own model. The phone output is only adopted when a
  reply lands inside the mailbox deadline, so a late or missing reply is a local frame, never a stall.
- Host without the model-source IPC: runner's import of run_with_model_source fails, the host records the plugin
  and keeps sp_models' modeld.
"""
from openpilot.tesla.plugin import Plugin

MODES = ("off", "usb", "ios")
MODE_PARAM = "XpilotJetlinkMode"
# process name -> module inside this package, in the order manager starts them
PROCESSES = (("jetlinkd", "seam"), ("jetlink_modeld", "runner"), ("jetlink_peer", "peer"))


def mode(params) -> str:
  """The link setting as jetlink names it: 'off' when unset, unreadable or unknown."""
  try:
    index = int(params.get(MODE_PARAM))
  except (TypeError, ValueError):
    return "off"
  return MODES[index] if 0 <= index < len(MODES) else "off"


def available() -> bool:
  """Is the jetlink package importable? Without it none of these processes can run."""
  import importlib.util
  try:
    return importlib.util.find_spec("jetlink") is not None
  except Exception:
    return False


def run_processes(params, CP) -> bool:
  """Should manager keep jetlink's processes up: the link is on and jetlink is installed."""
  return mode(params) != "off" and available()


def _onroad(started, params, CP) -> bool:
  return started and run_processes(params, CP)


class Jetlink(Plugin):
  """Owns role:perception.model. Its modeld runs the local model and adopts phone frames when they arrive."""

  @classmethod
  def processes(cls) -> list:
    from openpilot.system.manager.process import PythonProcess
    return [PythonProcess(name, f"{__package__}.{module}", _onroad) for name, module in PROCESSES]