"""Mapping from the plugin switches to the host cruise params.

Failure cases: a missing or non-numeric stored value falls back to the default; the initial speed is clamped to the
declared range; MadsMainCruiseAllowed is only written when the car still has the key.
"""
MIN_SPEED, MAX_SPEED = 20, 160


def _bool(view, key: str, default: bool) -> bool:
  try:
    value = view.get_bool(key)
  except Exception:
    return default
  if isinstance(value, str):
    return value.strip() in ("1", "true", "True")
  return bool(value)


def _int(view, key: str, default: int, low: int, high: int) -> int:
  try:
    value = int(str(view.get(key, return_default=True)).strip())
  except Exception:
    return default
  return min(max(value, low), high)


def read(view, host_has_main_cruise: bool = True) -> dict:
  values = {
    "IntelligentCruiseButtonManagement": _bool(view, "ExtCruiseIcbm", False),
    "SmartCruiseControlVision": _bool(view, "ExtCruiseSccVision", False),
    "SmartCruiseControlMap": _bool(view, "ExtCruiseSccMap", False),
    "InitialCruiseSpeedKph": _int(view, "ExtCruiseInitialSpeed", 40, MIN_SPEED, MAX_SPEED),
  }
  if host_has_main_cruise:
    values["MadsMainCruiseAllowed"] = _bool(view, "ExtCruiseMainCruise", True)
  return values
