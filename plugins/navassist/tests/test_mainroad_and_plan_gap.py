"""Failure contracts before fix: merge guidance is not lane-membership proof;
short position gaps retain only bounded lamp preparation, never stale permission.
"""
from dataclasses import replace
from types import SimpleNamespace as N
import pytest
from navassist.planning import build_lane_plan
from navassist.settings import NavSettings
from navassist.intent import build_intent, LaneIntentCoordinator, TurnSignalCoordinator
from navassist.tests.test_legacy_preparation_continuity import preparation


def nav(maneuver='mergeRight',lanes=True):
 return N(valid=True,stale=False,sessionId='route',routeRevision=1,maneuverEventId=7,
  maneuver=maneuver,maneuverDistanceM=80.,lanes=[N(index=i,recommended=i==2) for i in range(3)] if lanes else [])


@pytest.mark.parametrize('maneuver',['mergeLeft','mergeRight'])
@pytest.mark.parametrize('lanes',[False,True])
def test_merge_without_absolute_position_uses_one_relative_step(maneuver,lanes):
 p=build_lane_plan(nav(maneuver,lanes),N(visibleLaneCount=3,egoLaneIndexFromLeft=1),healthy=True)
 assert p.valid and p.heuristic and p.relative_change_limit == 1
 assert not p.force_fork and not p.ignore_solid_boundary


def test_merge_allows_only_proven_mismatch_and_already_recommended_is_no_action():
 topo=N(visibleLaneCount=3,egoLaneIndexFromLeft=1)
 p=build_lane_plan(nav(),topo,healthy=True,amap_ego_index=2)
 assert p.valid and not p.heuristic and p.recommended_indices==(1,)
 p=build_lane_plan(nav(),topo,healthy=True,amap_ego_index=1)
 assert p.valid and p.recommended_indices==(2,) and not p.heuristic


@pytest.mark.parametrize('absolute',[2])
def test_shared_publisher_does_not_fall_through_to_merge_turn_lamp(absolute):
 n=dict(valid=True,stale=False,linked=True,sessionId='route',routeRevision=1,maneuverEventId=7,
  maneuver='merge_right',distanceM=80.,laneTotalCount=3,lanes=[{'index':i,'recommended':i==2} for i in range(3)])
 t=dict(valid=True,visibleLaneCount=3,egoLaneIndexFromLeft=1,absoluteEgoIndex=absolute,
  leftNeighborExists=True,rightNeighborExists=True,leftCrossingAllowed=True,rightCrossingAllowed=True)
 turns,lanes=TurnSignalCoordinator(),LaneIntentCoordinator()
 for i in range(40):
  r=build_intent(n,t,settings=NavSettings(),v_ego=15.,now_ns=1_000_000_000+i*50_000_000,
   left_blocked=False,right_blocked=False,blindspot_left=False,blindspot_right=False,lateral_active=True,turns=turns,lanes=lanes)
  assert not r['signalRequested'] and not r['spLaneChangeReady']


def test_short_plan_gap_keeps_request_but_needs_new_readiness_confirmation():
 c,p,t,v,request=preparation()
 gap=replace(p,valid=False,recommended_indices=(),observation_interrupted=True)
 for i in range(7):
  r=c.update(gap,t,v,now_ns=2_500_000_000+i*50_000_000)
  assert r.signal_requested and r.request_id==request and not r.lane_change_ready
 for i in range(10):
  r=c.update(p,t,v,now_ns=2_850_000_000+i*50_000_000)
  assert r.signal_requested and r.request_id==request and not r.lane_change_ready
 for i in range(10):
  r=c.update(p,t,v,now_ns=3_350_000_000+i*50_000_000)
 assert r.signal_requested and r.lane_change_ready


def test_repeated_bad_plan_frames_keep_original_missing_and_total_budgets():
 c,p,t,v,request=preparation()
 gap=replace(p,valid=False,recommended_indices=(),observation_interrupted=True)
 assert c.update(gap,t,v,now_ns=2_500_000_000).signal_requested
 r=c.update(gap,t,v,now_ns=3_500_000_001)
 assert not r.signal_requested and not r.lane_change_ready
 c,p,t,v,request=preparation()
 r=c.update(gap,t,v,now_ns=100_000_000_000)
 assert not r.signal_requested and r.reason=='crossingWaitTimeout'


@pytest.mark.parametrize('changes',[{'left_blinker':True},{'brake_pressed':True}])
def test_driver_override_still_ends_preparation_during_a_plan_gap(changes):
 c,p,t,v,_=preparation()
 gap=replace(p,valid=False,recommended_indices=(),observation_interrupted=True)
 r=c.update(gap,t,replace(v,**changes),now_ns=2_500_000_000)
 assert not r.signal_requested and not r.lane_change_ready
