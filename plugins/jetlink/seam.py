"""The xpilot side of jetlink's Openpilot interface (jetlink.openpilot.interface), and jetlinkd.

jetlink never imports openpilot: it defines what it needs as one Protocol and one adapter module implements it.
This is that module for xpilot, plus the entry point of jetlinkd, the resident gadget owner.
tests/test_seam.py runs jetlink's own conformance() against Adapter, so a member that drifts fails here.
"""
import os
from pathlib import Path

API = 3  # the jetlink.openpilot API this adapter is written to
MODES = ("off", "usb", "ios")
# the params jetlink reads and writes; the model manager's big-model slot is not part of xpilot's plugin store, so
# jetlink runs its own default big model
KEYS = {"link": "XpilotJetlinkMode", "offroad": "IsOffroad", "progress": "XpilotJetlinkProgress",
        "spec": "XpilotJetlinkSpec", "pointers": "XpilotJetlinkPointers",
        "big_model": None, "catalog": None, "charge_phone": None}
# comma's chestnut, running and in its ROM: the USB-C port hosts one and is never held as a jetlink device
CHESTNUT_IDS = frozenset({(0xADD1, 0x0001), (0xADD1, 0x0002), (0x3801, 0x0001),
                          (0x174C, 0x2464), (0x174C, 0x2463)})
OWNER_LOG = Path("/data/log/jetlink-owner.log")


def params_dir() -> Path:
  """The params store's directory, by params.cc's rule, worked out per call so it follows OPENPILOT_PREFIX."""
  prefix = os.environ.get("OPENPILOT_PREFIX", "")
  root = os.environ.get("PARAMS_ROOT")
  if root is None:
    root = "/data/params" if os.path.isfile("/AGNOS") else os.path.join(os.environ.get("HOME", ""), ".comma" + prefix, "params")
  return Path(root) / os.environ.get("OPENPILOT_PREFIX", "d")


def keys():
  from jetlink.openpilot.interface import Keys
  return Keys(**KEYS)


def _models_dir() -> Path:
  from openpilot.selfdrive.modeld.helpers import MODELS_DIR
  return Path(MODELS_DIR)


def owner_config():
  """What jetlinkd needs, data only: the owner stays at the standard library plus jetlink.comma."""
  from jetlink.openpilot.interface import OwnerConfig

  from openpilot.common.basedir import BASEDIR
  # the provisioning run starts in the checkout with every path this process already has, so `jetlink` and
  # `openpilot` resolve there exactly as they do here
  return OwnerConfig(params_dir=params_dir(), keys=keys(), chestnut_ids=CHESTNUT_IDS, adapter=__name__,
                     cwd=Path(BASEDIR), env={"PYTHONPATH": os.pathsep.join(p for p in (BASEDIR, os.environ.get("PYTHONPATH", "")) if p)},
                     log_file=OWNER_LOG)


def main() -> None:
  """jetlinkd: hold the USB gadget for the whole drive; manager stops this process."""
  from jetlink.openpilot.owner import main as run_owner
  run_owner(owner_config())


def adapter():
  return Adapter()


class Adapter:
  """jetlink.openpilot.interface.Openpilot over xpilot."""

  def __init__(self):
    from openpilot.common.swaglog import cloudlog
    from openpilot.common.basedir import BASEDIR
    self.keys = keys()
    self.log = cloudlog
    self.basedir = Path(BASEDIR)
    self.catalog_selector = 0
    self._stores: dict[Path, object] = {}
    self._geometry: tuple[int, int, int, int] | None = None

  def _params(self):
    where = params_dir()
    store = self._stores.get(where)
    if store is None:
      from openpilot.common.params import Params
      store = self._stores[where] = Params()
    return store

  def params_dir(self) -> Path:
    return params_dir()

  def get(self, key: str):
    try:
      return self._params().get(key)
    except Exception:
      return None

  def put(self, key, value, *, block: bool = False) -> None:
    self._params().put(key, value, block=block)

  def remove(self, key: str) -> None:
    self._params().remove(key)

  def chestnut_present(self) -> bool:
    """Is comma's chestnut fitted? modeld's own answer, so the owner caches it the same way."""
    try:
      from openpilot.system.hardware import chestnut_present
      return bool(chestnut_present())
    except Exception:
      return False

  def camera(self) -> tuple[int, int, int, int]:
    """(cam_w, cam_h, model_w, model_h) of the warp this checkout carries: the biggest built one, which is
    modeld's main camera on a comma three."""
    if self._geometry is None:
      found = []
      for path in _models_dir().glob("big_driving_warp_*x*_tinygrad.pkl"):
        try:
          width, height = (int(v) for v in path.stem.split("_")[-2].split("x"))
        except ValueError:
          continue
        found.append((width, height))
      self._geometry = (*max(found), *max(found)) if found else (0, 0, 0, 0)
    return self._geometry

  def warp_path(self, cam_w: int, cam_h: int, model_w: int, model_h: int) -> Path:
    return _models_dir() / f"big_driving_warp_{cam_w}x{cam_h}_tinygrad.pkl"

  def model_root(self) -> Path:
    """Where jetlink keeps its downloads: next to the models it serves."""
    return _models_dir()

  def model_face(self):
    """What openpilot's modeld reads off a model: comma's parser, constants and action function."""
    from jetlink.openpilot.interface import ModelFace
    from openpilot.selfdrive.modeld.constants import ModelConstants
    from openpilot.selfdrive.modeld.modeld import LAT_SMOOTH_SECONDS, LONG_SMOOTH_SECONDS, get_action_from_model
    from openpilot.selfdrive.modeld.parse_model_outputs import Parser
    return ModelFace(parser=Parser, frame_size=_frame_size, desire_len=ModelConstants.DESIRE_LEN,
                     constants=ModelConstants, lat_smooth_seconds=LAT_SMOOTH_SECONDS,
                     long_smooth_seconds=LONG_SMOOTH_SECONDS, get_action_from_model=get_action_from_model)

  def in_control(self) -> bool:
    """Is anything in control? The phone path keeps its own model running and swaps per frame through the
    mailbox, so this only answers jetlink's joining model, which this plugin never builds: stay conservative."""
    return True

  def event(self, name: str, **fields) -> None:
    try:
      from openpilot.common.swaglog import cloudlog
      cloudlog.event(name, **fields)
    except Exception:
      pass


def _frame_size(w: int, h: int) -> int:
  from openpilot.common.transformations.camera import get_nv12_info
  return get_nv12_info(w, h)[3]