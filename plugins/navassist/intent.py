"""Adapt plugin messages to the verified legacy preparation state machines.

Fresh absolute evidence or explicitly enabled, count-matched phone estimates
translate map indices. Same-direction edge fallback
remains separate evidence and inherits the bounded source-continuity checks.
"""
from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace as N

from .coordinator import NavLaneIntentCoordinator, NavTurnSignalCoordinator
from .intent_types import LaneIntentDirection, LaneTopologyInput, LaneVehicleInput, NavTurnPlan, ObservedLaneChangeState
from .intent_types import lane_change_direction_name, lane_change_state_name
from .planning import build_lane_plan, lane_alignment_may_start, RELATIVE_ROUTE_MANEUVERS


def camel(name):
  first, *rest = str(name).split('_')
  return first+''.join(p[:1].upper()+p[1:] for p in rest)


def navigation(nav):
  items = nav.get('lanes') or []
  count = nav.get('laneTotalCount', -1)
  if type(count) is not int or not 1 <= count <= 16:
    count = max((int(l.get('index', -1))+1 for l in items), default=0)
  if not items:
    count = 0
  by_index = {int(l['index']): l for l in items if type(l.get('index')) is int}
  return N(valid=bool(nav.get('valid')), stale=bool(nav.get('stale', False)),
           sessionId=str(nav.get('sessionId', '')), routeRevision=int(nav.get('routeRevision', 0)),
           maneuverEventId=int(nav.get('maneuverEventId', 0)), maneuver=camel(nav.get('maneuver', 'none')),
           maneuverDistanceM=float(nav.get('distanceM', 0)),
           lanes=[N(index=i, recommended=by_index.get(i, {}).get('recommended') is True) for i in range(count)])


@dataclass
class LanePlan:
  direction: str = 'none'
  target_lane: int = -1
  absolute_target: int = -1
  reason: str = 'idle'
  edge_anchored: bool = False
  core: object = None
  topology: object = None
  speed: float = 0.


def planning_ego_index(topology):
  # Model ownership clears stale geometry fallback when its observation is unknown.
  if topology.get('phoneLanePlanningEnabled'):
    estimated = topology.get('estimatedEgoIndex')
    if isinstance(estimated, int):
      return estimated
    return None
  absolute = topology.get('absoluteEgoIndex')
  if isinstance(absolute, int) and absolute >= 0:
    return absolute
  return None


def lane_plan(nav, topology, settings, *, v_ego):
  n = navigation(nav)
  count, ego = int(topology.get('visibleLaneCount', 0)), int(topology.get('egoLaneIndexFromLeft', -1))
  absolute = planning_ego_index(topology)
  if type(absolute) is not int:
    absolute = None
  core = build_lane_plan(n, N(visibleLaneCount=count, egoLaneIndexFromLeft=ego),
                         healthy=True, settings=settings, amap_ego_index=absolute)
  target = NavLaneIntentCoordinator._target(core, ego) if core.valid else None
  direction = (NavLaneIntentCoordinator._relative_direction(core) or
               NavLaneIntentCoordinator._direction(ego, target)) if target is not None else LaneIntentDirection.none
  # The facade's target is adjacent; the core retains the actual route target.
  adjacent = NavLaneIntentCoordinator._adjacent_target_index(ego, direction) if direction else -1
  return LanePlan('left' if direction == LaneIntentDirection.left else 'right' if direction else 'none',
                  adjacent, -1, 'edgeFallback' if core.heuristic else 'modelLane' if topology.get('phoneLanePlanningEnabled') else 'absoluteLane', absolute is not None,
                  core, topology, v_ego)


