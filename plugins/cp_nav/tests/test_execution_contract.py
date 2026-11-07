"""Failures first: independent CP entry absent; native fork lamps are cut by a
veto; route-turn lamps start a crossing; disable/stale/driver changes leave an
owned request; one completed fork repeatedly requests the same maneuver.
No live services or vehicle are used.
"""
import time
from types import SimpleNamespace as N
from cp_nav.settings import CPSettings
from cp_nav.execution import CPExecution


def native(kind='fork left',event=1):
 return dict(valid=True,control_allowed=True,route_key=('test',1),event=event,
  carrot={'atcType':kind,'xDistToTurn':40})
def obs(clear=True,state='off',direction='none'):
 return dict(fresh=True,model_state=state,model_direction=direction,
  sides={'left':dict(observed=True,neighbor=True,allowed=clear,blindspot=False,crossable=clear,gap_clear=clear)})

def test_fork_keeps_lamp_but_does_not_cross_when_blocked():
 e=CPExecution();s=CPSettings(enabled=True);now=time.monotonic_ns()
 out=e.update(native(),obs(False),{},s,now)
 assert out['signalRequested'] and not out['laneChangeAllowed']
 out=e.update(native(),obs(True),{},s,now+600_000_000)
 assert out['signalRequested'] and out['laneChangeAllowed']

def test_route_turn_has_turn_intent_without_starting_a_lane_crossing():
 out=CPExecution().update(native('turn right'),obs(),{},CPSettings(enabled=True),time.monotonic_ns())
 assert out['signalRequested'] and out['turnOnly'] and not out['laneChangeAllowed']

def test_disable_source_or_driver_authority_retires_owned_request():
 for cause in ('master','source','authority','signals'):
  e=CPExecution();now=time.monotonic_ns();s=CPSettings(enabled=True)
  assert e.update(native(),obs(),{},s,now)['signalRequested']
  n=native()
  if cause=='source':n['valid']=False
  if cause=='authority':n['control_allowed']=False
  if cause=='master':s=CPSettings(enabled=False)
  if cause=='signals':s=CPSettings(enabled=True,signals=False)
  assert not e.update(n,obs(),{},s,now+100_000_000)['signalRequested']

def test_completed_native_fork_cannot_retrigger_until_next_maneuver():
 e=CPExecution();s=CPSettings(enabled=True);now=time.monotonic_ns()
 e.update(native(),obs(),{},s,now)
 for i,state in enumerate(('laneChangeStarting','laneChangeFinishing','off')):
  out=e.update(native(),obs(state=state,direction='left' if state!='off' else 'none'),{},s,now+(i+1)*600_000_000)
 assert not out['signalRequested']
 assert not e.update(native(),obs(),{},s,now+3_000_000_000)['signalRequested']
 assert e.update(native(event=2),obs(),{},s,now+3_100_000_000)['signalRequested']

def test_stale_model_keeps_fork_preparation_but_never_crosses():
 now=time.monotonic_ns();x=obs();x['fresh']=False
 e=CPExecution();e.update(native(),x,{},CPSettings(enabled=True),now)
 out=e.update(native(),x,{},CPSettings(enabled=True),now+600_000_000)
 assert out['signalRequested'] and not out['laneChangeAllowed']


def test_a_new_cp_passing_request_is_not_consumed_by_the_previous_pass():
 e=CPExecution();s=CPSettings(enabled=True);now=1_000_000_000
 state=native('none');passing={'request_direction':'left','request_id':1}
 assert e.update(state,obs(),passing,s,now)['signalRequested']
 for i,m in enumerate(('laneChangeStarting','laneChangeFinishing','off')):
  e.update(state,obs(state=m,direction='left' if m!='off' else 'none'),passing,s,now+(i+1)*600_000_000)
 assert not e.update(state,obs(),passing,s,now+3_000_000_000)['signalRequested']
 passing['request_id']=2
 assert e.update(state,obs(),passing,s,now+30_000_000_000)['signalRequested']
