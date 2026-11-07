"""CP may prepare or veto SP lane changes, never bypass its automatic mode."""

from openpilot.tesla.lane_policy import LaneChangeLimits
from .settings import CPSettings


def side(direction):
  value = str(getattr(direction, 'raw', direction)).lower()
  return {'1': 'left', '2': 'right'}.get(value, value)


class CPLanePolicy:
  def __init__(self, params):
    self.params = params
    self._msgs = None
    self.owned = None

  def _read(self):
    # Only these two BOOLs are consumed here; avoid reading all native tuning keys
    # each frame while keeping explicit disable effective immediately.
    return CPSettings(enabled=self.params.get_bool('ExtCpNavEnabled'), lane_changes=self.params.get_bool('ExtCpNavLaneChanges'))

  def intent(self):
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs = PluginMsgs()
    d = self._msgs.fresh('lanes.intent').get('cp_nav') or {}
    if self._read().enabled and d.get('valid') is True and d.get('signalRequested') is True:
      self.owned = d.get('direction')
      return d
    return {}

  def allow(self, carstate, direction, default):
    d = self.intent()
    if d:
      settings = self._read()
      return bool(settings.lane_changes and default and not d.get('turnOnly')
                  and d.get('laneChangeAllowed') is True
                  and d.get('direction') == side(direction))
    return bool(default and self.owned is None)

  def constraints(self, carstate, direction):
    d = self.intent()
    if d:
      settings = self._read()
      opposite = getattr(carstate, 'rightBlinker' if d.get('direction') == 'left' else 'leftBlinker', True)
      turn = d.get('turnOnly') is True
      ready = bool(settings.lane_changes and not opposite and not turn
                   and d.get('laneChangeAllowed') is True)
      return LaneChangeLimits(allow_start=ready, allow_continue=ready,
                              turn_only=turn and not opposite, suppress_turn=not turn)
    if self.owned is not None:
      if getattr(carstate, 'leftBlinker', False) or getattr(carstate, 'rightBlinker', False):
        return LaneChangeLimits(allow_start=False, allow_continue=False, suppress_turn=True)
      self.owned = None
    return LaneChangeLimits()
