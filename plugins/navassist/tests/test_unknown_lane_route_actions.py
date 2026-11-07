"""Failure cases before implementation: missing absolute ego lane cancels a
fresh merge/exit lamp; a relative merge repeats crossings; a turn-only request
suppresses SP turn desire; no lamp feedback must never become turn intent.
Blindspots, solid paint, stale navigation and disabled controls still veto.
"""
from types import SimpleNamespace as N
import pytest
from navassist.intent import build_intent, LaneIntentCoordinator, TurnSignalCoordinator
from navassist.settings import NavSettings
from .test_migration_contract import Params, Messages


def inputs(maneuver):
  nav = dict(valid=True,linked=True,stale=False,sessionId='route',routeRevision=1,maneuverEventId=7,
             maneuver=maneuver,distanceM=80.,laneTotalCount=3,lanes=[])
  topo = dict(valid=True,visibleLaneCount=3,egoLaneIndexFromLeft=1,absoluteEgoIndex=None,
              leftNeighborExists=True,rightNeighborExists=True,leftCrossingAllowed=True,rightCrossingAllowed=True)
  return nav,topo


@pytest.mark.parametrize('maneuver',['merge_left','merge_right','exit_left','exit_right','ramp_left','ramp_right'])
def test_unknown_absolute_lane_can_signal_and_prepare_without_permission_to_cross(maneuver):
  n,t=inputs(maneuver)
  turns,lanes=TurnSignalCoordinator(),LaneIntentCoordinator()
  for tick in range(35):
    r=build_intent(n,t,settings=NavSettings(),v_ego=15.,now_ns=1_000_000_000+tick*50_000_000,
      left_blocked=False,right_blocked=False,blindspot_left=True,blindspot_right=True,
      lateral_active=True,turns=turns,lanes=lanes)
  assert r['signalRequested'] and not r['spLaneChangeReady']


def test_merge_relative_cap_does_not_repeat_after_observed_completion():
  from navassist.planning import build_lane_plan
  from navassist.coordinator import NavLaneIntentCoordinator, ObservedLaneChangeState, LaneIntentDirection
  from .test_mainroad_and_plan_gap import nav
  from .test_legacy_lane_intent import topology, vehicle
  p=build_lane_plan(nav('mergeLeft',False),N(visibleLaneCount=3,egoLaneIndexFromLeft=1),healthy=True)
  assert p.valid and p.relative_change_limit==1
  c=NavLaneIntentCoordinator()
  t=topology(ego=1,left_cross=True)
  for ns in (1,500_000_001,1_000_000_001,1_400_000_001):
    c.update(p,t,vehicle(left_blinker=True),now_ns=ns)
  c.update(p,t,vehicle(left_blinker=True,state=ObservedLaneChangeState.starting,direction=LaneIntentDirection.left),now_ns=1_500_000_001)
  for ns in (1_600_000_001,2_200_000_001):
    r=c.update(p,t,vehicle(left_blinker=True,state=ObservedLaneChangeState.pre,direction=LaneIntentDirection.left),now_ns=ns)
  assert r.reason=='laneChangeObserved'
  for ns in (3_000_000_001,6_000_000_001,7_000_000_001):
    r=c.update(p,t,vehicle(),now_ns=ns)
    assert not r.signal_requested and not r.lane_change_ready


@pytest.mark.parametrize('absolute',[None,1])
def test_junction_turn_lamp_survives_unknown_or_already_recommended_lane(absolute):
  n,t=inputs('turn_right');n['distanceM']=40.;t['absoluteEgoIndex']=absolute
  n['lanes']=[{'index':i,'recommended':i==1} for i in range(3)]
  r=build_intent(n,t,settings=NavSettings(),v_ego=5.,now_ns=1_000_000_000,left_blocked=True,
    right_blocked=True,blindspot_left=False,blindspot_right=False,lateral_active=True,
    turns=TurnSignalCoordinator(),lanes=LaneIntentCoordinator())
  assert r['signalRequested'] and r['targetLaneIndex']==-1
  from navassist.policy import NavLanePolicy
  policy=NavLanePolicy(Params());policy._msgs=Messages({'lanes.intent':{'navassist':r}})
  limits=policy.constraints(N(leftBlinker=False,rightBlinker=True),2)
  assert limits.turn_only and not limits.suppress_turn and not limits.allow_start


