"""Migration failure cases, recorded before the implementation.

Real cereal lane arrays/CAN messages must work; stale/future or impossible geometry
must not become a lane; blocked preparations keep the lamp but never readiness;
one source's plugin message must not inherit another source's controls.
"""
from types import SimpleNamespace as N
import math

import pytest

from navassist.settings import NavSettings
from navassist.topology import from_model


def model(ys=(-5.4, -1.8, 1.8, 5.4), *, road_right=5.8, frame=1):
  from openpilot.cereal import log
  m = log.ModelDataV2.new_message()
  m.frameId = frame
  m.laneLineProbs = [0.95] * 4
  m.laneLines = [{'x': [0.0, 10.0, 30.0], 'y': [y, y, y], 'z': [0.0] * 3} for y in ys]
  m.roadEdges = [{'x': [0.0, 10.0, 30.0], 'y': [-6.0] * 3},
                 {'x': [0.0, 10.0, 30.0], 'y': [road_right] * 3}]
  m.roadEdgeStds = [0.2, 0.2]
  m.meta.laneChangeState = 'off'
  m.meta.laneChangeDirection = 'none'
  return m


def test_real_cereal_parallel_lane_arrays_and_left_to_right_index():
  result = from_model(model(), 1_100_000_000, 1_000_000_000)
  assert result['valid']
  assert result['visibleLaneCount'] == 3
  assert result['egoLaneIndexFromLeft'] == 1
  assert result['leftNeighborExists'] and result['rightNeighborExists']
  leftmost = from_model(model((-1.8, 1.8, 5.4, 9.0), road_right=9.4), 2_000_000_000, 2_000_000_000)
  assert leftmost['valid'] and leftmost['egoLaneIndexFromLeft'] == 0
  assert not leftmost['leftNeighborExists'] and leftmost['rightNeighborExists']


@pytest.mark.parametrize('ys', [(-8., -6., -4., -2.), (-1., 1., 1.1, 1.2), (-5.4, -1.8, math.nan, 5.4)])
def test_unbracketed_or_impossible_geometry_is_unknown(ys):
  assert not from_model(model(ys), 1_100_000_000, 1_000_000_000)['valid']


@pytest.mark.parametrize('now', [500_000_000, 2_000_000_000])
def test_future_and_stale_model_cannot_authorize_topology(now):
  assert not from_model(model(), now, 1_000_000_000)['valid']


def test_real_can_event_is_converted_once_without_submaster_list_confusion():
  from openpilot.cereal import messaging
  from navassist.can_input import can_batches
  event = messaging.new_message('can', 1)
  event.logMonoTime = 123
  event.can[0].address, event.can[0].src, event.can[0].dat = 0x39B, 1, b'\0' * 8
  assert can_batches([event]) == [(123, [(0x39B, b'\0' * 8, 1)])]


def test_absolute_lane_needs_physical_anchor_and_distinct_model_frames():
  from navassist.position import AbsolutePosition
  gate = AbsolutePosition()
  nav = {'valid': True, 'sessionId': 's', 'routeRevision': 1, 'laneTotalCount': 4}
  topo = from_model(model(), 1_000_000_000, 1_000_000_000)
  for _ in range(10):
    result = gate.update(topo, nav, 1_000_000_000)
  assert not result['valid']
  for tick in range(1, 4):
    now = 1_000_000_000 + tick * 50_000_000
    topo = from_model(model(frame=tick+1), now, now)
    result = gate.update(topo, nav, now)
  assert result['valid'] and result['lane_index'] == 3 and result['lane_count'] == 4
  now += 50_000_000
  bad = from_model(model(road_right=12., frame=9), now, now)
  assert not gate.update(bad, nav, now)['valid']
  assert not gate.update(topo, dict(nav, sessionId='new'), now)['valid']


def test_preparation_keeps_lamp_while_boundary_or_blindspot_vetoes_readiness():
  from navassist.intent import LaneIntentCoordinator, TurnSignalCoordinator, build_intent
  nav = {'valid': True, 'stale': False, 'routeActive': True, 'routeMatched': True, 'mode': 'realtime',
         'sessionId': 's', 'routeRevision': 1, 'maneuverEventId': 7, 'maneuver': 'turn_right',
         'distanceM': 300., 'laneTotalCount': 4,
         'lanes': [{'index': i, 'recommended': i == 3} for i in range(4)]}
  topology = {'valid': True, 'visibleLaneCount': 3, 'egoLaneIndexFromLeft': 1,
              'leftNeighborExists': True, 'rightNeighborExists': True}
  settings = NavSettings(lane_change_enabled=True, turn_signal_enabled=True)
  lanes, turns = LaneIntentCoordinator(), TurnSignalCoordinator()
  for tick in range(30):
    out = build_intent(nav, topology, settings=settings, v_ego=15., now_ns=1_000_000_000+tick*50_000_000,
                       left_blocked=False, right_blocked=True, blindspot_left=False, blindspot_right=True,
                       lateral_active=True, right_blinker=tick > 0, turns=turns, lanes=lanes)
  assert out['signalRequested'] and out['direction'] == 'right'
  assert not out['spLaneChangeReady'] and not out['laneChangeAllowed']


