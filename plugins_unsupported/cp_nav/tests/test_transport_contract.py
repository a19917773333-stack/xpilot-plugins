"""Failures first: an independent CP listener imports optional TesNav; old source
age is renewed by arrival; an unbound/remote peer mutates global Params; native
CP settings read shape lacks values; moving/stale vehicle accepts writes.
Tests use only loopback servers and isolated in-memory settings.
"""
import http.client,json,threading,time
from contextlib import contextmanager
from cp_nav.ingress import CPStore
from cp_nav.cpserver import CPServer
from cp_nav.http import CPStatusServer
from .test_entry_contract import Params


def test_snapshot_preserves_original_age_and_route_withdrawal():
 now=[3_000_000_000];s=CPStore(clock_ms=lambda:2000,clock_ns=lambda:now[0])
 def send(name,seq,stamp,value,present=True):
  return s.accept(dict(type='item_update',protocol_version=2,session_id=s.session,manifest_revision=1,
   kind='json',name=name,stream_handle=s.handles[name],schema_version=1,sequence=seq,
   source_timestamp_ms=stamp,sent_at_ms=2000,present=present,value=value))
 send('vehicle',1,1000,{'lat':23.,'lon':113.,'virtual_gps':False})
 row=s.snapshot(connected=True)['items']['vehicle']
 assert now[0]-row['received_mono_ns']==1_000_000_000
 send('route',1,2000,{'total_distance_m':1000});send('guidance_current',1,2000,{'turn_type':13,'distance_m':80})
 send('route',2,2000,None,False)
 assert not s.snapshot(connected=True)['items'].get('guidance_current',{}).get('present')
 assert not s.snapshot(connected=False)['connected']


@contextmanager
def api():
 params=Params(ExtCpNavEnabled='1');parked=[True]
 ingress=CPServer(('127.0.0.1',0),CPStore());ingress.owner=('127.0.0.1',1);ingress.applied=True
 s=CPStatusServer(('127.0.0.1',0),ingress,params,lambda:parked[0])
 t=threading.Thread(target=s.serve_forever,daemon=True);t.start()
 try:yield s,ingress,params,parked
 finally:s.shutdown();s.server_close();ingress.server_close();t.join(2)


def request(s,path,payload=None):
 c=http.client.HTTPConnection(*s.server_address,timeout=2)
 c.request('GET' if payload is None else 'POST',path,body=None if payload is None else json.dumps(payload),
           headers={} if payload is None else {'Content-Type':'application/json'})
 r=c.getresponse();code=r.status;data=json.loads(r.read());c.close();return code,data


def test_original_cp_values_shape_and_scoped_effectful_write():
 with api() as (s,ingress,params,parked):
  code,d=request(s,'/api/params_bulk?names=AutoTurnControl,ExperimentalMode')
  assert code==200 and d['values']['AutoTurnControl']==2 and 'ExperimentalMode' in d['unsupported']
  code,d=request(s,'/api/param_set',{'name':'AutoTurnControlSpeedTurn','value':25})
  assert code==200 and d['ok'] and params.get('ExtCpNavTurnKph')=='25'
  assert 'AutoTurnControlSpeedTurn' not in params.values
  for name in ('ExperimentalMode','ExtNavAssistEnabled','ExtCpNavEnabled','TurnSpeedControlMode'):
   code,d=request(s,'/api/param_set',{'name':name,'value':1})
   assert code==422 and not d['ok']


def test_unbound_and_moving_writes_fail_without_mutating_settings():
 with api() as (s,ingress,params,parked):
  for fault in ('moving','unbound','disabled'):
   parked[0]=fault!='moving';ingress.owner=None if fault=='unbound' else ('127.0.0.1',1)
   params.put('ExtCpNavEnabled','0' if fault=='disabled' else '1')
   code,d=request(s,'/api/param_set',{'name':'AutoTurnControl','value':0})
   assert code==403 and not d['ok'],fault
   assert params.get('ExtCpNavAutoTurn')=='2'


def test_out_of_bounds_and_boolean_value_rejected_instead_of_silent_clamp():
 with api() as (s,ingress,params,parked):
  for value in (999,-1,True,'20',float('nan')):
   code,d=request(s,'/api/param_set',{'name':'AutoTurnControlSpeedTurn','value':value})
   assert code in (400,422) and not d['ok']