def test_sp_turn_intent_requires_actual_single_blinker_feedback(monkeypatch):
  import openpilot.sunnypilot.selfdrive.controls.lib.lane_turn_desire as module
  class P:
    def get(self,*a,**k):return 20
    def get_bool(self,*a,**k):return True
  monkeypatch.setattr(module,'Params',P)
  controller=module.LaneTurnController(None)
  controller.update_lane_turn(False,False,False,False,5.)
  assert controller.get_turn_direction()==module.TurnDirection.none
  controller.update_lane_turn(False,False,False,True,5.)
  assert controller.get_turn_direction()==module.TurnDirection.turnRight
  controller.update_lane_turn(False,False,True,True,5.)
  assert controller.get_turn_direction()==module.TurnDirection.none


def test_merge_lamp_only_preparation_cannot_trigger_junction_turn_desire():
  from navassist.policy import NavLanePolicy
  n,t=inputs('merge_right');n['valid']=False;n['distanceM']=40.
  out=build_intent(n,t,settings=NavSettings(),v_ego=5.,now_ns=1_000_000_000,left_blocked=True,
    right_blocked=True,blindspot_left=False,blindspot_right=False,lateral_active=True,
    turns=TurnSignalCoordinator(),lanes=LaneIntentCoordinator())
  assert out['signalRequested'] and out['targetLaneIndex']==-1
  from navassist.display import signal_status
  assert signal_status(out)=='WAIT LANE CONFIRMATION'
  policy=NavLanePolicy(Params());policy._msgs=Messages({'lanes.intent':{'navassist':out}})
  limits=policy.constraints(N(leftBlinker=False,rightBlinker=True),2)
  assert limits.turn_only and limits.suppress_turn and not limits.allow_start
  policy._msgs=Messages({});policy._last_poll=-1
  assert policy.constraints(N(leftBlinker=False,rightBlinker=True),2).suppress_turn


def test_completed_unknown_merge_does_not_restart_lamp_via_turn_fallback():
  n,t=inputs('merge_right');turns,lanes=TurnSignalCoordinator(),LaneIntentCoordinator()
  def tick(ms,state='off',blinker=False):
    return build_intent(n,t,settings=NavSettings(),v_ego=15.,now_ns=1_000_000_000+ms*1_000_000,
      left_blocked=False,right_blocked=False,blindspot_left=False,blindspot_right=False,
      lateral_active=True,right_blinker=blinker,model_state=state,model_direction='right' if state!='off' else 'none',
      turns=turns,lanes=lanes)
  for ms in (0,500,1000,1300,1600):tick(ms,blinker=True)
  assert tick(1700,'laneChangeStarting',True)['spLaneChangeReady']
  tick(1800,'preLaneChange',True)
  done=tick(2400,'preLaneChange',True)
  assert not done['signalRequested']
  for ms in (3300,6000,7000):
    out=tick(ms)
    assert not out['signalRequested'] and not out['spLaneChangeReady']


def test_aborted_lane_preparation_cannot_restart_as_turn_only_lamp():
  n,t=inputs('merge_right');turns,lanes=TurnSignalCoordinator(),LaneIntentCoordinator()
  def tick(ms,gas=False):
    return build_intent(n,t,settings=NavSettings(),v_ego=15.,now_ns=1_000_000_000+ms*1_000_000,
      left_blocked=False,right_blocked=False,blindspot_left=False,blindspot_right=False,
      lateral_active=True,gas_pressed=gas,turns=turns,lanes=lanes)
  for ms in (0,500,1000,1300):out=tick(ms)
  assert out['signalRequested'] and out['targetLaneIndex']>=0
  # Gas is no longer a cancellation gate; the request remains until the route/plan ends.
  assert tick(1400,gas=True)['signalRequested']
  assert tick(1500)['signalRequested']
