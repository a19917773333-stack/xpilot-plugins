from dataclasses import replace

import pytest

from navassist.coordinator import (
  LaneIntentDirection, LaneTopologyInput, LaneVehicleInput, NavLaneIntentCoordinator, NavLanePlan,
  ObservedLaneChangeState,
)


def preparation(direction=LaneIntentDirection.right, *, relative=False):
  coordinator = NavLaneIntentCoordinator()
  target = 0 if direction == LaneIntentDirection.left else 2
  plan = NavLanePlan(True, 'route', 1, 7, 3, (target,), heuristic=relative,
                     edge_direction=direction if relative else LaneIntentDirection.none)
  topology = LaneTopologyInput(True, 3, 1, True, True, True, True)
  car = LaneVehicleInput(True, 15, left_blinker=direction == LaneIntentDirection.left,
                         right_blinker=direction == LaneIntentDirection.right)
  for tick in range(30):
    result = coordinator.update(plan, topology, car, now_ns=1_000_000_000 + tick * 50_000_000)
  assert result.signal_requested and result.lane_change_ready
  return coordinator, plan, topology, car, result.request_id


@pytest.mark.parametrize('direction', [LaneIntentDirection.left, LaneIntentDirection.right])
@pytest.mark.parametrize('relative', [False, True])
def test_source_transition_keeps_lamp_and_request_but_reconfirms_readiness(direction, relative):
  coordinator, plan, topology, car, request_id = preparation(direction, relative=relative)
  changed = replace(plan, heuristic=not relative,
                    edge_direction=direction if not relative else LaneIntentDirection.none)
  first = coordinator.update(changed, topology, car, now_ns=2_500_000_000)
  assert first.signal_requested and first.request_id == request_id
  assert not first.lane_change_ready
  for tick in range(1, 21):
    result = coordinator.update(changed, topology, car, now_ns=2_500_000_000 + tick * 50_000_000)
    assert result.signal_requested and result.request_id == request_id
    if not relative and tick < 10:
      assert not result.lane_change_ready
  assert result.lane_change_ready


def test_repeated_source_switches_do_not_restart_the_physical_request():
  coordinator, plan, topology, car, request_id = preparation()
  for tick in range(200):
    relative = bool(tick % 2)
    changed = replace(plan, heuristic=relative,
                      edge_direction=LaneIntentDirection.right if relative else LaneIntentDirection.none)
    result = coordinator.update(changed, topology, car, now_ns=2_500_000_000 + tick * 50_000_000)
    assert result.signal_requested and result.request_id == request_id
    if tick:
      assert not result.lane_change_ready  # An unstable source never inherits old readiness.


@pytest.mark.parametrize('obstruction', ['blindspot', 'solid', 'lamp_missing'])
def test_source_transition_does_not_bypass_crossing_feedback_or_blindspot(obstruction):
  coordinator, plan, topology, car, request_id = preparation()
  changed = replace(plan, heuristic=True, edge_direction=LaneIntentDirection.right)
  topology = replace(topology, right_crossing_allowed=obstruction != 'solid')
  car = replace(car, right_blindspot=obstruction == 'blindspot', right_blinker=obstruction != 'lamp_missing')
  for tick in range(30):
    result = coordinator.update(changed, topology, car, now_ns=2_500_000_000 + tick * 50_000_000)
    assert result.signal_requested and result.request_id == request_id
    assert not result.lane_change_ready


@pytest.mark.parametrize('change', ['event', 'revision', 'session', 'direction', 'target', 'edge', 'brake', 'lateral'])
def test_actual_target_or_safety_change_does_not_inherit_preparation(change):
  coordinator, plan, topology, car, request_id = preparation()
  if change == 'event':
    plan = replace(plan, maneuver_event_id=8)
  elif change == 'revision':
    plan = replace(plan, route_revision=2)
  elif change == 'session':
    plan = replace(plan, session_id='other')
  elif change == 'direction':
    plan = replace(plan, recommended_indices=(0,))
  elif change == 'target':
    plan = replace(plan, lane_count=4, recommended_indices=(3,))
    topology = replace(topology, visible_lane_count=4)
  elif change == 'edge':
    topology = replace(topology, right_neighbor_exists=False)
  elif change == 'brake':
    car = replace(car, brake_pressed=True)
  else:
    car = replace(car, lateral_active=False)
  result = coordinator.update(plan, topology, car, now_ns=2_500_000_000)
  assert not result.signal_requested and not result.lane_change_ready


def test_recovery_confirmation_does_not_cancel_a_short_missing_observation():
  coordinator, plan, topology, car, request_id = preparation()
  unknown = replace(topology, right_neighbor_exists=None)
  coordinator.update(plan, unknown, car, now_ns=2_500_000_000)
  recovering = coordinator.update(plan, topology, car, now_ns=3_200_000_000)
  assert recovering.signal_requested and not recovering.lane_change_ready
  # Total episode is > 1 second, but the missing interval was only 0.7 s.
  waiting = coordinator.update(plan, topology, car, now_ns=3_550_000_000)
  assert waiting.signal_requested and not waiting.lane_change_ready
  resumed = coordinator.update(plan, topology, car, now_ns=3_750_000_000)
  assert resumed.signal_requested and resumed.request_id == request_id
  assert not resumed.lane_change_ready
  assert coordinator.update(plan, topology, car, now_ns=4_100_000_000).lane_change_ready


@pytest.mark.parametrize('invalid_topology', [False, True])
def test_continuous_missing_observation_still_releases_after_original_grace(invalid_topology):
  coordinator, plan, topology, car, request_id = preparation()
  missing = replace(topology, valid_for_control=not invalid_topology, right_neighbor_exists=None)
  assert coordinator.update(plan, missing, car, now_ns=2_500_000_000).signal_requested
  result = coordinator.update(plan, missing, car, now_ns=3_500_000_001)
  assert not result.signal_requested and not result.lane_change_ready
  assert result.request_id == request_id


@pytest.mark.parametrize('waiting', ['observation', 'source'])
def test_intermittent_observation_and_source_waits_cannot_extend_signal_timeout(waiting):
  coordinator, plan, topology, car, _ = preparation()
  for tick in range(1, 1300):
    now = 2_450_000_000 + tick * 50_000_000
    if waiting == 'observation':
      current_topology = replace(topology, right_neighbor_exists=None if tick % 2 else True)
      current_plan = plan
    else:
      current_topology = topology
      current_plan = replace(plan, heuristic=bool(tick % 2), edge_direction=LaneIntentDirection.right)
    result = coordinator.update(current_plan, current_topology, car, now_ns=now)
    if not result.signal_requested:
      assert result.reason == 'crossingWaitTimeout'
      break
  else:
    pytest.fail('Preparation held beyond its original overall timeout')


def test_started_absolute_change_keeps_original_completion_rules_on_source_switch():
  coordinator, plan, topology, car, request_id = preparation()
  changing = replace(car, lane_change_state=ObservedLaneChangeState.starting,
                     lane_change_direction=LaneIntentDirection.right)
  coordinator.update(plan, topology, changing, now_ns=2_500_000_000)
  changed = replace(plan, heuristic=True, edge_direction=LaneIntentDirection.right)
  result = coordinator.update(changed, topology, changing, now_ns=2_550_000_000)
  assert result.signal_requested and result.request_id == request_id
  assert coordinator._candidate[4] is False