class Params:
  def get_bool(self, key, **kw):
    return key in ('ExtNavAssistEnabled', 'ExtNavAssistLaneChange', 'ExtNavAssistTurnSignal', 'ExtNavAssistTurnSlowdown')

  def get(self, key, **kw):
    return None


class Messages:
  def __init__(self, sources):
    self.sources = sources

  def fresh(self, kind):
    return self.sources.get(kind, {})


def test_policy_ignores_another_publishers_intent_and_rejects_turn_only_as_change():
  from navassist.policy import NavLanePolicy
  policy = NavLanePolicy(Params())
  policy._msgs = Messages({'lanes.intent': {'other': {'signalRequested': True, 'direction': 'left',
    'targetLaneIndex': 0, 'spLaneChangeReady': True, 'laneChangeAllowed': True}}})
  assert not policy.allow(None, 1, False)
  policy._last_poll = -1
  policy._msgs = Messages({'lanes.intent': {'navassist': {'signalRequested': True, 'direction': 'left',
    'targetLaneIndex': -1, 'spLaneChangeReady': False}}})
  assert not policy.allow(None, 1, True)


def test_expired_overlay_message_clears_instead_of_latching_old_route():
  from navassist.display import read_state
  states = read_state(Messages({'nav.state': {'navassist': {'valid': True}}}))
  assert states['nav']['valid']
  assert read_state(Messages({}))['nav'] == {}


def test_policy_preparation_and_expired_owned_lamp_remain_start_vetoes():
  from navassist.policy import NavLanePolicy
  policy = NavLanePolicy(Params())
  car = N(leftBlinker=True, rightBlinker=False)
  policy._msgs = Messages({'lanes.intent': {'navassist': {'valid': True, 'signalRequested': True,
    'direction': 'left', 'targetLaneIndex': 0, 'spLaneChangeReady': False}}})
  assert not policy.constraints(car, 1).allow_start
  policy._msgs = Messages({})
  policy._last_poll = -1
  assert not policy.constraints(car, 1).allow_start
  policy._last_poll = -1
  car.leftBlinker = False
  assert policy.constraints(car, 1).allow_start


def test_oem_payload_respects_event_age_and_the_replay_clock():
  from navassist.oem import OemLaneSignals
  signal = OemLaneSignals()
  data = (21 << 46).to_bytes(8, 'little')
  signal.update([(1_000_000_000, [(0x39B, data, 1)])], 1_000_000_000)
  assert signal.payload(1_100_000_000)['rightExplicitBlock']
  assert not signal.payload(2_000_000_000)['rightExplicitBlock']
  signal.update([(1_000_000_000, [(0x39B, data, 1)])], 3_000_000_000)
  assert not signal.payload(3_000_000_000)['rightExplicitBlock']


def test_repeated_cached_oem_packet_is_not_two_independent_frames():
  from navassist.blocker import LaneChangeBlocker
  blocker = LaneChangeBlocker()
  packet = {'rightExplicitBlock': True, 'alcStampNs': 100, 'mapStampNs': -1}
  for _ in range(20):
    assert not blocker.update(packet, {'valid': True})[1]
  assert blocker.update(dict(packet, alcStampNs=200), {'valid': True})[1]


def test_complete_runtime_retains_preparation_on_reliable_oem_boundary_veto():
  import json
  from navassist.runtime import NavigationRuntime
  from navassist.store import NavAssistStore
  from navassist.tests.test_navassist import snapshot_body
  body = json.loads(snapshot_body())
  body['validForMs'] = 2000
  body['guidance']['maneuver'] = 'turn_right'
  body['guidance']['maneuverDistanceM'] = 300
  body['lanes']['totalCount'] = 4
  body['lanes']['items'] = [dict(index=i, allowedActions=['RIGHT'], recommendedActions=['RIGHT'],
                               recommended=i == 3) for i in range(4)]
  store = NavAssistStore(clock_ns=lambda: 1_000_000_000)
  current = store.accept(json.dumps(body).encode(), 'a'*32)
  runtime = NavigationRuntime(NavSettings())
  car = N(vEgo=15., leftBlinker=False, rightBlinker=True, leftBlindspot=False, rightBlindspot=False,
          brakePressed=False, gasPressed=False, steeringPressed=False)
  cc = N(latActive=True)
  for tick in range(30):
    now = 1_000_000_000+tick*50_000_000
    state = 7 if tick < 20 else 21
    batches = [(now, [(0x39B, (state << 46).to_bytes(8, 'little'), 1)])]
    result = runtime.tick(current, model(frame=tick+1), now, car, cc, now,
                          can_list=batches, vehicle_fresh=True)
  assert result['nav']['valid'] and result['position']['valid']
  assert result['intent']['signalRequested']
  assert not result['intent']['spLaneChangeReady']
  assert result['oem']['rightBlocked']


