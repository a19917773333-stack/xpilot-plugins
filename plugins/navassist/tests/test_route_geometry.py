"""Before implementation: route geometry must not enter high-rate snapshots or
control. Reject mixed sessions/revisions, duplicates/conflicts, corrupt/oversize
chunks, invalid coordinates and stale context; bound assembly memory/time. Publish
only complete WGS84 routes, clear on end/disable, recover after consumer restart.
"""
import base64,hashlib,json
from types import SimpleNamespace as N
import pytest
from navassist.route_geometry import RouteGeometryCache, RouteGeometryPublisher, gcj02_to_wgs84

NOW=1_000_000_000

def wait_route(c,ctx=None,now=NOW):
 import time
 ctx=ctx or context()
 deadline=time.monotonic()+3
 while time.monotonic()<deadline:
  g=c.current(ctx,now)
  if g is not None:return g
  time.sleep(.001)
 raise AssertionError('route conversion did not complete')


def context(**changes):
 s=N(session_id='route-s',route_revision=7,navigation_mode='realtime',coordinate_system='gcj02')
 for k,v in changes.items():setattr(s,k,v)
 return N(snapshot=s,is_stale=lambda now:now>NOW+2_000_000_000)


def payload(**changes):
 d=dict(schemaVersion=1,coordinateSystem='gcj02',pathId=42,sourcePointCount=3,
  sourcePointIndices=[0,1,2],totalDistanceMeters=130,toleranceMeters=5.,
  points=[[31.2301,121.4702],[31.2305,121.4707],[31.2301,121.4712]])
 d.update(changes);return d


def packets(data=None,size=90,**changes):
 raw=json.dumps(data or payload(),separators=(',',':'),allow_nan=False).encode()
 rid=hashlib.sha256(raw).hexdigest();parts=[raw[i:i+size] for i in range(0,len(raw),size)]
 result=[]
 for i,part in enumerate(parts):
  d=dict(messageType='route_geometry_chunk',schemaVersion=1,sessionId='route-s',routeRevision=7,
   routeId=rid,chunkIndex=i,chunkCount=len(parts),payload=base64.b64encode(part).decode())
  d.update(changes);result.append(json.dumps(d).encode())
 return result


def ready(cache=None):
 c=cache or RouteGeometryCache()
 for p in reversed(packets()):c.accept(p,context(),NOW)
 assert wait_route(c) is not None
 return c


def test_out_of_order_reassembly_is_complete_only_and_duplicate_is_idempotent():
 c=RouteGeometryCache();p=packets();c.accept(p[-1],context(),NOW)
 assert c.current(context(),NOW) is None
 for b in p[:-1]:c.accept(b,context(),NOW)
 original=wait_route(c)
 assert original.points==tuple(tuple(p) for p in payload()['points'])
 assert c.accept(p[-1],context(),NOW)['complete']
 assert c.current(context(),NOW) is original


@pytest.mark.parametrize('changes',[{'sessionId':'other'},{'routeRevision':6},{'schemaVersion':2},
 {'chunkIndex':True},{'chunkCount':65},{'chunkIndex':-1},{'routeId':'x'*64},{'payload':'@'}])
def test_invalid_chunks_never_replace_an_existing_route(changes):
 c=ready();old=c.current(context(),NOW)
 with pytest.raises(ValueError):c.accept(packets(**changes)[0],context(),NOW)
 assert c.current(context(),NOW) is old


@pytest.mark.parametrize('changes',[{'schemaVersion':True},{'schemaVersion':1.0},{'coordinateSystem':'unknown'},{'coordinateSystem':'wgs84'},
 {'points':[[91,121],[31,121]]},{'points':[[True,121],[31,121]]},
 {'sourcePointIndices':[0,0,2]},{'toleranceMeters':80},{'sourcePointCount':50001},
 {'points':[[31,121]]}])
def test_invalid_geometry_is_not_published(changes):
 c=RouteGeometryCache()
 with pytest.raises(ValueError):
  for b in packets(payload(**changes)):c.accept(b,context(),NOW)
 assert c.current(context(),NOW) is None


def test_corrupt_body_or_conflicting_revision_cannot_replace_committed_geometry():
 c=ready();old=c.current(context(),NOW)
 with pytest.raises(ValueError):c.accept(packets(payload(pathId=99))[0],context(),NOW)
 assert c.current(context(),NOW) is old
 c=RouteGeometryCache();p=packets();d=json.loads(p[-1]);d['payload']=base64.b64encode(b'bad').decode();p[-1]=json.dumps(d).encode()
 with pytest.raises(ValueError):
  for b in p:c.accept(b,context(),NOW)
 assert c.current(context(),NOW) is None


def test_transfer_cannot_refresh_snapshot_and_stale_or_new_context_clears_display():
 c=ready();ctx=context()
 assert c.current(ctx,NOW+3_000_000_000) is None
 assert c.current(ctx,NOW) is not None  # static route may resume with the same live route context
 assert c.current(context(route_revision=8),NOW) is None
 c=ready();assert c.current(context(navigation_mode='arrived'),NOW) is None
 assert c.current(context(),NOW) is None  # explicit end cannot revive the old cache


