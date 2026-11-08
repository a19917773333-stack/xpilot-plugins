"""The xpilot side of jetlink's Openpilot interface (jetlink.openpilot.interface), and jetlinkd.

jetlink never imports openpilot: it defines what it needs as one Protocol and one adapter module implements it.
This is that module for xpilot, plus the entry point of jetlinkd, the resident gadget owner.
tests/test_seam.py runs jetlink's own conformance() against Adapter, so a member that drifts fails here.
"""
import ast
import json
import os
from pathlib import Path

from .plugin import JETLINK_RUNTIME_DIR

API = 3  # the jetlink.openpilot API this adapter is written to
MODES = ("off", "usb", "ios")
# the params jetlink reads and writes; the model manager's big-model slot is not part of xpilot's plugin store, so
# jetlink runs its own default big model
KEYS = {"link": "XpilotJetlinkMode", "offroad": "IsOffroad", "progress": "XpilotJetlinkProgress",
        "spec": "XpilotJetlinkSpec", "pointers": "XpilotJetlinkPointers",
        "big_model": None, "catalog": None, "charge_phone": None}
JSON_KEYS = frozenset({KEYS["progress"], KEYS["spec"], KEYS["pointers"]})
# comma's chestnut, running and in its ROM: the USB-C port hosts one and is never held as a jetlink device
CHESTNUT_IDS = frozenset({(0xADD1, 0x0001), (0xADD1, 0x0002), (0x3801, 0x0001),
                          (0x174C, 0x2464), (0x174C, 0x2463)})
OWNER_LOG = Path("/data/log/jetlink-owner.log")
OWNER_PARAMS_DIR = Path("/dev/shm/jetlink/params")
LFS_CONFIG_DIR = Path("/dev/shm/jetlink/lfs")
LFS_MIRROR = "https://hf-mirror.com/commaai/openpilot_driving_models.git/info/lfs"
BOOTSTRAP_DIR = Path(__file__).resolve().parent / "_boot"


def _host_params_dir() -> Path:
  """The params store's directory, by params.cc's rule, worked out per call so it follows OPENPILOT_PREFIX."""
  prefix = os.environ.get("OPENPILOT_PREFIX", "")
  root = os.environ.get("PARAMS_ROOT")
  if root is None:
    root = "/data/params" if os.path.isfile("/AGNOS") else os.path.join(os.environ.get("HOME", ""), ".comma" + prefix, "params")
  return Path(root) / os.environ.get("OPENPILOT_PREFIX", "d")


def _plugin_params_dir() -> Path:
  """The file-backed store downloaded plugins use for params absent from params_keys.h."""
  from openpilot.tesla.manifest import INSTALL_DIR
  return Path(INSTALL_DIR) / ".params"


def params_dir() -> Path:
  """A stable directory exposing the two params stores jetlink reads.

  Downloaded-plugin params live in xpilot_plugins/.params, while IsOffroad and
  the other host params live in params.cc's directory. jetlink's lightweight
  owner intentionally reads plain files, so expose one directory containing
  links to both. ParamsView replaces files atomically, which the links follow.
  """
  host_dir = _host_params_dir()
  plugin_dir = _plugin_params_dir()
  OWNER_PARAMS_DIR.mkdir(parents=True, exist_ok=True)
  for key in (key for key in KEYS.values() if key):
    source = host_dir / key if key == KEYS["offroad"] else plugin_dir / key
    target = OWNER_PARAMS_DIR / key
    temporary = OWNER_PARAMS_DIR / f".{key}.{os.getpid()}"
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(source)
    os.replace(temporary, target)
  return OWNER_PARAMS_DIR


def keys():
  from jetlink.openpilot.interface import Keys
  return Keys(**KEYS)


def decode_param(key: str, value):
  """Decode JSON params saved by 1.0.8 as Python ``str(dict)`` text."""
  if key not in JSON_KEYS or not isinstance(value, str):
    return value
  for decode in (json.loads, ast.literal_eval):
    try:
      return decode(value)
    except (TypeError, ValueError, SyntaxError):
      pass
  return value


