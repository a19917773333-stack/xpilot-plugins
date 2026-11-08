"""Jetlink: the driving model runs on a phone, Mac or Jetson on the USB cable.

Failure cases:
- No jetlink checkout: the manifest still loads, `available()` is False and no process starts, so the host's own
  modeld keeps running (the role is claimed but nothing replaces it, which the host treats as a plugin that runs
  no process).
- Link setting Off: the same, so switching the link off needs no plugin reload.
- Persistent runtime present but checkout link gone: the plugin adds the runtime root to sys.path before checking for
  the jetlink package, so an update or reboot that removes the checkout link does not disable the phone model.
- Peer, link or phone failing mid-drive: modeld publishes its own model. The phone output is only adopted when a
  reply lands inside the mailbox deadline, so a late or missing reply is a local frame, never a stall.
- Host without the model-source IPC: runner's import of run_with_model_source fails, the host records the plugin
  and keeps sp_models' modeld.
"""
from pathlib import Path

from openpilot.tesla.plugin import Plugin
from .ready import peer_ready

MODES = ("off", "usb", "ios")
MODE_PARAM = "XpilotJetlinkMode"
JETLINK_RUNTIME_VERSION = "0.9.0"
JETLINK_RUNTIME_DIR = Path("/data/jetlink-runtime-v0.9.0")
# process name -> module inside this package, in the order manager starts them
PROCESSES = (("jetlinkd", "seam"), ("jetlink_modeld", "runner"), ("jetlink_peer", "peer"))


def ensure_runtime() -> bool:
  """Put the persistent jetlink runtime on sys.path; checkout links do not survive every host update."""
  import importlib
  import sys

  if not JETLINK_RUNTIME_DIR.is_dir():
    return False
  runtime = str(JETLINK_RUNTIME_DIR)
  if runtime not in sys.path:
    sys.path.insert(0, runtime)
    importlib.invalidate_caches()
  return True


def mode(params) -> str:
  """The link setting as jetlink names it: 'off' when unset, unreadable or unknown."""
  try:
    index = int(params.get(MODE_PARAM))
  except (TypeError, ValueError):
    return "off"
  return MODES[index] if 0 <= index < len(MODES) else "off"


def available() -> bool:
  """Is the jetlink package importable? Without it none of these processes can run."""
  ensure_runtime()
  import importlib
  try:
    return importlib.import_module("jetlink").__version__ == JETLINK_RUNTIME_VERSION
  except Exception:
    return False


def run_processes(params, CP) -> bool:
  """Should manager keep jetlink's processes up: the link is on and jetlink is installed."""
  return mode(params) != "off" and available()


def _onroad(started, params, CP) -> bool:
  return started and run_processes(params, CP)


def _owner(started, params, CP) -> bool:
  """The USB owner provisions while parked as well as holding the link onroad."""
  return run_processes(params, CP)




def _peer(started, params, CP) -> bool:
  """The peer also connects offroad once the phone has a prepared engine.

  Offroad peer use must not hold the gadget while the owner still has model
  provisioning to do. A ready spec from the previous selection is stale until
  its pointer matches the host's current model slot.
  """
  return run_processes(params, CP) and peer_ready(params)


PROCESS_GATES = {"jetlinkd": _owner, "jetlink_modeld": _onroad, "jetlink_peer": _peer}


class Jetlink(Plugin):
  """Owns role:perception.model. Its modeld runs the local model and adopts phone frames when they arrive."""

  @classmethod
  def prepare_install(cls) -> bool:
    """The store probe checks the device warp before activating a model-role plugin."""
    try:
      if not available():
        return False
      from jetlink.openpilot.warp import Warps
      from .seam import adapter
      warps = Warps(adapter())
      geometry = warps.geometry()
      if not warps.is_cached(*geometry):
        return False
      warps.load(*geometry)
      return True
    except Exception:
      return False

  @classmethod
  def processes(cls) -> list:
    from openpilot.system.manager.process import PythonProcess
    return [PythonProcess(name, f"{__package__}.{module}", PROCESS_GATES[name]) for name, module in PROCESSES]
