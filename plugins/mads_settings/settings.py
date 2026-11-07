"""Mapping from the plugin's own switch values to the host MADS params.

Failure cases kept in mind: a missing or non-numeric stored value falls back to the declared default; an
out-of-range steering mode is clamped to DISENGAGE; a host key the car removed (Tesla drops
MadsMainCruiseAllowed) is not recreated.
"""
STEERING_MODE = {"0": 0, "1": 1, "2": 2}
SCREEN_BUTTON = {"0": 0, "1": 1, "2": 2, "3": 3}


def _bool(view, key: str, default: bool) -> bool:
  try:
    value = view.get_bool(key)
  except Exception:
    return default
  if isinstance(value, str):
    return value.strip() in ("1", "true", "True")
  return bool(value)


def _choice(view, key: str, table: dict[str, int], default: int) -> int:
  try:
    raw = str(view.get(key, return_default=True)).strip()
  except Exception:
    return default
  return table.get(raw, default)


def read(view) -> dict:
  """Host Params key -> value, in write order. Missing keys are left untouched by the caller."""
  return {
    "Mads": _bool(view, "ExtMadsEnabled", True),
    "MadsSteeringMode": _choice(view, "ExtMadsSteeringMode", STEERING_MODE, 2),
    "MadsUnifiedEngagementMode": _bool(view, "ExtMadsUnified", True),
    "TeslaMadsScreenButton": _choice(view, "ExtMadsScreenButton", SCREEN_BUTTON, 0),
  }