def test_pending_chunks_expire_instead_of_accumulating_across_outages():
 c=RouteGeometryCache();p=packets();c.accept(p[0],context(),NOW)
 longctx=context();longctx.is_stale=lambda now:False
 for b in p[1:]:c.accept(b,longctx,NOW+16_000_000_000)
 assert c.current(longctx,NOW+16_000_000_000) is None
 c.accept(p[0],longctx,NOW+16_100_000_000)
 assert wait_route(c,longctx,NOW+16_100_000_000) is not None


def test_hello_restores_after_receiver_restart_without_large_periodic_packets():
 c=ready();g=c.current(context(),NOW)
 hello=json.dumps(dict(messageType='route_geometry_hello',schemaVersion=1,sessionId='route-s',
  routeRevision=7,routeId=g.route_id)).encode()
 assert c.accept(hello,context(),NOW)['complete']
 assert not RouteGeometryCache().accept(hello,context(),NOW)['complete']
 with pytest.raises(ValueError):c.accept(hello,context(),NOW+3_000_000_000)


def test_conversion_is_explicit_and_does_not_offset_points_outside_gcj_region():
 lat,lon=gcj02_to_wgs84(39.915,116.404)
 assert lat==pytest.approx(39.9135957,abs=2e-6) and lon==pytest.approx(116.3977555,abs=2e-6)
 assert gcj02_to_wgs84(0.,0.)==(0.,0.)


def test_route_publisher_resends_slowly_clears_on_disable_and_isolated_errors():
 sent=[]
 class Pub:
  def send(self,name,msg):sent.append((name,msg.to_bytes()))
 p=RouteGeometryPublisher(lambda:Pub());g=ready().current(context(),NOW)
 assert p.update(g,NOW,enabled=True)['published']
 p.update(g,NOW+1_000_000_000,enabled=True);assert len(sent)==1
 p.update(g,NOW+10_000_000_000,enabled=True);assert len(sent)==2
 assert not p.update(g,NOW+11_000_000_000,enabled=False)['available'];assert len(sent)==3
 p.update(None,NOW+12_000_000_000,enabled=False);assert len(sent)==3
 def busy():raise RuntimeError('publisher busy')
 assert not RouteGeometryPublisher(busy).update(g,NOW,enabled=True)['published']


def test_udp_transfer_is_bound_to_a_live_snapshot_and_does_not_change_it():
 from navassist.tests.test_legacy_udp_receiver import run_server,stop_server,send
 from navassist.tests.test_legacy_protocol import payload as nav_payload,encode
 store,server,thread=run_server()
 try:
  port=server.server_address[1]
  # Constructor supplies a geometry cache by default, still no geometry before a live owner.
  assert send(port,packets()[0]) is None
  assert send(port,encode(nav_payload(session_id='route-s',route_revision=7)))
  current=store.current()
  for b in packets(size=1500):assert send(port,b)['accepted']
  assert store.current() is current
  assert wait_route(server.geometry,current,__import__('time').monotonic_ns()) is not None
  assert send(port,encode(nav_payload(session_id='route-s',route_revision=8,sequence=2)))
  assert server.geometry.current(store.current(),__import__('time').monotonic_ns()) is None
 finally:stop_server(server,thread)


def test_disabled_route_publisher_never_acquires_a_new_channel():
 calls=[]
 def factory():calls.append(True);raise RuntimeError('must not acquire')
 p=RouteGeometryPublisher(factory)
 assert not p.update(None,NOW,enabled=False)['available']
 assert calls==[]


def test_coordinate_system_change_invalidates_cached_route_even_without_revision_change():
 c=ready()
 assert c.current(context(coordinate_system='wgs84'),NOW) is None


def test_deeply_nested_datagram_cannot_kill_navigation_receiver():
 from navassist.tests.test_legacy_udp_receiver import run_server,stop_server,send
 from navassist.tests.test_legacy_protocol import payload as nav_payload,encode
 store,server,thread=run_server()
 try:
  port=server.server_address[1]
  assert send(port,b'['*1500+b'0'+b']'*1500) is None
  assert thread.is_alive()
  assert send(port,encode(nav_payload())) is not None
 finally:stop_server(server,thread)


def test_navigation_loop_never_waits_for_geometry_conversion_lock():
 import threading,time
 c=RouteGeometryCache();held=threading.Event();release=threading.Event()
 def ingress():
  with c.lock:
   held.set();release.wait(1)
 t=threading.Thread(target=ingress);t.start();held.wait(1)
 try:
  started=time.monotonic()
  assert c.current(context(),NOW) is None
  assert time.monotonic()-started < .1
 finally:release.set();t.join()


def test_slow_coordinate_conversion_does_not_hold_udp_snapshot_receiver(monkeypatch):
 import threading,time
 from navassist import route_geometry as module
 from navassist.tests.test_legacy_udp_receiver import run_server,stop_server,send
 from navassist.tests.test_legacy_protocol import payload as nav_payload,encode
 entered=threading.Event();release=threading.Event()
 original=module.gcj02_to_wgs84
 def slow(*point):
  entered.set();release.wait(2)
  return original(*point)
 monkeypatch.setattr(module,'gcj02_to_wgs84',slow)
 store,server,thread=run_server()
 try:
  port=server.server_address[1]
  assert send(port,encode(nav_payload(session_id='route-s',route_revision=7)))
  data=packets(size=1500)[0]
  started=time.monotonic()
  assert send(port,data) is not None
  assert time.monotonic()-started < .2
  assert entered.wait(.5)
  assert send(port,encode(nav_payload(session_id='route-s',route_revision=7,sequence=2)))
 finally:release.set();stop_server(server,thread)