def payload(intent, nav):
  return dict(valid=bool(nav.get('linked', nav.get('valid'))), sessionId=str(nav.get('sessionId', '')),
              routeRevision=int(nav.get('routeRevision', 0)), maneuverEventId=int(nav.get('maneuverEventId', 0)),
              signalRequested=intent.signal_requested, direction=intent.direction.name,
              targetLaneIndex=intent.target_lane_index, spLaneChangeReady=intent.lane_change_ready,
              laneChangeAllowed=intent.lane_change_ready, reason=intent.reason, requestId=intent.request_id,
              forkNow=False, allowUnknownCrossing=False, ignoreSolidBoundary=False,
              signalPurpose='nativeLaneChange' if nav.get('maneuver') in ('slight_left', 'slight_right')
                and intent.target_lane_index < 0 else 'lanePreparation' if nav.get('maneuver') in
                ('merge_left', 'merge_right', 'exit_left', 'exit_right', 'ramp_left', 'ramp_right')
                or intent.target_lane_index >= 0 else 'junction')


class TurnSignalCoordinator:
  def __init__(self):
    self.core = NavTurnSignalCoordinator()
    self._synth_key = None
    self._synth_id = 0
    self._synth_last_distance = None
    self._yield_until_ns = 0
    self._lamp_seen_key = None
    self._lamp_off_since_ns = 0
    self._lamp_drops = 0

  def reset(self):
    self.core = NavTurnSignalCoordinator()
    self._yield_until_ns = 0
    self._lamp_seen_key = None
    self._lamp_off_since_ns = 0
    self._lamp_drops = 0

  def update(self, nav, *, speed_mps, now_ns, lookahead_time_s=8., lookahead_distance_m=None,
             turn_geometry_active=False, left_blinker=False, right_blinker=False):
    n = navigation(nav)
    # Route-active but not yet position-matched still carries guidance: arm the lamp early, while lane
    # change readiness remains gated by the fully valid/matched nav state.
    armed = bool((nav.get('linked', nav.get('valid', False)) or nav.get('routeActive', False))
                 and not nav.get('stale', False))
    event_id = int(n.maneuverEventId)
    if event_id == 0 and armed and n.maneuver not in ("", "none", "destination", "unknown") and n.maneuverDistanceM > 0:
      key = (n.sessionId, n.routeRevision, n.maneuver)
      passed = (self._synth_last_distance is not None and self._synth_last_distance < 30.0
                and n.maneuverDistanceM > 100.0)
      if key != self._synth_key or passed:
        self._synth_key = key
        self._synth_id += 1
      event_id = self._synth_id
    if event_id:
      self._synth_last_distance = n.maneuverDistanceM
    plan = NavTurnPlan(armed, n.sessionId, n.routeRevision, event_id, n.maneuver, n.maneuverDistanceM)
    out = payload(self.core.update(plan, speed_mps=speed_mps, now_ns=now_ns,
                                  lookahead_time_s=lookahead_time_s,
                                  lookahead_distance_m=lookahead_distance_m,
                                  turn_geometry_active=turn_geometry_active), nav)
    key = (n.sessionId, n.routeRevision, n.maneuverEventId)
    ours = 'right' if out.get('direction') == 'RIGHT' else 'left' if out.get('direction') == 'LEFT' else ''
    opposing = bool(ours and ((ours == 'right' and left_blinker) or (ours == 'left' and right_blinker)))
    if opposing:
      # The driver used the stalk against navigation: hand the lamp over, then take the route back.
      self.core.reset()
      self._lamp_seen_key = None
      self._lamp_off_since_ns = 0
      self._lamp_drops = 0
      self._yield_until_ns = now_ns + 1_500_000_000
      return dict(out, signalRequested=False, direction='none', reason='driverYielding')
    if now_ns < self._yield_until_ns and (left_blinker or right_blinker):
      return dict(out, signalRequested=False, direction='none', reason='driverYielding')
    if not out['signalRequested']:
      self._lamp_seen_key = None
      self._lamp_off_since_ns = 0
      self._lamp_drops = 0
      return out
    lamp_on = (right_blinker if ours == 'right' else left_blinker) if ours else False
    if lamp_on:
      if self._lamp_seen_key == key and self._lamp_off_since_ns:
        self._lamp_drops += 1  # the car handed the lamp back while we still asked for it
      self._lamp_seen_key = key
      self._lamp_off_since_ns = 0
      if self._lamp_drops >= 2:
        self.core.reset()
        self._lamp_seen_key = None
        self._lamp_off_since_ns = 0
        self._lamp_drops = 0
        return dict(out, signalRequested=False, direction='none', reason='lampRejected')
    elif self._lamp_seen_key == key and not left_blinker and not right_blinker:
      if self._lamp_off_since_ns == 0:
        self._lamp_off_since_ns = now_ns
      elif now_ns - self._lamp_off_since_ns > 400_000_000:
        self.core.reset()
        self._lamp_seen_key = None
        self._lamp_off_since_ns = 0
        return dict(out, signalRequested=False, direction='none', reason='driverCancelled')
    return out


