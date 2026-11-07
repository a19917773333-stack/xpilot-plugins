from __future__ import annotations

import math
from .intent_types import NavLanePlan, NavLaneIntent, LaneIntentDirection
from .settings import NavSettings


LEFT_TURN_LANE_MANEUVERS = frozenset(("turnLeft", "sharpLeft", "uTurnLeft"))


RIGHT_TURN_LANE_MANEUVERS = frozenset(("turnRight", "sharpRight", "uTurnRight"))


LEFT_EXIT_LANE_MANEUVERS = frozenset(("exitLeft", "rampLeft", "mergeLeft"))


RIGHT_EXIT_LANE_MANEUVERS = frozenset(("exitRight", "rampRight", "mergeRight"))
# Freeways aim at the exit-side edge well before the exit itself.
FREEWAY_RECOMMENDED_FROM_M = 800.0
ROAD_KIND_LOOKAHEAD_SCALE = {"expressway": 1.0, "urban_expressway": 0.8, "ramp": 0.0}
# No recommendation at all: drift to the maneuver's side only this close, and only once.
EDGE_FALLBACK_FROM_M = 250.0
DIRECTIONAL_MANEUVERS = (LEFT_TURN_LANE_MANEUVERS | RIGHT_TURN_LANE_MANEUVERS
                         | LEFT_EXIT_LANE_MANEUVERS | RIGHT_EXIT_LANE_MANEUVERS
                         | frozenset(("slightLeft", "slightRight", "keepLeft", "keepRight")))


MERGE_MANEUVERS = frozenset(("mergeLeft", "mergeRight"))
RELATIVE_ROUTE_MANEUVERS = LEFT_EXIT_LANE_MANEUVERS | RIGHT_EXIT_LANE_MANEUVERS

FORK_NOW_DISTANCE_M = 50.0


