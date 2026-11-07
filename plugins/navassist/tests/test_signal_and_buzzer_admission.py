"""Failures: unknown numbering swallows a fresh directional lamp; a lamp alone
authorizes crossing; an unrelated/manual/stale/blocked start produces a chime.
No GPU, model training, vehicle messages or GPIO are used.
"""
from types import SimpleNamespace as N
import time
import pytest
from openpilot.cereal import log
from navassist.intent import build_intent, LaneIntentCoordinator, TurnSignalCoordinator
from navassist.settings import NavSettings
from navassist.chime import NavigationChime
from .test_unknown_lane_route_actions import inputs
from .test_migration_contract import Params, Messages


@pytest.mark.parametrize('maneuver', ['slight_left', 'slight_right'])
def test_unknown_numbering_does_not_swallow_directional_lamp(maneuver):
  nav, topo = inputs(maneuver)
  nav['distanceM'] = 35.
  out = build_intent(nav, topo, settings=NavSettings(), v_ego=8., now_ns=1_000_000_000,
    left_blocked=False, right_blocked=False, blindspot_left=False, blindspot_right=False,
    lateral_active=True, turns=TurnSignalCoordinator(), lanes=LaneIntentCoordinator())
  assert out['signalRequested'] and out['direction'] == maneuver.split('_')[1]
  assert not out['laneChangeAllowed'] and out['signalPurpose'] == 'nativeLaneChange'
  from navassist.policy import NavLanePolicy
  policy = NavLanePolicy(Params())
  policy._msgs = Messages({'lanes.intent': {'navassist': out}})
  car = N(leftBlinker=out['direction'] == 'left', rightBlinker=out['direction'] == 'right',
          leftBlindspot=False, rightBlindspot=False)
  limits = policy.constraints(car, 1 if car.leftBlinker else 2)
  assert limits.allow_start and limits.suppress_turn and not limits.turn_only
  direction = 1 if car.leftBlinker else 2
  assert policy.allow(car, direction, True)
  assert not policy.allow(car, direction, False)  # SP's own veto cannot be overridden.
  car.leftBlindspot = car.rightBlindspot = True
  policy._last_poll = -1
  assert not policy.constraints(car, direction).allow_start
  assert not policy.allow(car, direction, True)


@pytest.mark.parametrize('maneuver', ['merge_left', 'merge_right', 'exit_left', 'exit_right', 'ramp_left', 'ramp_right'])
@pytest.mark.parametrize('veto', ['none', 'bsm', 'paint', 'neighbor', 'gas'])
def test_explicit_route_action_needs_local_corridor_not_absolute_number(maneuver, veto):
  nav, topo = inputs(maneuver)
  nav['distanceM'] = 500.
  nav['lanes'] = [{'index': i, 'recommended': i == 1} for i in range(3)]
  side = maneuver.split('_')[1]
  if veto == 'paint': topo[side+'CrossingAllowed'] = False
  if veto == 'neighbor':
    topo[side+'NeighborExists'] = False
    topo[side+'RoadEdge'] = True
  turns, lanes = TurnSignalCoordinator(), LaneIntentCoordinator()
  for tick in range(60):
    out = build_intent(nav, topo, settings=NavSettings(), v_ego=15., now_ns=1_000_000_000+tick*50_000_000,
      left_blocked=False, right_blocked=False,
      blindspot_left=veto == 'bsm' and side == 'left', blindspot_right=veto == 'bsm' and side == 'right',
      lateral_active=True, left_blinker=side == 'left', right_blinker=side == 'right',
      gas_pressed=veto == 'gas', turns=turns, lanes=lanes)
  if veto in ('none', 'paint', 'gas'):
    assert out['signalRequested'] and out['laneChangeAllowed']
    assert out['targetLaneIndex'] == (0 if side == 'left' else 2)
  else:
    # BSM and a road-edge/absent neighbor remain hard vetoes.
    assert not out['laneChangeAllowed']


class State(dict):
  def __init__(self):
    super().__init__(modelV2=N(meta=N(laneChangeState=log.LaneChangeState.laneChangeStarting,
      laneChangeDirection=log.LaneChangeDirection.right)),
      carState=N(leftBlinker=False, rightBlinker=True, leftBlindspot=False, rightBlindspot=False), carControl=N(latActive=True))
    self.alive = self.valid = {key: True for key in self}
    self.logMonoTime = {key: time.monotonic_ns() for key in self}


def admitted():
  return dict(valid=True, signalRequested=True, direction='right', sessionId='s',
    routeRevision=1, maneuverEventId=3, requestId=3, targetLaneIndex=2,
    spLaneChangeReady=True, laneChangeAllowed=True)


@pytest.mark.parametrize('change', [dict(laneChangeAllowed=False), dict(spLaneChangeReady=False),
  dict(valid=False), dict(signalRequested=False), dict(direction='left')])
def test_unadmitted_or_opposite_change_is_silent(change):
  c = NavigationChime(Params()); c.settings = N(enabled=True, beep_enabled=True)
  c._msgs = Messages({'lanes.intent': {'navassist': dict(admitted(), **change)}})
  assert c.update(State()) == []


def test_stale_model_or_absent_physical_lamp_is_silent():
  for missing in ('lamp', 'model', 'lateral'):
    c = NavigationChime(Params()); c.settings = N(enabled=True, beep_enabled=True)
    c._msgs = Messages({'lanes.intent': {'navassist': admitted()}})
    sm = State()
    if missing == 'lamp': sm['carState'].rightBlinker = False
    if missing == 'model': sm.logMonoTime['modelV2'] -= 1_000_000_000
    if missing == 'lateral': sm['carControl'].latActive = False
    assert c.update(sm) == []


def test_navigation_execution_is_single_and_cannot_latch_into_manual_change():
  c = NavigationChime(Params()); c.settings = N(enabled=True, beep_enabled=True)
  c._msgs = Messages({'lanes.intent': {'navassist': admitted()}})
  assert len(c.update(State())) == 1
  assert c.update(State()) == []


def test_native_bsm_delegation_chimes_only_on_matching_actual_execution():
  c = NavigationChime(Params()); c.settings = N(enabled=True, beep_enabled=True)
  intent = dict(admitted(), signalPurpose='nativeLaneChange', targetLaneIndex=-1,
                spLaneChangeReady=False, laneChangeAllowed=False)
  c._msgs = Messages({'lanes.intent': {'navassist': intent}})
  sm = State(); sm['modelV2'].meta.laneChangeState = log.LaneChangeState.preLaneChange
  assert c.update(sm) == []
  sm['modelV2'].meta.laneChangeState = log.LaneChangeState.laneChangeStarting
  sm['carState'].rightBlindspot = True
  assert c.update(sm) == []
  sm['carState'].rightBlindspot = False
  assert len(c.update(sm)) == 1
  assert c.update(sm) == []
  c._msgs = Messages({})
  assert c.update(State()) == []


def test_plugin_owns_only_its_execution_prompt_and_releases_policy_when_disabled():
  from navassist.chime import NavigationBuzzerPolicy
  p = Params(); policy = NavigationBuzzerPolicy(p)
  assert policy.allow_prompt('Navigation turn signal', 'xpilotPluginWarning/permanent')
  assert not policy.allow_prompt('Car Detected in Blindspot', 'laneChangeBlocked/warning')
  assert not policy.allow_prompt('Navigation turn signal', 'laneChangeBlocked/warning')
  class Off(Params):
    def get_bool(self, *a, **kw): return False
  assert NavigationBuzzerPolicy(Off()).allow_prompt('anything', 'anything')
