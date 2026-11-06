from dataclasses import fields, replace
from typing import Any

from openpilot.common.params import UnknownKeyName

from .registry import BackendSpec
from .tuning import LongitudinalTuning, VALUE_SPECS, backend_values


def _ramp(current: LongitudinalTuning, target: LongitudinalTuning, dt: float) -> LongitudinalTuning:
  if dt <= 0:
    return current
  changes = {}
  for field in fields(current):
    old = getattr(current, field.name)
    new = getattr(target, field.name)
    rate = VALUE_SPECS[field.name][3]
    changes[field.name] = old + max(-rate * dt, min(rate * dt, new - old))
  return replace(current, **changes)


class TuningController:
  """Poll a validated backend snapshot and retain the last known-good revision."""
  def __init__(self, params: Any, backend: BackendSpec, poll_interval: float = 1.0):
    self.params = params
    self.backend = backend
    self.poll_interval = poll_interval
    self.poll_elapsed = poll_interval
    self.current = LongitudinalTuning()
    self.target = self.current
    self.initialized = False

  def update(self, dt: float) -> LongitudinalTuning:
    self.poll_elapsed += max(dt, 0.0)
    if self.poll_elapsed >= self.poll_interval:
      self.poll_elapsed = 0.0
      try:
        target = backend_values(self.params, self.backend)
      except (ValueError, UnknownKeyName):
        target = None
      if target is not None:
        self.target = target
        if not self.initialized:
          self.current = target
          self.initialized = True
    self.current = _ramp(self.current, self.target, dt)
    return self.current
