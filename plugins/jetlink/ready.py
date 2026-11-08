"""Whether the peer's built engine still belongs to the host's selected model."""
import json

SPEC_PARAM = "XpilotJetlinkSpec"
POINTERS_PARAM = "XpilotJetlinkPointers"
BIG_MODEL_PARAM = "ModelManager_ActiveBundleChestnut"


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
  """
  spec = _json_param(params, SPEC_PARAM)
  if not (spec and spec.get("ready") is True and spec.get("sha256") and spec.get("nbytes")):
    return False

  active = _json_param(params, BIG_MODEL_PARAM)
  ref = active.get("ref") if active else None
  if not isinstance(ref, str) or not ref:
    return True

  pointers = _json_param(params, POINTERS_PARAM) or {}
  pointer = pointers.get(ref)
  if not isinstance(pointer, dict) or pointer.get("oid") != spec["sha256"]:
    return False
  try:
    return not pointer.get("size") or int(pointer["size"]) == int(spec["nbytes"])
  except (KeyError, TypeError, ValueError):
    return False