class LaneIntentCoordinator:
  def __init__(self, *, max_changes=5):
    self.max_changes = max_changes
    self.core = NavLaneIntentCoordinator(max_changes=max_changes)
    self._completed_relative_event = None
    self._owned_lane_event = None
    self._hold = None

  def reset(self):
    self.core = NavLaneIntentCoordinator(max_changes=self.max_changes)
    self._completed_relative_event = None
    self._owned_lane_event = None
    self._hold = None

  def update(self, nav, plan, *, now_ns, topology_valid, left_blocked, right_blocked,
             blindspot_left, blindspot_right, lateral_active, left_blinker=False, right_blinker=False,
             brake_pressed=False, gas_pressed=False, steering_pressed=False,
             model_state='off', model_direction='none', allow_new_lane_change=True):
    t = plan.topology or {}
    count, ego = int(t.get('visibleLaneCount', 0)), int(t.get('egoLaneIndexFromLeft', -1))

    def neighbor(side, present):
      if not topology_valid:
        return None
      return True if t.get(side+'NeighborExists', present) else False if t.get(side+'RoadEdge') else None

    topology = LaneTopologyInput(topology_valid, count, ego, neighbor('left', ego > 0),
      neighbor('right', 0 <= ego < count-1),
      bool(t.get('leftCrossingAllowed') or plan.core.allow_unknown_crossing) and not left_blocked and not t.get('leftRoadEdge'),
      bool(t.get('rightCrossingAllowed') or plan.core.allow_unknown_crossing) and not right_blocked and not t.get('rightRoadEdge'))
    state = {'off': ObservedLaneChangeState.off, 'preLaneChange': ObservedLaneChangeState.pre,
             'laneChangeStarting': ObservedLaneChangeState.starting,
             'laneChangeFinishing': ObservedLaneChangeState.finishing}.get(
               lane_change_state_name(model_state), ObservedLaneChangeState.off)
    direction = {'none': LaneIntentDirection.none, 'left': LaneIntentDirection.left,
                 'right': LaneIntentDirection.right}.get(
                   lane_change_direction_name(model_direction), LaneIntentDirection.none)
    vehicle = LaneVehicleInput(lateral_active, plan.speed, blindspot_left, blindspot_right,
      left_blinker, right_blinker, brake_pressed, gas_pressed, steering_pressed, state, direction)
    result = self.core.update(plan.core, topology, vehicle, now_ns=now_ns,
                              allow_new_lane_change=allow_new_lane_change)
    event = (nav.get('sessionId'), nav.get('routeRevision'), nav.get('maneuverEventId'))
    if plan.core.relative_change_limit == 1 and result.reason == 'laneChangeObserved':
      self._completed_relative_event = event
    if result.reason in ('laneChangeObserved', 'laneChangeComplete', 'heuristicChangeLimit', 'changeLimit'):
      self._hold = None
    if result.signal_requested:
      self._owned_lane_event = event
    out = dict(payload(result, nav), relativeStepComplete=self._completed_relative_event == event,
               laneRequestOwned=self._owned_lane_event == event)
    # A started change must not be dropped by a one-frame plan gap: that makes the host re-press the
    # stalk and the lamp blinks. Hold the same request briefly instead.
    prepared = lane_change_state_name(model_state) in ('preLaneChange', 'laneChangeStarting', 'laneChangeFinishing')
    if out['signalRequested'] and int(out.get('targetLaneIndex', -1)) >= 0:
      self._hold = (event, out, now_ns + 4_000_000_000)
    elif self._hold is not None:
      held_event, held_out, until_ns = self._hold
      if held_event == event and now_ns <= until_ns and prepared:
        return dict(held_out, reason='laneHold')
      self._hold = None
    return out


