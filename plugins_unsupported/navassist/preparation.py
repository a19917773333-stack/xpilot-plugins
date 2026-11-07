from __future__ import annotations

from .intent_types import (LaneIntentDirection, ObservedLaneChangeState, NavLanePlan, LaneTopologyInput, LaneVehicleInput, NavTurnPlan, NavLaneIntent)
from .relative_lane_consistency import RelativeLaneConsistencyFilter


class LanePreparation:
  PLAN_RECOVERY_STABLE_NS = 3_000_000_000


  PLAN_RECOVERY_TIMEOUT_NS = 10_000_000_000


  PLAN_RECOVERY_MAX_RETRIES = 2


  MISMATCH_STABLE_NS = 500_000_000


  CROSSING_STABLE_NS = 300_000_000


  LANE_INDEX_STABLE_NS = 500_000_000


  TOPOLOGY_TRANSITION_GRACE_NS = 1_000_000_000


  OBSERVATION_RECOVERY_NS = 3_000_000_000


  SIGNAL_WAIT_TIMEOUT_NS = 60_000_000_000


  LANE_CHANGE_TIMEOUT_NS = 10_000_000_000


  COOLDOWN_NS = 750_000_000


  MIN_SPEED_MPS = 20 * 0.44704


  MAX_SPEED_MPS = 33.33


  def __init__(self, *, max_changes: int = 5) -> None:
    self._clear_plan_recovery()
    self._plan_recovery_count_key = None
    self._plan_recovery_count = 0
    self._phase = "idle"
    self._candidate = None
    self._candidate_since_ns = 0
    self._crossing_since_ns = 0
    self._phase_since_ns = 0
    self._signal_since_ns = 0
    self._blocked_key = None
    self._request_id = 0
    self._expected_lane_index = -1
    self._completion_since_ns = 0
    self._topology_invalid_since_ns = 0
    self._observation_since_ns: int | None = None
    self._observation_missing_since_ns: int | None = None
    self._observation_recovery_ns: int | None = None
    self._observation_lamp_released = False
    self._relative_consistency = RelativeLaneConsistencyFilter(max_changes=max_changes)


  def _idle(self, reason: str = "idle") -> NavLaneIntent:
    return NavLaneIntent(reason=reason)


  @staticmethod
  def _target(plan: NavLanePlan, ego_index: int) -> int | None:
    valid = tuple(index for index in plan.recommended_indices if 0 <= index < plan.lane_count)
    return min(valid, key=lambda index: (abs(index - ego_index), index)) if valid else None


  @staticmethod
  def _direction(ego_index: int, target_index: int) -> LaneIntentDirection:
    if target_index < ego_index:
      return LaneIntentDirection.left
    if target_index > ego_index:
      return LaneIntentDirection.right
    return LaneIntentDirection.none


  @staticmethod
  def _adjacent_target_index(ego_index: int, direction: LaneIntentDirection) -> int:
    return max(0, ego_index - 1) if direction == LaneIntentDirection.left else ego_index + 1


  @staticmethod
  def _event_key(plan: NavLanePlan) -> tuple[str, int, int]:
    # Visible lane indices recenter while crossing a boundary. They describe an
    # observation, not a new navigation event or a reason to cancel its lamp.
    return (plan.session_id, plan.route_revision, plan.maneuver_event_id)


  @staticmethod
  def _plan_reason(plan: NavLanePlan, reason: str) -> str:
    return f"heuristic{reason[0].upper()}{reason[1:]}" if plan.heuristic and reason else reason


  @staticmethod
  def _relative_direction(plan: NavLanePlan) -> LaneIntentDirection:
    if not plan.heuristic:
      return LaneIntentDirection.none
    if plan.edge_direction != LaneIntentDirection.none:
      return plan.edge_direction
    if plan.lane_count > 1 and plan.recommended_indices == (0,):
      return LaneIntentDirection.left
    if plan.lane_count > 1 and plan.recommended_indices == (plan.lane_count - 1,):
      return LaneIntentDirection.right
    return LaneIntentDirection.none


  def _reset(self) -> None:
    self._clear_plan_recovery()
    self._phase = "idle"
    self._candidate = None
    self._candidate_since_ns = 0
    self._crossing_since_ns = 0
    self._phase_since_ns = 0
    self._signal_since_ns = 0
    self._expected_lane_index = -1
    self._completion_since_ns = 0
    self._topology_invalid_since_ns = 0
    self._observation_since_ns = None
    self._observation_missing_since_ns = None
    self._observation_recovery_ns = None
    self._observation_lamp_released = False


  def _observe_before_start(self, now_ns: int, *, recovering: bool) -> NavLaneIntent | None:
    """Keep one request through a bounded gap, never its permission to start."""
    assert self._candidate is not None
    self._phase = "observing"
    self._crossing_since_ns = 0
    if self._observation_since_ns is None:
      self._observation_since_ns = now_ns
    if not recovering:
      self._observation_recovery_ns = None
      if self._observation_missing_since_ns is None:
        self._observation_missing_since_ns = now_ns
    elif self._observation_recovery_ns is None:
      self._observation_recovery_ns = now_ns
    if recovering:
      self._observation_missing_since_ns = None
    stable_ns = self.OBSERVATION_RECOVERY_NS if self._observation_lamp_released else self.MISMATCH_STABLE_NS
    if recovering and now_ns - self._observation_recovery_ns >= stable_ns:
      self._phase = "signaling"
      self._phase_since_ns = now_ns
      if self._observation_lamp_released:
        self._signal_since_ns = now_ns
      self._observation_since_ns = self._observation_recovery_ns = None
      self._observation_missing_since_ns = None
      self._observation_lamp_released = False
      return None
    # Recovery confirmation must not consume the missing-observation budget.
    # Readiness remains false until the complete stable recovery has elapsed.
    if (not self._observation_lamp_released and self._observation_missing_since_ns is not None
        and now_ns - self._observation_missing_since_ns > self.TOPOLOGY_TRANSITION_GRACE_NS):
      self._observation_lamp_released = True
      self._observation_recovery_ns = now_ns if recovering else None
    _event, _ego, direction, target, _relative = self._candidate
    return NavLaneIntent(
      signal_requested=not self._observation_lamp_released, direction=direction,
      request_id=self._request_id, target_lane_index=target,
      reason="neighborObservationPaused" if self._observation_lamp_released else "neighborObservationHold",
    )


  def _abort(self, event_key, reason: str) -> NavLaneIntent:
    self._blocked_key = event_key
    self._reset()
    return self._idle(reason)


  def _clear_plan_recovery(self) -> None:
    self._plan_recovery_key = None
    self._plan_recovery_direction = LaneIntentDirection.none
    self._plan_recovery_started_ns = 0
    self._plan_recovery_stable_ns = None
    self._plan_recovery_token = None


  def _recover_plan_observation(self, plan: NavLanePlan, topology: LaneTopologyInput,
                                vehicle: LaneVehicleInput, *, now_ns: int,
                                vehicle_healthy: bool, topology_healthy: bool,
                                allow_new_lane_change: bool) -> NavLaneIntent | None:
    event_key = self._event_key(plan)
    if self._plan_recovery_key is not None:
      saved_key = self._plan_recovery_key
      direction = self._plan_recovery_direction
      if event_key != saved_key:
        return self._abort(saved_key, "lanePositionRouteChanged")
      if not plan.valid and not plan.observation_interrupted:
        return self._abort(saved_key, "lanePositionNavigationUnavailable")
      if not vehicle_healthy or vehicle.steering_pressed or not allow_new_lane_change:
        return self._abort(saved_key, "lanePositionRecoveryCancelled")
      if vehicle.lane_change_state in (ObservedLaneChangeState.starting, ObservedLaneChangeState.finishing):
        return self._abort(saved_key, "lanePositionUnexpectedChange")
      conflicting_lamp = (vehicle.left_blinker and vehicle.right_blinker) or (
        vehicle.right_blinker if direction == LaneIntentDirection.left else vehicle.left_blinker
      )
      if conflicting_lamp:
        return self._abort(saved_key, "lanePositionDriverSignal")
      if now_ns - self._plan_recovery_started_ns > self.PLAN_RECOVERY_TIMEOUT_NS:
        return self._abort(saved_key, "lanePositionRecoveryTimeout")
      target = self._target(plan, topology.ego_lane_index) if plan.valid and topology_healthy else None
      new_direction = (self._relative_direction(plan) or self._direction(topology.ego_lane_index, target)) if target is not None else None
      if new_direction == LaneIntentDirection.none:
        self._reset()
        return self._idle("alreadyInRecommendedLane")
      if new_direction is not None and new_direction != direction:
        return self._abort(saved_key, "lanePositionChangedDirection")
      neighbor = topology.left_neighbor_exists if direction == LaneIntentDirection.left else topology.right_neighbor_exists
      crossing = topology.left_crossing_allowed if direction == LaneIntentDirection.left else topology.right_crossing_allowed
      blindspot = vehicle.left_blindspot if direction == LaneIntentDirection.left else vehicle.right_blindspot
      safe = bool(plan.valid and topology_healthy and target is not None and neighbor is True
                  and crossing and not blindspot and not vehicle.left_blinker and not vehicle.right_blinker)
      token = (plan.lane_count, plan.recommended_indices, topology.ego_lane_index, target, direction) if safe else None
      if not safe:
        self._plan_recovery_stable_ns = self._plan_recovery_token = None
        return self._idle("lanePositionRecoveryWaiting")
      if token != self._plan_recovery_token:
        self._plan_recovery_token = token
        self._plan_recovery_stable_ns = now_ns
      if self._plan_recovery_stable_ns is None or now_ns - self._plan_recovery_stable_ns < self.PLAN_RECOVERY_STABLE_NS:
        return self._idle("lanePositionRecoveryStabilizing")
      # A new request must pass the original alignment, lamp feedback and
      # crossing timers. Never restore old readiness or an old request id.
      self._reset()
      return self._idle("lanePositionRecovered")

    recoverable = bool(
      not plan.valid and plan.observation_interrupted and vehicle_healthy
      and allow_new_lane_change and not vehicle.steering_pressed
      and vehicle.lane_change_state in (ObservedLaneChangeState.off, ObservedLaneChangeState.pre)
      and self._phase in ("signaling", "ready", "observing") and self._candidate is not None
      and self._candidate[0] == event_key
    )
    if not recoverable:
      return None
    if self._plan_recovery_count >= self.PLAN_RECOVERY_MAX_RETRIES:
      return self._abort(event_key, "lanePositionRetryLimit")
    direction = self._candidate[2]
    conflicting_lamp = (vehicle.left_blinker and vehicle.right_blinker) or (
      vehicle.right_blinker if direction == LaneIntentDirection.left else vehicle.left_blinker
    )
    if conflicting_lamp:
      return self._abort(event_key, "lanePositionDriverSignal")
    if now_ns - self._signal_since_ns > self.SIGNAL_WAIT_TIMEOUT_NS:
      return self._abort(event_key, "crossingWaitTimeout")
    # A fresh route with briefly unavailable map-to-visual lane position has
    # the same bounded preparation grace as an unknown neighboring lane.
    # Keep the physical request, discard readiness, and re-confirm on return.
    held = self._observe_before_start(now_ns, recovering=False)
    if held.signal_requested:
      return held
    self._reset()
    self._plan_recovery_key = event_key
    self._plan_recovery_direction = direction
    self._plan_recovery_started_ns = now_ns
    self._plan_recovery_count += 1
    return self._idle("lanePositionUnavailable")


