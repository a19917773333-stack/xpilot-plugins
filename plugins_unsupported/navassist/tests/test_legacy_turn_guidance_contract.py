"""23-Oct parity: unchanged guidance must not suppress turn-only lamps while
new matched realtime snapshots arrive. Expired snapshots, future guidance,
missing guidance and inactive routes still deny a new lamp; lane validity is
not restored by this compatibility path.
"""
import json
from .test_navassist import snapshot_body
from navassist.store import NavAssistStore
from navassist.navstate import build
from navassist.intent import TurnSignalCoordinator


def test_fresh_stream_with_unchanged_guidance_keeps_turn_signal_only():
  body = json.loads(snapshot_body())
  body['guidance']['observedAtMs'] = body['sourceWallTimeMs'] - 5000
  store = NavAssistStore(clock_ns=lambda: 1_000_000_000, wall_clock_ms=lambda: body['sourceWallTimeMs'])
  accepted = store.accept(json.dumps(body).encode(), 'a'*32)
  nav = build(accepted, 1_000_000_000)
  assert nav['linked']
  assert not nav['valid']
  turn = TurnSignalCoordinator().update(nav, speed_mps=15., now_ns=1_000_000_000)
  assert turn['signalRequested'] and turn['targetLaneIndex'] == -1
  expired = build(accepted, 2_000_000_000)
  assert not expired['linked']
  assert not TurnSignalCoordinator().update(expired, speed_mps=15., now_ns=2_000_000_000)['signalRequested']


def test_unchanged_guidance_does_not_revive_inactive_unmatched_or_future_input():
  from dataclasses import replace
  body = json.loads(snapshot_body())
  store = NavAssistStore(clock_ns=lambda: 1_000_000_000, wall_clock_ms=lambda: body['sourceWallTimeMs'])
  accepted = store.accept(json.dumps(body).encode(), 'a'*32)
  for overrides in ({'route_active': False}, {'route_matched': False}, {'guidance_present': False},
                    {'guidance_observed_at_ms': body['sourceWallTimeMs'] + 1},
                    {'navigation_mode': 'simulation'}):
    nav = build(replace(accepted, snapshot=replace(accepted.snapshot, **overrides)), 1_000_000_000)
    assert not nav['linked']