def test_missing_speed_control_context_cannot_request_a_maneuver_ceiling():
  from navassist.target import NavSpeedTarget
  target = NavSpeedTarget(Params())
  target._fresh = lambda: {'valid': True, 'stale': False, 'maneuver': 'turn_left', 'distanceM': 60.,
                           'sessionId': 's', 'routeRevision': 1, 'maneuverEventId': 3}
  assert target.update({}, 10., 15.) is None


def test_diagnostics_rotate_and_keep_payloads_out_of_the_public_tree(tmp_path):
  import gzip
  import json
  from navassist.recording import Recorder
  recorder = Recorder(tmp_path, max_seconds=1, max_files=3)
  for tick in range(6):
    recorder.write({'intent': {'reason': 'waitingCrossing'}}, wall_ms=1700000000000+tick*1100)
  recorder.close()
  files = list(tmp_path.glob('*.jsonl.gz'))
  assert 1 <= len(files) <= 3
  with gzip.open(files[-1], 'rt') as stream:
    assert json.loads(stream.readline())['intent']['reason'] == 'waitingCrossing'


def test_turn_sender_ignores_other_plugins_messages():
  from navassist.plugin import NavAssist
  plugin = NavAssist.__new__(NavAssist)
  plugin._msgs = Messages({'lanes.intent': {'other': {'valid': True, 'signalRequested': True}}})
  assert plugin._fresh_intent() == {}


def test_invalid_intent_never_grants_automatic_lane_change():
  from navassist.policy import NavLanePolicy
  policy = NavLanePolicy(Params())
  policy._msgs = Messages({'lanes.intent': {'navassist': {'valid': False, 'signalRequested': True,
    'direction': 'left', 'targetLaneIndex': 0, 'spLaneChangeReady': True, 'laneChangeAllowed': True}}})
  assert not policy.allow(None, 1, True)


def test_explicit_disable_clears_an_active_turn_without_plan_gap_grace():
  from navassist.runtime import NavigationRuntime
  from navassist.store import NavAssistStore
  from navassist.tests.test_navassist import snapshot_body
  import json
  body = json.loads(snapshot_body())
  body['guidance']['maneuver'] = 'turn_right'
  body['guidance']['maneuverDistanceM'] = 25
  store = NavAssistStore(clock_ns=lambda: 1_000_000_000)
  current = store.accept(json.dumps(body).encode(), 'a'*32)
  settings = NavSettings()
  runtime = NavigationRuntime(settings)
  car, cc = N(vEgo=10.), N(latActive=True)
  before = runtime.tick(current, model(), 1_000_000_000, car, cc, 1_000_000_000, vehicle_fresh=True)
  assert before['intent']['signalRequested']
  from dataclasses import replace
  runtime.settings = replace(settings, enabled=False)
  after = runtime.tick(current, model(), 1_050_000_000, car, cc, 1_050_000_000, vehicle_fresh=True)
  assert not after['intent']['signalRequested'] and not after['intent']['spLaneChangeReady']


def test_driver_opposite_lamp_is_never_overwritten_or_cancelled():
  from navassist.turnsignal import TurnSignalController
  from navassist.tests.test_navassist import _template
  controller = TurnSignalController()
  now = 1_000_000_000
  controller.observe([(now, [(0x3E9, _template(), 1)])], now)
  request = dict(valid=True, signalRequested=True, direction='left', sessionId='s', routeRevision=1, requestId=1)
  driver = N(leftBlinker=False, rightBlinker=True, brakePressed=False)
  cc = N(latActive=True)
  assert controller.update(request, driver, cc, now, enabled=True) == []
  driver.rightBlinker = False
  assert controller.update(request, driver, cc, now, enabled=True)
  driver.rightBlinker = True
  assert controller.update(request, driver, cc, now+200_000_000, enabled=True) == []
  assert controller.active is None


def test_phone_extra_veto_uses_plugin_switch_not_legacy_config(monkeypatch):
  from navassist.policy import NavLanePolicy
  monkeypatch.setattr('navassist.phone.load_mode', lambda: 'assist')
  assert not NavLanePolicy(Params())._phone.enabled


def test_disabled_plugin_cannot_begin_a_new_maneuver_speed_ceiling():
  from navassist.target import NavSpeedTarget
  class Disabled(Params):
    def get_bool(self, key, **kw):
      return key != 'ExtNavAssistEnabled'
  target = NavSpeedTarget(Disabled())
  target._fresh = lambda: {'valid': True, 'stale': False, 'maneuver': 'turn_right', 'distanceM': 50.,
                           'sessionId': 's', 'routeRevision': 1, 'maneuverEventId': 3}
  sm = {'carState': N(gasPressed=False, brakePressed=False),
        'carControl': N(enabled=True, cruiseControl=N(override=False))}
  assert target.update(sm, 10., 15.) is None


def test_plugin_discovery_refuses_a_host_without_lane_context_capability():
  import subprocess
  import sys
  code = "import sys; sys.modules['openpilot.tesla.lane_policy'] = None; import navassist.plugin"
  result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
  assert result.returncode != 0 and 'lane_policy' in result.stderr
