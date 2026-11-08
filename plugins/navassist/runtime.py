"""One complete pure navigation cycle; no camera, socket or vehicle actuation."""
from __future__ import annotations

from .branch import BranchMatcher
from .map_data import MapData
from .blocker import LaneChangeBlocker
from .intent import LaneIntentCoordinator, TurnSignalCoordinator, build_intent
from .intent_types import lane_change_direction_name, lane_change_state_name
from .navstate import build as build_nav_state
from .oem import OemLaneSignals
from .phone_lane import PhoneLaneEvidence, planning_index
from .position import AbsolutePosition
from .topology import from_model


class NavigationRuntime:
  def __init__(self, settings):
    self.settings = settings
    self.branch = BranchMatcher()
    self.oem = OemLaneSignals()
    self.blocker = LaneChangeBlocker()
    self.position = AbsolutePosition()
    self.phone_lane = PhoneLaneEvidence()
    self.turns = TurnSignalCoordinator()
    self.lanes = LaneIntentCoordinator(max_changes=settings.max_lane_changes)

  def tick(self, current, model, model_ns, car, cc, now_ns, *, can_list=(), vehicle_fresh=False,
           left_phone=False, right_phone=False, turn_geometry_active=False,
           localization_valid=True, map_snapshot=None, phone_lane_observation=None,
           phone_lane_estimate=None):
    self.oem.update(can_list, now_ns)
    oem = self.oem.payload(now_ns)
    topology = from_model(model, now_ns, model_ns)
    nav = build_nav_state(current, now_ns, oem_nav_route_active=oem['navRouteActive'])
    # The C3 lane model often cannot see lanes on ordinary roads; the phone's MNN estimate is the
    # driver-visible truth there, so use it as the lane geometry when it is fresh.
    est = phone_lane_estimate or {}
    if not topology.get('valid') or int(topology.get('visibleLaneCount', 0) or 0) <= 0:
      try:
        count, number, age = int(est.get('laneCount')), int(est.get('laneNumber')), int(est.get('ageNs', 1 << 62))
      except (TypeError, ValueError):
        count = number = 0; age = 1 << 62
      if est.get('valid') and count >= 1 and 1 <= number <= count and age < 1_000_000_000:
        topology.update(valid=True, visibleLaneCount=count, egoLaneIndexFromLeft=number - 1,
                        leftNeighborExists=number > 1, rightNeighborExists=number < count,
                        source='phoneLane')
        topology['phoneLaneCount'] = count
        if len(nav.get('lanes') or ()) == count:
          # The phone counts the whole road like AMap does: its lane number is an absolute index,
          # which is what lets a middle-lane recommendation be followed.
          topology['absoluteEgoIndex'] = number - 1
    nav['valid'] = bool(nav['valid'] and localization_valid)
    if not localization_valid and nav['reason'] == 'none':
      nav['reason'] = 'localLocalization'
    evidence = map_snapshot or MapData().snapshot(now_ns)
    # Broker TTL cannot extend the original CAN timestamp.
    if not 0 < evidence.get('stampNs', 0) <= now_ns or now_ns-evidence.get('stampNs', 0) > 1_000_000_000:
      evidence = MapData().snapshot(now_ns)
    if not self.settings.enabled:
      self.branch = BranchMatcher()
      evidence = MapData().snapshot(now_ns)
    nav['branchEvidence'] = self.branch.update(nav, evidence, now_ns)
    position = self.position.update(topology, nav, now_ns)
    candidate = self.phone_lane.update(phone_lane_observation, nav, now_ns,
      enabled=self.settings.enabled and self.settings.phone_lane_enabled)
    nav['phoneLaneEvidence'] = candidate
    topology['estimatedEgoIndex'] = planning_index(candidate, nav,
      enabled=self.settings.enabled and self.settings.phone_lane_enabled)
    topology['phoneLanePlanningEnabled'] = self.settings.enabled and self.settings.phone_lane_enabled
    # 手机 MNN 是车道编号的第一决策源：它报出车道号时直接采信，模型只做补充。
    _phone_abs = topology.get('absoluteEgoIndex')
    _phone_ok = isinstance(_phone_abs, int) and _phone_abs >= 0
    if _phone_ok:
      topology['absoluteEgoIndex'] = _phone_abs
      if int(topology.get('visibleLaneCount', 0) or 0) == int(topology.get('phoneLaneCount', 0) or -1):
        topology['egoLaneIndexFromLeft'] = _phone_abs
    else:
      topology['absoluteEgoIndex'] = position['lane_index']-1 if position['valid'] else None
    left_blocked, right_blocked, reasons = self.blocker.update(oem, topology,
      phone_left=left_phone, phone_right=right_phone)
    oem.update(leftBlocked=left_blocked, rightBlocked=right_blocked, blockReasons=list(reasons))
    for side in ('left', 'right'):
      topology[side+'CrossingAllowed'] = oem[side+'CrossingAllowed'] and not oem[side+'Blocked']
    usable_nav = dict(nav, valid=bool(nav['valid'] and vehicle_fresh),
                      linked=bool(nav.get('linked', nav['valid']) and vehicle_fresh),
                      routeActive=bool(nav.get('routeActive') and vehicle_fresh and self.settings.enabled))
    if not self.settings.enabled:
      usable_nav.update(valid=False, linked=False)
      self.turns.reset()
      self.lanes.reset()
    meta = getattr(model, 'meta', None)
    intent = build_intent(usable_nav, topology, settings=self.settings,
      v_ego=float(getattr(car, 'vEgo', 0.)), now_ns=now_ns, left_blocked=left_blocked, right_blocked=right_blocked,
      blindspot_left=bool(getattr(car, 'leftBlindspot', False)),
      blindspot_right=bool(getattr(car, 'rightBlindspot', False)),
      lateral_active=bool(vehicle_fresh and getattr(cc, 'latActive', False)),
      left_blinker=bool(getattr(car, 'leftBlinker', False)), right_blinker=bool(getattr(car, 'rightBlinker', False)),
      brake_pressed=bool(getattr(car, 'brakePressed', False)), gas_pressed=bool(getattr(car, 'gasPressed', False)),
      steering_pressed=bool(getattr(car, 'steeringPressed', False)),
      model_state=lane_change_state_name(getattr(meta, 'laneChangeState', 'off')),
      model_direction=lane_change_direction_name(getattr(meta, 'laneChangeDirection', 'none')),
      turn_geometry_active=turn_geometry_active,
      turns=self.turns, lanes=self.lanes)
    return dict(nav=nav, topology=topology, intent=intent, oem=oem, position=position)
