"""Whether the peer's built engine still belongs to the host's selected model."""
import json
from pathlib import Path

SPEC_PARAM = "XpilotJetlinkSpec"
POINTERS_PARAM = "XpilotJetlinkPointers"
BIG_MODEL_PARAM = "ModelManager_ActiveBundleChestnut"


def _models_index_path() -> Path:
  """The copy of Jetlink's model index that the runtime keeps beside its models."""
  from openpilot.common.hardware.hw import Paths
  return Path(Paths.model_root()) / "jetlink" / "index.json"


def _parse_index(data):
  from jetlink.registry.index import parse_index
  return parse_index(data)


def _load_index():
  """Jetlink's parsed model index, or None before it has ever been fetched."""
  try:
    return _parse_index(json.loads(_models_index_path().read_text()))
  except Exception:
    return None


def _matches_pointer(pointer, spec: dict) -> bool:
  if pointer is None or pointer.oid != spec["sha256"]:
    return False
  try:
    return int(pointer.size) == int(spec["nbytes"])
  except (KeyError, TypeError, ValueError):
    return False


def _pointer_from_index(index, ref: str | None):
  """The index's pointer for a ref, falling to its default when no ref was picked."""
  if not ref and index.models:
    ref = index.default or index.models[0].ref
  return index.pointer(ref) if ref else None


def _pointer_from_legacy(params, ref: str | None):
  """API 3's pointer map, used only until the first v0.9.0 index is fetched."""
  pointers = _json_param(params, POINTERS_PARAM) or {}
  pointer = pointers.get(ref) if ref else None
  return pointer if isinstance(pointer, dict) else None

def _json_param(params, key: str) -> dict | None:
  """A JSON object from plugin or host params, including values saved by older releases."""
  try:
    value = params.get(key)
    if isinstance(value, str):
      value = json.loads(value)
  except (TypeError, ValueError):
    return None
  return value if isinstance(value, dict) else None


def peer_ready(params) -> bool:
  """Is the built engine the one the host's current model resolves to?

  Refuse a ready spec from the previous selection while provisioning resolves
  the new model. Otherwise the offroad peer takes the USB lease first and the
  owner can never run the provisioning pass that would replace that spec.

  v0.9.0 resolves the host pick through Jetlink's model index. The old pointer
  map is an upgrade fallback only while that index does not exist or cannot be
  parsed; it must not let through a ref missing from an otherwise valid index.
  """
  spec = _json_param(params, SPEC_PARAM)
  if not (spec and spec.get("ready") is True and spec.get("sha256") and spec.get("nbytes")):
    return False

  active = _json_param(params, BIG_MODEL_PARAM)
  ref = active.get("ref") if active else None
  if not isinstance(ref, str) or not ref:
    ref = None

  index = _load_index()
  if index is not None:
    return _matches_pointer(_pointer_from_index(index, ref), spec)

  # Before the first index fetch, preserve a previously provisioned engine.
  if ref is None:
    return True
  pointer = _pointer_from_legacy(params, ref)
  if pointer is None:
    return False
  return _matches_pointer(type("Pointer", (), {"oid": pointer.get("oid"), "size": pointer.get("size")}), spec)
