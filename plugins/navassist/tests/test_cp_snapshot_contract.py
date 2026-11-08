"""Failures specified against CP latest-snapshot 91d77de before adaptation:
CP16 sharp-left is lost; SDK exit/fork/slight-turn codes are conflated; phone
vision estimates become map-lane facts; explicit route withdrawal retains prior
route lanes. No remote commands, permissions or camera transport are introduced.
"""
import pytest
from .test_cp_navigation_contract import ready, update

@pytest.mark.parametrize('code,expected', [(16,'sharp_left'),(17,'keep_left'),
 (101,'exit_right'),(102,'exit_left'),(6,'merge_right'),(7,'merge_left'),
 (1000,'slight_left'),(1001,'slight_right')])
def test_latest_cp_maneuver_codes_keep_distinct_semantics(code,expected):
 s=ready();update(s,'guidance_current',{'turn_type':code,'distance_m':80},seq=2)
 n=s.normalized(1_000_000_000_000)
 assert n['valid'] and n['maneuver']==expected


def test_phone_model_observation_never_identifies_map_lane_or_recommendation():
 s=ready();update(s,'lane_current',{'count':5,'current_lane':2,'lane_source':'model',
  'model_count':5,'model_current_lane':2,
  'lanes':[{'index':i,'is_recommended':i==1} for i in range(5)]},seq=2)
 n=s.normalized(1_000_000_000_000)
 assert n['valid'] and not n['lanes'] and n['laneTotalCount']==-1
 e=n['modelLaneEstimate'];assert e['count']==5 and e['laneNumber']==2
 assert e['confirmed'] is False and e['mapAssociated'] is False

@pytest.mark.parametrize('count,current',[(True,1),(5,True),(17,2),(3,4),(-1,1)])
def test_invalid_model_estimates_remain_unknown(count,current):
 s=ready();update(s,'lane_current',{'lane_source':'model','model_count':count,'model_current_lane':current},seq=2)
 assert s.normalized(1_000_000_000_000).get('modelLaneEstimate') is None


def test_explicit_route_withdrawal_cannot_reuse_previous_route_guidance_or_lanes():
 s=ready();before=s.normalized(1_000_000_000_000)
 update(s,'route',None,stamp=1_000_001,seq=2)
 update(s,'route',{'remain_distance_m':10000,'remain_time_sec':900,'total_distance_m':12000},stamp=1_000_002,seq=3)
 n=s.normalized(1_000_000_000_000)
 assert not n['valid'] and not n['lanes']
 assert n['routeRevision']>before['routeRevision']


def test_model_observation_expires_and_controlled_metadata_remains_ignored():
 s=ready();update(s,'lane_current',{'lane_source':'model','model_count':3,'model_current_lane':2,
  'automatic_lane_change_allowed':True},seq=2)
 n=s.normalized(1_000_000_000_000)
 assert not n['lanes'] and n['modelLaneEstimate']['confirmed'] is False
 assert s.normalized(1_002_000_000_000).get('modelLaneEstimate') is None


def test_previous_route_rejection_does_not_change_observation_clock():
 s=ready();update(s,'route',None,stamp=1_000_100,seq=2)
 before=dict(s.observation_stamps)
 with pytest.raises(ValueError,match='previous_route_observation'):
  update(s,'guidance_current',{'turn_type':13,'distance_m':80},stamp=1_000_050,seq=2)
 assert s.observation_stamps==before


def test_prior_route_summary_cannot_be_reintroduced_after_withdrawal():
 s=ready();update(s,'route',None,stamp=1_000_100,seq=2)
 with pytest.raises(ValueError,match='previous_route_observation'):
  update(s,'route',{'remain_distance_m':10000,'remain_time_sec':900,'total_distance_m':12000},stamp=1_000_050,seq=3)
