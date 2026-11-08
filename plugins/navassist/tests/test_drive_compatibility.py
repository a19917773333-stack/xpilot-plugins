"""Failure cases: bursty diagnostics exhaust the shared source budget;
phone-only navigation veto leaks into manual lamps; raw OEM veto is masked
by an unconfirmed aggregate.
Native SP denial, explicit OEM veto and navigation phone veto must survive.
"""
from collections import deque
from types import SimpleNamespace as N

from navassist.policy import NavLanePolicy
from .test_migration_contract import Params, Messages


def policy_with(oem, intent=None):
  p = NavLanePolicy(Params())
  p._msgs = Messages({'oem.lanes': {'navassist': oem},
    'lanes.topology': {'navassist': {'valid': True}},
    'lanes.intent': {'navassist': intent or {}}})
  p._phone_t = float('inf')
  p._phone.mode = 'assist'
  p._phone_states = (N(blocked=True), N(blocked=False))
  return p


def test_recorded_manual_left_lamp_is_not_owned_by_phone_navigation_veto():
  p = policy_with({'leftBlocked': True, 'leftExplicitBlock': False,
    'leftAvailabilityBlock': False, 'blockReasons': ['phoneBlindspot', '']})
  car = N(leftBlinker=True, rightBlinker=False, leftBlindspot=False)
  assert p.allow(car, 1, True)
  assert not p.allow(car, 1, False)  # Never manufacture native SP permission.
  limits = p.constraints(car, 1)
  assert limits.allow_start and limits.allow_continue


def test_explicit_oem_veto_survives_false_aggregate_and_phone_reason():
  p = policy_with({'leftBlocked': False, 'leftExplicitBlock': True,
                   'blockReasons': ['phoneBlindspot', '']})
  car = N(leftBlinker=True, rightBlinker=False)
  assert not p.allow(car, 1, True)
  assert not p.constraints(car, 1).allow_start


def test_phone_veto_still_blocks_navigation_requested_change():
  p = policy_with({'leftBlocked': True, 'blockReasons': ['phoneBlindspot', '']},
    {'valid': True, 'signalRequested': True, 'direction': 'left',
     'signalPurpose': 'nativeLaneChange'})
  car = N(leftBlinker=True, rightBlinker=False, leftBlindspot=False)
  assert not p.allow(car, 1, True)
  assert not p.constraints(car, 1).allow_start


def test_later_navigation_request_cannot_take_over_an_already_manual_lamp():
  p = policy_with({'leftBlocked': True, 'blockReasons': ['phoneBlindspot', '']})
  car = N(leftBlinker=True, rightBlinker=False, leftBlindspot=False)
  assert p.constraints(car, 1).allow_start
  p._last_poll = -1
  p._msgs.sources['lanes.intent']['navassist'] = dict(valid=True,
    signalRequested=True, direction='left', signalPurpose='nativeLaneChange')
  assert p.constraints(car, 1).allow_start
  assert p.allow(car, 1, True)
  # The manual ownership ends with the physical lamp, not an arbitrary timer.
  car.leftBlinker = False
  assert not p.constraints(car, 1).allow_start


def test_cycle_publisher_bounds_bursts_and_keeps_control_ttl():
  from navassist.publication import CyclePublisher
  sent = []
  p = CyclePublisher(lambda kind, payload, ttl: sent.append((now, kind, ttl)))
  result = {key: {} for key in ('nav', 'topology', 'intent', 'oem')}
  # Fast catch-up loops, a stall, then fast catch-up: never replay missed slots.
  times = list(range(0, 1_500_000_000, 1_000_000)) + list(range(1_900_000_000, 4_000_000_000, 1_000_000))
  for now in times:
    p.publish(result, now)
  window = deque()
  for stamp, kind, ttl in sent:
    window.append(stamp)
    while stamp-window[0] >= 1_000_000_000:
      window.popleft()
    assert len(window) <= 55  # + map2, lamp5, route1 leaves >=37 messages spare.
    assert ttl == {'nav.state': 1000, 'lanes.topology': 150,
                   'lanes.intent': 200, 'oem.lanes': 500}[kind]
  for kind, maximum_gap in [('lanes.topology', 50_000_000), ('lanes.intent', 50_000_000)]:
    stamps = [s for s, k, _ in sent if k == kind and s < 1_500_000_000]
    assert all(b-a == maximum_gap for a, b in zip(stamps, stamps[1:]))


def test_lamp_diagnostics_are_not_a_continuous_five_hz_stream(monkeypatch):
  from navassist.plugin import NavAssist
  from openpilot.tesla import plugins
  sent = []
  monkeypatch.setattr(plugins, 'send_msg', lambda *args: sent.append(args))
  p = NavAssist.__new__(NavAssist)
  p.settings = N(enabled=True, turn_signal_enabled=True)
  p._next_lamp = 0
  p._fresh_intent = lambda: {}
  p.turns = N(update=lambda *a, **kw: [], diagnostics=lambda *a, **kw: {})
  for now in range(0, 3_000_000_000, 10_000_000):
    p.control_sends(N(), N(), now)
  assert len(sent) == 3
