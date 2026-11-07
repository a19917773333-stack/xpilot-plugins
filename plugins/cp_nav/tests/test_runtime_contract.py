"""Failures first: native Carrot decisions never reach independent CP outputs;
closed master or lost route ownership still requests a lamp; plain SP model
missing CP side tracks is mislabeled as a verified passing gap.
"""
import time
from types import SimpleNamespace as N
from cp_nav.runtime import CPRuntime
from cp_nav.observations import build
from cp_nav.settings import CPSettings
from .test_native_contract import snapshot,car,control


def model():
 return N(frameId=1,laneLines=[N(x=[0.,30.],y=[y,y]) for y in (-5.4,-1.8,1.8,5.4)],
  laneLineProbs=[.9]*4,roadEdges=[],roadEdgeStds=[],leadsV3=[],
  meta=N(laneChangeState='off',laneChangeDirection='none'))


def test_runtime_emits_native_turn_preparation_without_crossing():
 now=time.monotonic_ns();m=model();s=snapshot(now)
 out=CPRuntime(CPSettings(enabled=True)).tick(s,car(),control(),m,now,now_ns=now,
      vehicle_fresh=True,owner=True,oem={},curvature=.001)
 assert out['state']['valid'] and out['intent']['signalRequested']
 assert out['intent']['turnOnly'] and not out['intent']['laneChangeAllowed']
 assert out['state']['carrot']['xTurnInfo']==1


def test_lost_owner_source_or_master_withdraws_outputs():
 now=time.monotonic_ns()
 for fault in ('owner','source','master','vehicle'):
  cfg=CPSettings(enabled=fault!='master');r=CPRuntime(cfg);s=snapshot(now)
  if fault=='source':s['connected']=False
  out=r.tick(s,car(),control(),model(),now,now_ns=now,vehicle_fresh=fault!='vehicle',
    owner=fault!='owner',oem={},curvature=.001)
  assert not out['state']['valid'] and not out['intent']['signalRequested'],fault


def test_standard_sp_model_does_not_invent_cp_side_track_clearance():
 now=time.monotonic_ns();cs=car();cs.steeringAngleDeg=0.
 oem=dict(alcFresh=True,alcStampNs=now,leftCrossingAllowed=True,rightCrossingAllowed=True)
 x=build(model(),now,cs,control(),now_ns=now,vehicle_fresh=True,oem=oem,curvature=.001,snapshot=snapshot(now))
 assert x['navigation_sides']['left']['crossable'] is True
 assert x['sides']['left']['gap_clear'] is False
 assert not x['passed_confirmed'] and x['passing_source']=='unavailable_standard_host'


def test_expired_oem_or_missing_bsm_never_grants_crossing():
 now=time.monotonic_ns()
 for fault in ('oem','bsm'):
  cs=car();oem=dict(alcFresh=True,alcStampNs=now,leftCrossingAllowed=True)
  if fault=='oem':oem['alcStampNs']=now-5_000_000_000
  if fault=='bsm':del cs.leftBlindspot
  x=build(model(),now,cs,control(),now_ns=now,vehicle_fresh=True,oem=oem,curvature=.001,snapshot=snapshot(now))
  assert not x['navigation_sides']['left']['allowed'],fault


def test_confirmed_oem_block_is_not_released_on_the_first_clear_sample():
 now=time.monotonic_ns();r=CPRuntime(CPSettings(enabled=True));cs=car();m=model()
 for index,blocked in enumerate((True,True,False)):
  stamp=now+index*600_000_000;m.frameId=index+1
  oem=dict(alcFresh=True,alcStampNs=stamp,rightCrossingAllowed=not blocked,
           rightExplicitBlock=blocked,leftCrossingAllowed=True)
  out=r.tick(snapshot(stamp,turn=6,distance=40),cs,control(),m,stamp,
      now_ns=stamp,vehicle_fresh=True,owner=True,oem=oem,curvature=.001)
 assert out['intent']['signalRequested']
 assert not out['intent']['laneChangeAllowed']


def test_http_park_permission_expires_even_if_the_main_loop_stalls(monkeypatch):
 from cp_nav import process
 now=[2_000_000_000];monkeypatch.setattr(process.time,'monotonic_ns',lambda:now[0])
 state=dict(verified=True,stamp=now[0])
 assert process.parked_now(state)
 now[0]+=300_000_000
 assert not process.parked_now(state)
