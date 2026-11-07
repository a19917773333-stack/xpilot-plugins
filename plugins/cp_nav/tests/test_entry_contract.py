"""Failures before implementation: CP is not a discoverable independent plugin;
CP and TesNav both own the lamps; old Params bypass bounds; a missing CP message
falls through to automatic SP while its lamp remains on; turn-only starts a
crossing; disabled CP keeps a target, a lamp or a chime. No devices involved.
"""
import json
from pathlib import Path
from types import SimpleNamespace as N
from openpilot.tesla import manifest as mf
from cp_nav.settings import read

ROOT=Path(__file__).resolve().parents[1]

class Params:
 def __init__(self,**values):
  self.defaults={k:v.get('default') for k,v in json.loads((ROOT/'plugin.json').read_text())['params'].items()}
  self.values=values
 def get(self,key,**kwargs):return self.values.get(key,self.defaults.get(key))
 def get_bool(self,key):return self.get(key) in ('1',b'1',True)
 def put(self,key,value):self.values[key]=value

class Messages:
 def __init__(self,**values):self.values=values
 def fresh(self,kind):return {'cp_nav':self.values.get(kind,{})}


def test_independent_entry_owned_keys_and_exclusive_navigation_claims():
 m=mf.parse(ROOT/'plugin.json');nav=mf.parse(ROOT.parent/'navassist/plugin.json')
 assert m.enable_param=='ExtCpNavEnabled' and m.params[m.enable_param]['default']=='0'
 assert m.requires['rule_abi']==nav.requires['rule_abi']==2
 assert m.rules==nav.rules
 assert set(m.params).isdisjoint(nav.params)
 assert mf.conflicting(m.id,[(m.id,m.priority,m.claims),(nav.id,nav.priority,nav.claims)])==['navassist']
 assert mf.compatible(m,mf.HOST_CAPS)[0]
 from cp_nav.plugin import CPNav
 assert issubclass(CPNav,__import__('openpilot.tesla.plugin',fromlist=['Plugin']).Plugin)


def test_setting_bounds_are_enforced_without_changing_global_params():
 s=read(Params(ExtCpNavEnabled='1',ExtCpNavTurnKph='999',ExtCpNavLaneDelayMs='-50',ExtCpNavOvertakeMode='bad'))
 assert s.enabled and s.turn_kph==40 and s.lane_delay_ms==500 and s.overtake_mode==0


def test_owned_fork_waits_then_stale_lamp_never_falls_through_to_auto():
 from cp_nav.policy import CPLanePolicy
 p=CPLanePolicy(Params(ExtCpNavEnabled='1'));msgs=Messages(**{'lanes.intent':dict(valid=True,signalRequested=True,direction='left',turnOnly=False,laneChangeAllowed=False)})
 p._msgs=msgs;cs=N(leftBlinker=True,rightBlinker=False)
 assert not p.allow(cs,'left',True)
 assert not p.constraints(cs,'left').allow_start
 msgs.values['lanes.intent']['laneChangeAllowed']=True
 assert p.allow(cs,'left',True)
 assert not p.allow(cs,'left',False)  # does not override SP automatic mode
 msgs.values.clear()
 assert not p.allow(cs,'left',True)
 assert not p.constraints(cs,'left').allow_start
 cs.leftBlinker=False;p.constraints(cs,'none')
 assert p.allow(cs,'left',True)  # unrelated later manual lamp remains stock


def test_turn_only_produces_turn_intent_and_disabled_policy_retires_it():
 from cp_nav.policy import CPLanePolicy
 params=Params(ExtCpNavEnabled='1');p=CPLanePolicy(params)
 p._msgs=Messages(**{'lanes.intent':dict(valid=True,signalRequested=True,direction='right',turnOnly=True,laneChangeAllowed=False)})
 cs=N(leftBlinker=False,rightBlinker=True)
 assert p.constraints(cs,'right').turn_only
 assert not p.allow(cs,'right',True)
 params.put('ExtCpNavEnabled','0')
 assert not p.allow(cs,'right',True)
 assert not p.constraints(cs,'right').turn_only


def test_disabled_cp_target_cannot_consume_a_valid_other_process_result():
 from cp_nav.target import CPTarget
 p=CPTarget(None,Params(ExtCpNavEnabled='0'))
 p._msgs=Messages(**{'cp.state':dict(valid=True,control_allowed=True,raw_limit_kph=100,route_key=['test',1],carrot={'desiredSpeed':100,'desiredSource':'road'})})
 sm={'carState':N(gasPressed=False,brakePressed=False),'carControl':N(enabled=True,longActive=True,cruiseControl=N(override=False))}
 assert p.update(sm,20.,25.) is None


def test_live_lane_setting_disable_cannot_use_an_old_ready_intent():
 from cp_nav.policy import CPLanePolicy
 params=Params(ExtCpNavEnabled='1');p=CPLanePolicy(params)
 p._msgs=Messages(**{'lanes.intent':dict(valid=True,signalRequested=True,direction='left',turnOnly=False,laneChangeAllowed=True)})
 cs=N(leftBlinker=True,rightBlinker=False)
 assert p.allow(cs,'left',True)
 params.put('ExtCpNavLaneChanges','0')
 assert not p.allow(cs,'left',True)
 assert not p.constraints(cs,'left').allow_continue
