"""Failures first: CP is only a TesNav source flag; native Carrot decisions are
not executed; CP master/settings do not isolate side effects; stale inputs or a
raised target override the driver. Native decision and vehicle actuation are
validated separately, without devices or live message publishers.
"""
import time
from types import SimpleNamespace as N
from cp_nav.engine import CPEngine
from cp_nav.settings import CPSettings


def snapshot(now,turn=12,distance=40,limit=80):
 values={'vehicle':{'lat':23.,'lon':113.,'heading_deg':90.,'speed_kph':54.,'virtual_gps':False},
  'guidance_current':{'turn_type':turn,'distance_m':distance,'road_name':'test-road'},
  'navigation_status':{'mode':'guiding','guidance_active':True,'off_route':False,'route_present':True},
  'route':{'remain_distance_m':10000,'remain_time_sec':900,'total_distance_m':12000},
  'speed':{'road_limit_kph':limit},'lane_current':{'count':3,'road_category':2,'lanes':[]}}
 return {'session_id':'test','connected':True,'generation':1,'items':{k:{'present':True,'sequence':1,'received_mono_ns':now,'source_timestamp_ms':int(time.time()*1000),'value':v} for k,v in values.items()}}


def car():return N(vEgo=15.,aEgo=0.,speedLimit=0.,steeringPressed=False,steeringTorque=0.,gasPressed=False,brakePressed=False,vCruise=80.,vCruiseCluster=80.,gearShifter='drive',leftBlinker=False,rightBlinker=False,leftBlindspot=False,rightBlindspot=False)
def control():return N(enabled=True,latActive=True,longActive=True,cruiseControl=N(override=False))


def test_original_carrot_tbt_and_speed_pipeline_runs():
 now=time.monotonic_ns();e=CPEngine(CPSettings(enabled=True,auto_turn=2))
 out=e.update(snapshot(now),car(),control(),now_ns=now,vehicle_fresh=True)
 assert out['valid'] and out['carrot']['xTurnInfo']==1
 assert out['carrot']['atcType'] in ('turn left','atc left')
 assert 0<out['carrot']['desiredSpeed']<80
 assert out['native_source']=='jixiexiaoge/carrot@3615bf4'


def test_native_speed_source_road_and_camera_are_executed():
 now=time.monotonic_ns();e=CPEngine(CPSettings(enabled=True,auto_turn=0))
 s=snapshot(now,turn=51,distance=5000)
 out=e.update(s,car(),control(),now_ns=now,vehicle_fresh=True)
 assert out['valid'] and out['carrot']['desiredSpeed']==80
 s['items']['speed']['sequence']=2;s['items']['speed']['value']['sdi']={'type':0,'distance_m':20,'speed_limit_kph':40}
 out=e.update(s,car(),control(),now_ns=now+100_000_000,vehicle_fresh=True)
 assert out['carrot']['desiredSpeed']<=80


def test_source_expiry_missing_gps_disabled_and_override_cannot_request_actuation():
 now=time.monotonic_ns()
 for fault in ('source','gps','vehicle','master','brake','gas','override'):
  e=CPEngine(CPSettings(enabled=fault!='master',auto_turn=2));s=snapshot(now);cs=car();cc=control()
  if fault=='gps':s['items']['vehicle']['present']=False
  if fault=='brake':cs.brakePressed=True
  if fault=='gas':cs.gasPressed=True
  if fault=='override':cc.cruiseControl.override=True
  out=e.update(s,cs,cc,now_ns=now+(3_000_000_000 if fault=='source' else 0),vehicle_fresh=fault!='vehicle')
  assert not out['control_allowed'],fault


def test_missing_phone_heading_does_not_become_a_confirmed_north_heading():
 now=time.monotonic_ns();s=snapshot(now);s['items']['vehicle']['value'].pop('heading_deg')
 out=CPEngine(CPSettings(enabled=True)).update(s,car(),control(),now_ns=now,vehicle_fresh=True)
 assert out['valid'] and out['carrot']['positionHeadingValid'] is False


def test_unknown_turn_does_not_become_an_automatic_speed_or_signal_request():
 now=time.monotonic_ns();s=snapshot(now,turn=9999)
 out=CPEngine(CPSettings(enabled=True)).update(s,car(),control(),now_ns=now,vehicle_fresh=True)
 assert not out['control_allowed']


def test_native_result_never_grants_park_reverse_or_steering_fault_permission():
 now=time.monotonic_ns()
 for fault in ('park','reverse','steerFaultTemporary','steerFaultPermanent'):
  cs=car()
  if fault in ('park','reverse'):cs.gearShifter=fault
  else:setattr(cs,fault,True)
  out=CPEngine(CPSettings(enabled=True)).update(snapshot(now),cs,control(),now_ns=now,vehicle_fresh=True)
  assert out['valid'] and not out['control_allowed'],fault


def test_malformed_guidance_distance_is_not_native_control_permission():
 now=time.monotonic_ns()
 for distance in (-1,float('inf'),'80',True):
  s=snapshot(now,distance=distance)
  out=CPEngine(CPSettings(enabled=True)).update(s,car(),control(),now_ns=now,vehicle_fresh=True)
  assert not out['control_allowed'],distance


def test_cp_mode_labels_match_native_signal_and_slowdown_semantics():
 import json
 from pathlib import Path
 manifest=json.loads((Path(__file__).resolve().parents[1]/'plugin.json').read_text())
 modes=next(r['choices'] for r in manifest['settings'] if r['key']=='ExtCpNavAutoTurn')
 assert dict((value,label) for label,value in modes)=={0:'Off',1:'Signals only',2:'Signals and slowdown',3:'Slowdown only'}
 now=time.monotonic_ns()
 for mode in (1,2,3):
  out=CPEngine(CPSettings(enabled=True,auto_turn=mode)).update(snapshot(now),car(),control(),now_ns=now,vehicle_fresh=True)
  assert (out['carrot']['atcType']!='none')==(mode in (1,2))
  assert (out['carrot']['desiredSpeed']<80)==(mode in (2,3))