def build_intent(nav, topology, *, settings, v_ego, now_ns, left_blocked, right_blocked,
                 blindspot_left, blindspot_right, lateral_active, turns, lanes,
                 left_blinker=False, right_blinker=False, brake_pressed=False, gas_pressed=False,
                 steering_pressed=False, model_state='off', model_direction='none', turn_geometry_active=False):
  turn = turns.update(nav, speed_mps=v_ego, now_ns=now_ns, lookahead_time_s=settings.signal_lead_time_s,
                      lookahead_distance_m=settings.turn_lane_lookahead_m,
                      turn_geometry_active=turn_geometry_active,
                      left_blinker=left_blinker, right_blinker=right_blinker)
  n = navigation(nav)
  intersection = n.maneuver in ('turnLeft', 'sharpLeft', 'uTurnLeft', 'turnRight', 'sharpRight', 'uTurnRight')
  approaching = bool(intersection and turn['signalRequested'])
  plan = lane_plan(nav, topology, settings, v_ego=v_ego)
  out = lanes.update(nav, plan, now_ns=now_ns, topology_valid=bool(topology.get('valid')),
    left_blocked=left_blocked, right_blocked=right_blocked,
    blindspot_left=blindspot_left, blindspot_right=blindspot_right, lateral_active=lateral_active,
    left_blinker=left_blinker, right_blinker=right_blinker, brake_pressed=brake_pressed,
    gas_pressed=gas_pressed, steering_pressed=steering_pressed, model_state=model_state,
    model_direction=model_direction, allow_new_lane_change=n.maneuverDistanceM > 0 and not approaching)
  if (n.maneuver in RELATIVE_ROUTE_MANEUVERS and planning_ego_index(topology) is None
      and out.get('relativeStepComplete')):
    out.update(signalRequested=False, spLaneChangeReady=False, laneChangeAllowed=False, reason='heuristicChangeLimit')
    return out
  if out['signalRequested']:
    return out
  if settings.turn_signal_enabled and turn['signalRequested']:
    relative_route_action = n.maneuver in ('mergeLeft', 'mergeRight', 'exitLeft', 'exitRight', 'rampLeft', 'rampRight')
    if relative_route_action and gas_pressed:
      return dict(out, signalRequested=False, spLaneChangeReady=False,
                  laneChangeAllowed=False, reason='driverAccelerator')
    if relative_route_action and out.get('laneRequestOwned'):
      return out  # Never bypass a lane coordinator's pause/abort via a turn-only fallback.
    if not intersection and out['reason'] in ('alreadyInRecommendedLane', 'noNeighbor'):
      return out
    # A completed relative merge cannot turn its lamp back on via the turn-only
    # fallback after the one-step lane coordinator has ended the request.
    if relative_route_action and out['reason'] in ('heuristicChangeLimit', 'changeLimit'):
      return out
    return turn
  if out['reason'] in ('routeChanged', 'neighborObservationPaused', 'crossingWaitTimeout') or out['reason'].startswith('lanePosition'):
    return out
  # 已经在要并过去那一侧的路沿：为「并道」点灯已经没有意义，直接不发（路口转弯灯不受影响）
  _LANE_CHANGE_LAMPS = frozenset(("slightLeft", "slightRight", "keepLeft", "keepRight",
                                  "exitLeft", "exitRight", "rampLeft", "rampRight", "mergeLeft", "mergeRight"))
  if turn.get('signalRequested') and str(n.maneuver) in _LANE_CHANGE_LAMPS:
    _count = int(topology.get('visibleLaneCount', 0) or 0)
    _ego = int(topology.get('egoLaneIndexFromLeft', -1) or -1)
    _dir = str(turn.get('direction', 'none')).lower()
    if _count > 1 and 0 <= _ego < _count:
      _at_edge = (_dir == 'left' and _ego == 0) or (_dir == 'right' and _ego == _count - 1)
      if _at_edge:
        turn = dict(turn, signalRequested=False, direction='none', reason='atRoadEdge')
  return turn if settings.turn_signal_enabled else out

