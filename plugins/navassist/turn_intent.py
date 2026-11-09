from __future__ import annotations

import math

from .intent_types import LaneIntentDirection, NavLaneIntent, NavTurnPlan


TURN_HOLD_SPEED_MPS = 8.0
TURN_LOOKAHEAD_MAX_M = 120.0
TURN_LAMP_STALL_NS = 10_000_000_000
TURN_PROGRESS_MIN_M = 0.5
TURN_ARRIVAL_DISTANCE_M = 5.0


class NavTurnSignalCoordinator:
  """Requests a physical lamp for a route turn without authorizing a lane change."""

  SIGNAL_TIMEOUT_NS = 60_000_000_000
  PLAN_GAP_GRACE_NS = 1_500_000_000
  LOOKAHEAD_TIME_S = 8.0
  TURN_MANEUVERS = frozenset((
    "turnLeft", "turnRight", "sharpLeft", "sharpRight", "uTurnLeft", "uTurnRight",
  ))
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
  RESTART_PULSE_NS = 2_000_000_000
  RESTART_PULSE_DISTANCE_M = 25.0
  RESTART_STOP_SPEED_MPS = 0.3
  RESTART_GO_SPEED_MPS = 1.5
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
    self._active_since_ns: int | None = None
    self._plan_gap_since_ns: int | None = None
    self._last_progress_distance_m: float | None = None
    self._last_progress_ns: int | None = None
    self._completion_hold = False
    self._turn_clear_since_ns: int | None = None
    self._stopped_since_ns: int | None = None
    self._pulse_until_ns = 0

  def _reset(self, reason: str = "idle") -> NavLaneIntent:
    self._active_key = None
    self._active_direction = LaneIntentDirection.none
    self._active_since_ns = None
    self._plan_gap_since_ns = None
    self._last_progress_distance_m = None
    self._last_progress_ns = None
    self._completion_hold = False
    self._turn_clear_since_ns = None
    return NavLaneIntent(reason=reason)

  def _restart_pulse(self, plan: NavTurnPlan, direction: LaneIntentDirection, speed_mps: float,
                     now_ns: int) -> NavLaneIntent | None:
    if speed_mps <= self.RESTART_STOP_SPEED_MPS:
      if self._stopped_since_ns is None:
        self._stopped_since_ns = now_ns
    else:
      if (self._stopped_since_ns is not None and speed_mps >= self.RESTART_GO_SPEED_MPS
          and now_ns - self._stopped_since_ns >= 500_000_000
          and direction is not LaneIntentDirection.none
          and 0.0 <= plan.distance_m <= self.RESTART_PULSE_DISTANCE_M):
        self._pulse_until_ns = now_ns + self.RESTART_PULSE_NS
      self._stopped_since_ns = None
    if (self._pulse_until_ns and now_ns < self._pulse_until_ns
        and direction is not LaneIntentDirection.none):
      self._active_key = (plan.session_id, plan.route_revision, plan.maneuver_event_id)
      self._active_direction = direction
      self._active_since_ns = now_ns
      self._last_progress_distance_m = plan.distance_m
      self._last_progress_ns = now_ns
      return NavLaneIntent(
        signal_requested=True, direction=direction, request_id=plan.maneuver_event_id,
        target_lane_index=-1, reason="turnRestartPulse",
      )
    return None

  def _track_progress(self, plan: NavTurnPlan, now_ns: int) -> None:
    distance = float(plan.distance_m)
    if not math.isfinite(distance):
      return
    if (self._last_progress_distance_m is None or self._last_progress_ns is None
        or distance <= self._last_progress_distance_m - TURN_PROGRESS_MIN_M):
      self._last_progress_distance_m = distance
      self._last_progress_ns = now_ns

  def _lookahead(self, plan: NavTurnPlan, speed_mps: float,
                 lookahead_time_s: float | None, lookahead_distance_m: float | None) -> float:
    seconds = self.LOOKAHEAD_TIME_S if lookahead_time_s is None else lookahead_time_s
    lookahead_m = max(self.MIN_LOOKAHEAD_M, min(
      self.MAX_LOOKAHEAD_M, max(0.0, speed_mps) * seconds + self.LOOKAHEAD_MARGIN_M,
    ))
    if lookahead_distance_m:
      lookahead_m = min(300.0, max(lookahead_m, float(lookahead_distance_m)))
    if plan.maneuver in self.TURN_MANEUVERS:
      lookahead_m = min(lookahead_m, TURN_LOOKAHEAD_MAX_M)
    if (plan.maneuver in self.IMMEDIATE_ARM_MANEUVERS
        and plan.distance_m <= self.IMMEDIATE_ARM_MAX_M.get(plan.maneuver, 600.0)):
      lookahead_m = max(lookahead_m, plan.distance_m)
    return lookahead_m

  def update(self, plan: NavTurnPlan, *, speed_mps: float, now_ns: int,
             turn_geometry_active: bool = False, lookahead_time_s: float | None = None,
             lookahead_distance_m: float | None = None) -> NavLaneIntent:
    direction = self.MANEUVER_DIRECTIONS.get(plan.maneuver, LaneIntentDirection.none)
    event_key = (plan.session_id, plan.route_revision, plan.maneuver_event_id)

    restart = self._restart_pulse(plan, direction, speed_mps, now_ns)
    if restart is not None:
      return restart

    if self._active_key is not None:
      if event_key != self._active_key or direction != self._active_direction:
        route_continuous = (plan.session_id, plan.route_revision) == self._active_key[:2]
        if not route_continuous:
          return self._reset("turnChanged")
        if direction not in (LaneIntentDirection.none, self._active_direction):
          return self._reset("turnChanged")
        if turn_geometry_active:
          self._completion_hold = True
          self._turn_clear_since_ns = None
        elif self._completion_hold or speed_mps <= TURN_HOLD_SPEED_MPS:
          self._completion_hold = True
          if self._turn_clear_since_ns is None:
            self._turn_clear_since_ns = now_ns
          elif now_ns - self._turn_clear_since_ns >= self.TURN_CLEAR_STABLE_NS:
            return self._reset("turnChanged")
        else:
          return self._reset("turnChanged")
        return NavLaneIntent(
          signal_requested=True,
          direction=self._active_direction,
          request_id=self._active_key[2],
          target_lane_index=-1,
          reason="turnCompletion",
        )
      if self._active_since_ns is not None and now_ns - self._active_since_ns > self.SIGNAL_TIMEOUT_NS:
        return self._reset("turnSignalTimeout")
      self._track_progress(plan, now_ns)
      if (self._last_progress_ns is not None and not turn_geometry_active
          and plan.distance_m > TURN_ARRIVAL_DISTANCE_M
          and now_ns - self._last_progress_ns > TURN_LAMP_STALL_NS):
        return self._reset("turnLampStalled")
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
      self._completion_hold = False
      self._turn_clear_since_ns = None
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

    lookahead_m = self._lookahead(plan, speed_mps, lookahead_time_s, lookahead_distance_m)
    if not 0.0 < plan.distance_m <= lookahead_m:
      return self._reset("turnOutsideWindow")

    self._active_key = event_key
    self._active_direction = direction
    self._active_since_ns = now_ns
    self._plan_gap_since_ns = None
    self._last_progress_distance_m = plan.distance_m
    self._last_progress_ns = now_ns
    return NavLaneIntent(
      signal_requested=True,
      direction=direction,
      request_id=plan.maneuver_event_id,
      target_lane_index=-1,
      reason="turnApproach",
    )