def migrate_json_params() -> None:
  """Atomically rewrite 1.0.8's ``str(dict)`` files before ParamsView reads them as JSON."""
  directory = _plugin_params_dir()
  for key in JSON_KEYS:
    path = directory / key
    try:
      raw = path.read_text()
      json.loads(raw)
      continue
    except FileNotFoundError:
      continue
    except (TypeError, ValueError):
      pass
    try:
      value = ast.literal_eval(raw)
    except (TypeError, ValueError, SyntaxError):
      continue
    temporary = directory / f".{key}.{os.getpid()}"
    temporary.write_text(json.dumps(value))
    os.replace(temporary, path)


def _models_dir() -> Path:
  from openpilot.selfdrive.modeld.helpers import MODELS_DIR
  return Path(MODELS_DIR)


def lfs_config_dir() -> Path:
  """A checkout-free LFS config with a reachable mirror as the first endpoint.

  Jetlink reads only OP.basedir/.lfsconfig. Pointing that at /dev/shm keeps the
  host checkout clean and lets models use the mirror before built-in fallbacks.
  """
  LFS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
  target = LFS_CONFIG_DIR / ".lfsconfig"
  temporary = LFS_CONFIG_DIR / f".lfsconfig.{os.getpid()}"
  temporary.write_text(f"[lfs]\n\turl = {LFS_MIRROR}\n\tlocksverify = false\n")
  os.replace(temporary, target)
  return LFS_CONFIG_DIR


def owner_pythonpath(basedir: Path) -> str:
  """Paths the provisioning child needs, including the runtime that survives checkout updates."""
  paths = [str(BOOTSTRAP_DIR), str(basedir)]
  if JETLINK_RUNTIME_DIR.is_dir():
    paths.append(str(JETLINK_RUNTIME_DIR))
  paths.extend(path for path in os.environ.get("PYTHONPATH", "").split(os.pathsep) if path)
  return os.pathsep.join(dict.fromkeys(paths))


def owner_config():
  """What jetlinkd needs, data only: the owner stays at the standard library plus jetlink.comma."""
  from jetlink.openpilot.interface import OwnerConfig

  from openpilot.common.basedir import BASEDIR
  # the provisioning run starts in the checkout with every path this process already has, so `jetlink` and
  # `openpilot` resolve there exactly as they do here
  return OwnerConfig(params_dir=params_dir(), keys=keys(), chestnut_ids=CHESTNUT_IDS, adapter=__name__,
                     cwd=Path(BASEDIR), env={"PYTHONPATH": owner_pythonpath(Path(BASEDIR))},
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
    migrate_json_params()
    self.keys = keys()
    self.log = cloudlog
    self.basedir = lfs_config_dir()
    self.catalog_selector = 0
    self._stores: dict[Path, object] = {}
    self._geometry: tuple[int, int, int, int] | None = None

  def _params(self):
    where = params_dir()
    store = self._stores.get(where)
    if store is None:
      from openpilot.common.params import Params
      from openpilot.tesla.plugin_params import ParamsView
      store = self._stores[where] = ParamsView(Params())
    return store

  def params_dir(self) -> Path:
    return params_dir()

  def get(self, key: str):
    try:
      return decode_param(key, self._params().get(key))
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
    """(cam_w, cam_h, model_w, model_h) for the device's own QCOM warp.

    ``big_*`` is chestnut's eGPU build and loads an AMD device even when the file sits on a C3.
    """
    if self._geometry is None:
      found = []
      from openpilot.common.transformations.model import MEDMODEL_INPUT_SIZE

      for path in _models_dir().glob("driving_warp_*x*_tinygrad.pkl"):
        try:
          width, height = (int(v) for v in path.stem.split("_")[-2].split("x"))
        except ValueError:
          continue
        found.append((width, height))
      self._geometry = (*max(found), *MEDMODEL_INPUT_SIZE) if found else (0, 0, *MEDMODEL_INPUT_SIZE)
    return self._geometry

  def warp_path(self, cam_w: int, cam_h: int, model_w: int, model_h: int) -> Path:
    return _models_dir() / f"driving_warp_{cam_w}x{cam_h}_tinygrad.pkl"

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
  from openpilot.system.camerad.cameras.nv12_info import get_nv12_info
  return get_nv12_info(w, h)[3]
