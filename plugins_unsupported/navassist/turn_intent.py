from __future__ import annotations

from .intent_types import (LaneIntentDirection, ObservedLaneChangeState, NavLanePlan, LaneTopologyInput, LaneVehicleInput, NavTurnPlan, NavLaneIntent)


TURN_HOLD_SPEED_MPS = 8.0


class NavTurnSignalCoordinator:
  """Requests a physical lamp for a route turn without authorizing a lane change."""

  SIGNAL_TIMEOUT_NS = 60_000_000_000
  PLAN_GAP_GRACE_NS = 1_500_000_000
  LOOKAHEAD_TIME_S = 8.0
  # Forks, exits and merges should warn as soon as they are announced, but only from a sane distance.
  IMMEDIATE_ARM_MANEUVERS = frozenset((
    "slightLeft", "slightRight", "keepLeft", "keepRight",
    "exitLeft", "exitRight", "rampLeft", "rampRight", "mergeLeft", "mergeRight",
  ))
  IMMEDIATE_ARM_MAX_M = {
    "slightLeft": 600.0, "slightRight": 600.0, "keepLeft": 600.0, "keepRight": 600.0,
    "exitLeft": 800.0, "exitRight": 800.0, "rampLeft": 800.0, "rampRight": 800.0,
    "mergeLeft": 800.0, "mergeRight": 800.0,
  }
  MIN_LOOKAHEAD_M = 40.0
  MAX_LOOKAHEAD_M = 250.0
  LOOKAHEAD_MARGIN_M = 20.0
  TURN_CLEAR_STABLE_NS = 500_000_000
  MANEUVER_DIRECTIONS = {
    "slightLeft": LaneIntentDirection.left,
    "turnLeft": LaneIntentDirection.left,
    "sharpLeft": LaneIntentDirection.left,
    "uTurnLeft": LaneIntentDirection.left,
    "exitLeft": LaneIntentDirection.left,
    "rampLeft": LaneIntentDirection.left,
    "mergeLeft": LaneIntentDirection.left,
    "slightRight": LaneIntentDirection.right,
    "turnRight": LaneIntentDirection.right,
    "sharpRight": LaneIntentDirection.right,
    "uTurnRight": LaneIntentDirection.right,
    "exitRight": LaneIntentDirection.right,
    "rampRight": LaneIntentDirection.right,
    "mergeRight": LaneIntentDirection.right,
  }

  def __init__(self) -> None:
    self._active_key: tuple[str, int, int] | None = None
    self._active_direction = LaneIntentDirection.none
    self._active_since_ns = 0
    self._plan_gap_since_ns: int | None = None
    self._completion_hold = False
    self._turn_clear_since_ns = 0

  def _reset(self, reason: str = "idle") -> NavLaneIntent:
    self._active_key = None
    self._active_direction = LaneIntentDirection.none
    self._active_since_ns = 0
    self._plan_gap_since_ns = None
    self._completion_hold = False
    self._turn_clear_since_ns = 0
    return NavLaneIntent(reason=reason)

  def update(self, plan: NavTurnPlan, *, speed_mps: float, now_ns: int,
             turn_geometry_active: bool = False, lookahead_time_s: float | None = None,
             lookahead_distance_m: float | None = None) -> NavLaneIntent:
    direction = self.MANEUVER_DIRECTIONS.get(plan.maneuver, LaneIntentDirection.none)
    event_key = (plan.session_id, plan.route_revision, plan.maneuver_event_id)

    if self._active_key is not None:
      if now_ns - self._active_since_ns > self.SIGNAL_TIMEOUT_NS:
        return self._reset("turnSignalTimeout")
      if event_key != self._active_key or direction != self._active_direction:
        route_continuous = (plan.session_id, plan.route_revision) == self._active_key[:2]
        if not route_continuous:
          return self._reset("turnChanged")
        # 模型不一定给出 turnGeometryActive；低车速（正在转弯）同样按完成态处理，
        # 否则每换一个导航 step 就会把灯掐灭再点亮。
        if turn_geometry_active or speed_mps <= TURN_HOLD_SPEED_MPS:
          self._completion_hold = True
          self._turn_clear_since_ns = 0
        elif self._completion_hold:
          if self._turn_clear_since_ns == 0:
            self._turn_clear_since_ns = now_ns
          elif now_ns - self._turn_clear_since_ns > self.TURN_CLEAR_STABLE_NS:
            return self._reset("turnChanged")
        else:
          return self._reset("turnChanged")
        return NavLaneIntent(
          signal_requested=True,
          direction=self._active_direction,
          # The next guidance event does not own the still-active turn lamp.
          request_id=self._active_key[2],
          target_lane_index=-1,
          reason="turnCompletion",
        )
      self._completion_hold = False
      self._turn_clear_since_ns = 0
      if not plan.valid:
        if self._plan_gap_since_ns is None:
          self._plan_gap_since_ns = now_ns
        if now_ns - self._plan_gap_since_ns <= self.PLAN_GAP_GRACE_NS:
          return NavLaneIntent(
            signal_requested=True,
            direction=self._active_direction,
            request_id=plan.maneuver_event_id,
            target_lane_index=-1,
            reason="turnApproachGrace",
          )
        return self._reset("turnUnavailable")
      else:
        self._plan_gap_since_ns = None
        return NavLaneIntent(
          signal_requested=True,
          direction=self._active_direction,
          request_id=plan.maneuver_event_id,
          target_lane_index=-1,
          reason="turnApproach",
        )

    if not plan.valid or direction == LaneIntentDirection.none or plan.maneuver_event_id == 0:
      return self._reset("turnUnavailable")

    lookahead_m = max(self.MIN_LOOKAHEAD_M, min(
      self.MAX_LOOKAHEAD_M, max(0.0, speed_mps) * (self.LOOKAHEAD_TIME_S if lookahead_time_s is None else lookahead_time_s) + self.LOOKAHEAD_MARGIN_M,
    ))
    if lookahead_distance_m:
      # Turn-lane lookahead (UI setting) extends the lamp window so an announced turn arms the lamp
      # hundreds of metres out; 300 m keeps it from blinking through an entire road.
      lookahead_m = min(300.0, max(lookahead_m, float(lookahead_distance_m)))
    if plan.maneuver in self.IMMEDIATE_ARM_MANEUVERS and plan.distance_m <= self.IMMEDIATE_ARM_MAX_M.get(plan.maneuver, 600.0):
      lookahead_m = max(lookahead_m, plan.distance_m)
    if not 0.0 < plan.distance_m <= lookahead_m:
      return self._reset("turnOutsideWindow")

    self._active_key = event_key
    self._active_direction = direction
    self._active_since_ns = now_ns
    self._plan_gap_since_ns = None
    return NavLaneIntent(
      signal_requested=True,
      direction=direction,
      request_id=plan.maneuver_event_id,
      target_lane_index=-1,
      reason="turnApproach",
    )

