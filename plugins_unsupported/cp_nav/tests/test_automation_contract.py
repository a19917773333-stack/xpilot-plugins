"""Failures first: speed increases cross a missing source/driver boundary;
CP's three-frame/2.5s request and 30s lane-memory phases are skipped; return
commands are treated as completed; unknown side observations become clearance.
"""
from cp_nav.settings import CPSettings
from cp_nav.speed import CPSpeedPolicy
from cp_nav.overtake import CPOvertake


def speed_state():return dict(valid=True,control_allowed=True,raw_limit_kph=100,carrot={'desiredSpeed':100,'desiredSource':'road'})


def test_intelligent_raise_is_bounded_and_driver_change_cancels():
 p=CPSpeedPolicy();s=CPSettings(enabled=True,speed_raise=True,max_kph=100)
 out=p.update(speed_state(),v_cruise=60/3.6,v_ego=60/3.6,long_active=True,override=False,settings=s,now_ns=1_000_000_000)
 assert 60/3.6-1e-9<=out<=70/3.6+1e-9
 out=p.update(speed_state(),v_cruise=60/3.6,v_ego=65/3.6,long_active=True,override=False,settings=s,now_ns=4_000_000_000)
 assert out<=80/3.6+1e-9
 assert p.update(speed_state(),v_cruise=50/3.6,v_ego=65/3.6,long_active=True,override=False,settings=s,now_ns=4_100_000_000) is None


def test_raise_requires_explicit_master_and_qualified_live_source():
 for fault in ('master','raise','source','limit','active','override'):
  p=CPSpeedPolicy();state=speed_state();cfg=CPSettings(enabled=fault!='master',speed_raise=fault!='raise')
  if fault=='source':state['valid']=False
  if fault=='limit':state['raw_limit_kph']=None
  out=p.update(state,v_cruise=60/3.6,v_ego=60/3.6,long_active=fault!='active',override=fault=='override',settings=cfg,now_ns=1_000_000_000)
  assert out is None,fault


def observation(frame=1):
 side=dict(observed=True,neighbor=True,allowed=True,blindspot=False,gap_clear=True,crossable=True)
 return dict(authority=True,fresh=True,road_type=0,speed_mps=25.,cruise_mps=28.,curvature=.001,steering_deg=1.,
  nav_distance_m=5000,lead={'observed':True,'distance_m':45.,'speed_mps':18.},
  sides={'left':dict(side),'right':dict(side)},model_state='off',model_direction='none',frame=frame,
  passed_confirmed=False,return_advantage_kph=10.)


def test_cp_trigger_debounce_request_completion_then_return():
 p=CPOvertake();s=CPSettings(enabled=True,overtake_mode=2)
 for i in range(3):out=p.update(observation(i+1),s,1_000_000_000+i*100_000_000)
 assert out['state']=='preparing' and not out.get('request_direction')
 out=p.update(observation(4),s,4_000_000_000)
 assert out['request_direction']=='left'
 # Original-lane memory records an actual completed change, not command enqueue.
 for i,state in enumerate(('laneChangeStarting','laneChangeFinishing','off')):
  x=observation(i+5);x.update(model_state=state,model_direction='left' if state!='off' else 'none')
  out=p.update(x,s,4_100_000_000+i*100_000_000)
 assert p.net_changes==1
 x=observation(8);x['passed_confirmed']=True
 p.update(x,s,5_000_000_000)
 x['frame']=9;out=p.update(x,s,7_100_000_000)
 assert out['request_direction']=='right'
 assert p.net_changes==1  # Sending the return request is not return completion.


def test_unknown_or_unsafe_side_and_driver_fault_block_passing():
 for fault in ('authority','blindspot','line','missingSide','nearTurn','stale'):
  p=CPOvertake();s=CPSettings(enabled=True,overtake_mode=2);x=observation()
  if fault=='authority':x['authority']=False
  if fault=='stale':x['fresh']=False
  if fault=='nearTurn':x['nav_distance_m']=500
  if fault=='blindspot':
   for side in x['sides'].values():side['blindspot']=True
  if fault=='line':
   for side in x['sides'].values():side['crossable']=False
  if fault=='missingSide':x['sides']={}
  for i in range(10):x['frame']=i+1;out=p.update(x,s,1_000_000_000+i*1_000_000_000)
  assert not out.get('request_direction'),fault


