"""Navigation consumes its own fresh messages; all outputs are vetoes or preparation.

An expired owned lamp cannot fall through to SP's automatic default while still
physically on. It does not mean that the target lane has become clear.
"""
from __future__ import annotations

import time

from openpilot.tesla.lane_policy import LaneChangeLimits
from .phone import PhoneBlindspotAssist
from .settings import read as read_settings


def _side(direction):
  raw = getattr(direction, 'raw', direction)
  try:
    return {1: 'left', 2: 'right'}.get(int(raw), 'none')
  except (TypeError, ValueError):
    name = str(raw).lower()
    return 'left' if 'left' in name else 'right' if 'right' in name else 'none'


class NavLanePolicy:
  def __init__(self, params):
    self.params = params
    self.settings = read_settings(params)
    self._msgs = None
    self._last = {}
    self._last_poll = -1.
    self._phone = PhoneBlindspotAssist(mode='assist' if self.settings.phone_assist_enabled else 'shadow')
    self._phone_t = 0.
    self._phone_states = None
    self._owned_side = None
    self._manual_side = None
    self._turn_only = False
    self._suppress_turn = False

  def _poll(self):
    now = time.monotonic()
    if now-self._last_poll < .001:
      return self._last
    self._last_poll = now
    try:
      if self._msgs is None:
        from openpilot.tesla.plugins import PluginMsgs
        self._msgs = PluginMsgs()
      self._last = {kind: self._msgs.fresh(kind).get('navassist') for kind in
                    ('oem.lanes', 'lanes.intent', 'lanes.topology')}
    except Exception:
      self._last = {}
    if now-self._phone_t >= .1:
      self._phone_t = now
      self._phone_states = self._phone.read(time.monotonic_ns())
    return self._last

  def _driver_lamp(self, carstate, intent):
    left = bool(getattr(carstate, 'leftBlinker', False))
    right = bool(getattr(carstate, 'rightBlinker', False))
    physical = 'left' if left and not right else 'right' if right and not left else None
    if physical != self._manual_side:
      self._manual_side = None
    if physical and self._owned_side is None and not intent.get('signalRequested'):
      self._manual_side = physical
    return physical is not None and physical == self._manual_side

  def _blocked(self, side, last, *, navigation=True):
    oem, topology = last.get('oem.lanes') or {}, last.get('lanes.topology') or {}
    reasons = oem.get('blockReasons') or []
    index = 0 if side == 'left' else 1
    phone_only = len(reasons) > index and reasons[index] == 'phoneBlindspot'
    # Aggregated phone evidence belongs to navigation preparation. It must not
    # replace native SP admission for the driver's own lamp. Explicit OEM veto
    # remains independent of the aggregate's two-frame confirmation.
    blocked = bool(oem.get(side+'ExplicitBlock'))
    blocked |= bool(oem.get(side+'Blocked')) and (navigation or not phone_only)
    blocked |= bool(oem.get(side+'AvailabilityBlock')) and not bool(topology.get('valid'))
    if navigation and self._phone.enabled and self._phone_states is not None and side in ('left', 'right'):
      blocked |= self._phone_states[0 if side == 'left' else 1].blocked
    return blocked

  def allow(self, carstate, direction, default):
    side, last = _side(direction), self._poll()
    intent = last.get('lanes.intent') or {}
    manual = self._driver_lamp(carstate, intent)
    if self._blocked(side, last, navigation=bool(intent.get('signalRequested')) and not manual):
      return False
    if manual:
      return bool(default and not getattr(carstate, side+'Blindspot', False))
    if intent.get('signalRequested'):
      if intent.get('signalPurpose') == 'nativeLaneChange':
        return bool(default and self.settings.lane_change_enabled and intent.get('valid')
                    and str(intent.get('direction')) == side
                    and not getattr(carstate, side+'Blindspot', False))
      return bool(default and intent.get('valid') and str(intent.get('direction')) == side and intent.get('targetLaneIndex', -1) >= 0
                  and intent.get('spLaneChangeReady') and intent.get('laneChangeAllowed'))
    return default

  def constraints(self, carstate, direction):
    last = self._poll()
    intent = last.get('lanes.intent') or {}
    side = str(intent.get('direction', 'none'))
    left, right = bool(getattr(carstate, 'leftBlinker', False)), bool(getattr(carstate, 'rightBlinker', False))
    if self._driver_lamp(carstate, intent):
      physical = 'left' if left else 'right'
      blocked = self._blocked(physical, last, navigation=False) or bool(getattr(carstate, physical+'Blindspot', False))
      return LaneChangeLimits(allow_start=not blocked, allow_continue=not blocked)
    if intent.get('valid') and intent.get('signalRequested') and side in ('left', 'right'):
      self._owned_side = side
      delegated = intent.get('signalPurpose') == 'nativeLaneChange'
      self._turn_only = intent.get('targetLaneIndex', -1) < 0 and not delegated
      self._suppress_turn = not self._turn_only or intent.get('signalPurpose') == 'lanePreparation'
      conflicting = right if side == 'left' else left
      if conflicting:
        return LaneChangeLimits(allow_start=False, allow_continue=False, suppress_turn=True)
      if delegated:
        clear = bool(self.settings.lane_change_enabled and not self._blocked(side, last)
                     and not getattr(carstate, side+'Blindspot', False))
        return LaneChangeLimits(allow_start=clear, allow_continue=clear, suppress_turn=True)
      if self._turn_only:
        return LaneChangeLimits(allow_start=False, allow_continue=False, turn_only=True,
                                suppress_turn=self._suppress_turn)
      ready = bool(intent.get('spLaneChangeReady') and intent.get('laneChangeAllowed'))
      clear = ready and not self._blocked(side, last)
      return LaneChangeLimits(allow_start=clear, allow_continue=clear, suppress_turn=True)
    if self._owned_side is not None:
      if left or right:
        return LaneChangeLimits(allow_start=False, allow_continue=False,
                                turn_only=self._turn_only, suppress_turn=self._suppress_turn)
      self._owned_side = None
    blocked = self._blocked(_side(direction), last, navigation=False)
    return LaneChangeLimits(allow_start=not blocked, allow_continue=not blocked)