def build_lane_plan(nav, topology, *, healthy: bool, settings: NavSettings | None = None,
                    amap_ego_index: int | None = None) -> NavLanePlan:
  settings = settings if settings is not None else NavSettings()
  nav_valid = bool(healthy and nav.valid and not nav.stale and settings.enabled and settings.lane_change_enabled)
  lanes = tuple(nav.lanes)
  recommended = tuple(int(lane.index) for lane in lanes if lane.recommended)
  maneuver = str(nav.maneuver)
  distance_m = float(nav.maneuverDistanceM)
  lane_count = int(topology.visibleLaneCount)
  road_kind = str(getattr(nav, 'roadKind', 'unknown'))
  scale = ROAD_KIND_LOOKAHEAD_SCALE.get(road_kind, 1.0)
  if road_kind == 'ramp':
    nav_valid = False  # no new lane changes while on a ramp
  fallback_side = None
  lookahead_m = 0.0
  if maneuver in LEFT_TURN_LANE_MANEUVERS:
    fallback_side, lookahead_m = "left", settings.turn_lane_lookahead_m
  elif maneuver in RIGHT_TURN_LANE_MANEUVERS:
    fallback_side, lookahead_m = "right", settings.turn_lane_lookahead_m
  elif maneuver in LEFT_EXIT_LANE_MANEUVERS:
    fallback_side, lookahead_m = "left", settings.exit_lane_lookahead_m * scale
  elif maneuver in RIGHT_EXIT_LANE_MANEUVERS:
    fallback_side, lookahead_m = "right", settings.exit_lane_lookahead_m * scale
  fork_now = bool(
    maneuver in LEFT_EXIT_LANE_MANEUVERS | RIGHT_EXIT_LANE_MANEUVERS
    and math.isfinite(distance_m) and 0.0 < distance_m <= FORK_NOW_DISTANCE_M
  )

  if maneuver in RELATIVE_ROUTE_MANEUVERS:
    if amap_ego_index is None:
      # A missing full-road lane number is not a reason to discard a fresh
      # merge/exit/ramp instruction. Prepare one adjacent relative step, not an edge
      # search across the whole road; observation/paint/BSM gates stay below.
      visual_ego = int(topology.egoLaneIndexFromLeft)
      ready = bool(nav_valid and int(nav.maneuverEventId) != 0
                   and 0 <= visual_ego < lane_count and fallback_side is not None
                   and math.isfinite(distance_m) and 0 < distance_m <= lookahead_m)
      target = 0 if fallback_side == 'left' else max(0, lane_count-1)
      return NavLanePlan(ready, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId),
                         lane_count, (target,), heuristic=True,
                         edge_direction=LaneIntentDirection.left if fallback_side == 'left' else LaneIntentDirection.right,
                         relative_change_limit=1)
    if not (nav_valid and lanes and recommended and 0 <= amap_ego_index < len(lanes)
            and 0 <= int(topology.egoLaneIndexFromLeft) < lane_count):
      return NavLanePlan(False, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId),
                         len(lanes), (), observation_interrupted=bool(nav_valid and recommended))
    fallback_side = None  # A confirmed absolute position still resolves the actual recommendation.

  if lanes:
    amap_lane_count = len(lanes)
    # Translate AMap full-road recommendations into the local visible window.
    # Passing AMap indices raw makes the coordinator compare them with a
    # different egoLaneIndexFromLeft and steer to the wrong edge.
    if nav_valid and amap_ego_index is not None and 0 <= amap_ego_index < amap_lane_count:
      visual_ego = int(topology.egoLaneIndexFromLeft)
      if 0 <= visual_ego < lane_count:
        offset = amap_ego_index - visual_ego
        visual_recommended = tuple(index - offset for index in recommended if 0 <= index - offset < lane_count)
        if visual_recommended:
          return NavLanePlan(
            True, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId),
            lane_count, visual_recommended,
          )
    # A confirmed absolute lane also permits one adjacent step toward a
    # recommendation outside the local window. Do not equate the local index
    # with an absolute lane or require the final destination to be visible.
    if nav_valid and amap_ego_index is not None and 0 <= amap_ego_index < amap_lane_count:
      visual_ego = int(topology.egoLaneIndexFromLeft)
      absolute_recommended = tuple(index for index in recommended if 0 <= index < amap_lane_count)
      if 0 <= visual_ego < lane_count and absolute_recommended:
        nearest = min(absolute_recommended, key=lambda index: (abs(index - amap_ego_index), index))
        step = -1 if nearest < amap_ego_index else (1 if nearest > amap_ego_index else 0)
        adjacent = visual_ego + step
        if step and 0 <= adjacent < lane_count:
          return NavLanePlan(
            True, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId),
            lane_count, (adjacent,),
          )
    edge_recommended = bool(
      (fallback_side == "left" and 0 in recommended)
      or (fallback_side == "right" and amap_lane_count - 1 in recommended)
    )
    if nav_valid and edge_recommended and math.isfinite(distance_m) and 0.0 <= distance_m <= lookahead_m:
      target = 0 if fallback_side == "left" else max(0, lane_count - 1)
      return NavLanePlan(
        True, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId),
        lane_count, (target,), heuristic=True,
        edge_direction=LaneIntentDirection.left if fallback_side == "left" else LaneIntentDirection.right,
        force_fork=fork_now, allow_unknown_crossing=True, ignore_solid_boundary=fork_now,
      )
    # Last resort: nothing recommends a lane and the maneuver is close. Head for the edge on the
    # maneuver's own side, one step at a time, and stop asking once that edge lane is reached.
    visual_ego = int(topology.egoLaneIndexFromLeft)
    if (nav_valid and not recommended and maneuver in DIRECTIONAL_MANEUVERS
        and math.isfinite(distance_m) and 0.0 < distance_m <= EDGE_FALLBACK_FROM_M
        and 0 <= visual_ego < lane_count):
      side = "left" if "left" in maneuver.lower() else "right"
      edge_index = 0 if side == "left" else lane_count - 1
      if visual_ego != edge_index:
        return NavLanePlan(
          True, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId),
          lane_count, (visual_ego - 1 if side == "left" else visual_ego + 1,), heuristic=True,
          edge_direction=LaneIntentDirection.left if side == "left" else LaneIntentDirection.right,
          allow_unknown_crossing=True, relative_change_limit=1,
        )
      return NavLanePlan(
        False, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId), lane_count, (),
        observation_interrupted=True,
      )
    # No trustworthy absolute lane number: follow the recommendation's own geometry. Recommended
    # lanes left of the road centre mean one step left, otherwise one step right, once per event.
    visual_ego = int(topology.egoLaneIndexFromLeft)
    if nav_valid and recommended and lane_count > 1 and 0 <= visual_ego < lane_count:
      if len(lanes) == lane_count and visual_ego in recommended:
        return NavLanePlan(
          False, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId), lane_count, (),
          observation_interrupted=True,
        )
      centre = (len(lanes) - 1) / 2.0
      rec_centre = sum(recommended) / len(recommended)
      side = "left" if rec_centre < centre else "right"
      target = max(0, visual_ego - 1) if side == "left" else min(lane_count - 1, visual_ego + 1)
      if target != visual_ego:
        return NavLanePlan(
          True, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId),
          lane_count, (target,), heuristic=True,
          edge_direction=LaneIntentDirection.left if side == "left" else LaneIntentDirection.right,
          allow_unknown_crossing=True, relative_change_limit=1,
        )
    # AMap lane indices describe the complete road while modelV2 exposes only a
    # local visible window. Without an edge-qualified directional target there
    # is no common absolute index, so retain the observation but do not control.
    return NavLanePlan(
      False, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId), amap_lane_count, (),
      observation_interrupted=bool(nav_valid and recommended),
    )

  heuristic_valid = bool(
    nav_valid and int(nav.maneuverEventId) != 0 and fallback_side is not None
    and math.isfinite(distance_m) and 0.0 <= distance_m <= lookahead_m
  )
  if heuristic_valid:
    target = 0 if fallback_side == "left" else max(0, lane_count - 1)
    return NavLanePlan(
      True, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId), lane_count, (target,), heuristic=True,
      edge_direction=LaneIntentDirection.left if fallback_side == "left" else LaneIntentDirection.right,
      force_fork=fork_now, allow_unknown_crossing=True, ignore_solid_boundary=fork_now,
    )

  return NavLanePlan(
    nav_valid, str(nav.sessionId), int(nav.routeRevision), int(nav.maneuverEventId), len(lanes), recommended,
  )


def lane_alignment_may_start(nav, turn_intent: NavLaneIntent) -> bool:
  distance_m = float(nav.maneuverDistanceM)
  approaching_turn = bool(
    turn_intent.signal_requested and str(nav.maneuver) in LEFT_TURN_LANE_MANEUVERS | RIGHT_TURN_LANE_MANEUVERS
  )
  return math.isfinite(distance_m) and distance_m > 0.0 and not approaching_turn