def test_stale_repeated_model_frame_cannot_satisfy_confirmation():
 p=CPOvertake();s=CPSettings(enabled=True,overtake_mode=2)
 for i in range(10):out=p.update(observation(),s,1_000_000_000+i*100_000_000)
 assert not out.get('request_direction')


def test_lost_authority_discards_original_lane_memory():
 p=CPOvertake();p.net_changes=1;p.memory_since=1_000_000_000
 x=observation();x['authority']=False
 p.update(x,CPSettings(enabled=True,overtake_mode=2),2_000_000_000)
 assert p.net_changes==0


def test_return_confirmation_requires_continuous_speed_advantage():
 p=CPOvertake();p.net_changes=1;p.memory_since=1_000_000_000;p.phase='passing'
 s=CPSettings(enabled=True,overtake_mode=2)
 x=observation(1);x['passed_confirmed']=True
 p.update(x,s,2_000_000_000)
 x['frame']=2;x['return_advantage_kph']=2
 p.update(x,s,3_000_000_000)
 x['frame']=3;x['return_advantage_kph']=10
 out=p.update(x,s,4_100_000_000)
 assert not out.get('request_direction')


def test_road_or_turn_change_cancels_already_queued_pass():
 for fault in ('turn','road'):
  p=CPOvertake();s=CPSettings(enabled=True,overtake_mode=2)
  for i in range(3):p.update(observation(i+1),s,1_000_000_000+i*100_000_000)
  assert p.update(observation(4),s,4_000_000_000)['request_direction']=='left'
  x=observation(5)
  if fault=='turn':x['nav_distance_m']=500
  if fault=='road':x['road_type']=1
  assert not p.update(x,s,4_100_000_000).get('request_direction'),fault


def test_lead_under_fifty_kph_never_triggers_cp_passing():
 p=CPOvertake();s=CPSettings(enabled=True,overtake_mode=2)
 for i in range(10):
  x=observation(i+1);x['lead']['speed_mps']=10.
  out=p.update(x,s,1_000_000_000+i*1_000_000_000)
  assert not out.get('request_direction')


def test_changed_side_restarts_three_new_frame_confirmation():
 p=CPOvertake();s=CPSettings(enabled=True,overtake_mode=2)
 for i in (1,2):p.update(observation(i),s,1_000_000_000+i*100_000_000)
 x=observation(3);x['sides']['left']['blindspot']=True
 out=p.update(x,s,1_300_000_000)
 assert out['state']=='observing'


def test_conservative_cp_style_needs_fifteen_kph_speed_difference():
 p=CPOvertake();s=CPSettings(enabled=True,overtake_mode=2,driving_style=0)
 for i in range(10):
  x=observation(i+1);x['lead']['speed_mps']=21.5
  out=p.update(x,s,1_000_000_000+i*1_000_000_000)
  assert not out.get('request_direction')


def test_cp_tbt_bias_blocks_opposing_pass_with_insufficient_advantage():
 p=CPOvertake();s=CPSettings(enabled=True,overtake_mode=2)
 for i in range(10):
  x=observation(i+1);x.update(nav_distance_m=2100,nav_direction='right');x['lead']['speed_mps']=20.
  out=p.update(x,s,1_000_000_000+i*1_000_000_000)
  assert not out.get('request_direction')


def test_source_dropout_cannot_rearm_a_cancelled_same_route_speed_increase():
 import time
 from cp_nav.engine import CPEngine
 from .test_native_contract import snapshot,car,control
 now=time.monotonic_ns();settings=CPSettings(enabled=True,speed_raise=True)
 source=snapshot(now,turn=51,distance=5000,limit=100);engine=CPEngine(settings);speed=CPSpeedPolicy()
 def update(connected,stamp):
  source['connected']=connected
  state=engine.update(source,car(),control(),now_ns=stamp,vehicle_fresh=True)
  return speed.update(state,v_cruise=60/3.6,v_ego=60/3.6,long_active=True,
    override=False,settings=settings,now_ns=stamp)
 assert update(True,now)>60/3.6
 assert update(False,now+100_000_000) is None
 assert update(True,now+200_000_000) is None
