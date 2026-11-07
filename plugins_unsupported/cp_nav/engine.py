"""Execute original Carrot navigation policy against qualified CP observations.
Native output is internal data; vehicle hooks separately enforce actuation gates.
"""
import math
from types import SimpleNamespace as N
from .native import NativeCarrot
from .native.payload import build_carrot_navi_payload
from .native.common import Memory, OutputSink
from .native.gps import GPSSources
from .native.constants import nav_type_mapping
from .settings import CPSettings, NativeParams


class QualifiedGPS(GPSSources):
  heading_observed=False
  def put(self,source,latitude,longitude,heading,speed,stamp):
    if source=='external_navi' and not self.heading_observed:heading=None
    return super().put(source,latitude,longitude,heading,speed,stamp)


class CarStateView:
  def __init__(self, cs):self.cs=cs
  def __getattr__(self, name):
    if name=='vehicleGps':return N(valid=False)  # no claimed Tesla CAN positioning
    if name=='speedLimit' and not hasattr(self.cs,name):return 0.
    if name=='schoolZoneActive' and not hasattr(self.cs,name):return False  # unavailable optional OEM source
    return getattr(self.cs,name)


class CPEngine:
  def __init__(self, settings: CPSettings):
    self.settings=settings;self.key=None;self.distance=0.;self.last_ns=None
    self.memory=Memory();self.params=NativeParams(settings);self.core=NativeCarrot(self.params,self.memory)

  def update(self,snapshot,cs,cc,*,now_ns,vehicle_fresh,model=None):
    items=snapshot.get('items',{})
    def fresh(name):
      row=items.get(name,{})
      return bool(row.get('present') and 0<=now_ns-row.get('received_mono_ns',0)<=1_500_000_000)
    v=items.get('vehicle',{}).get('value') or {};status=items.get('navigation_status',{}).get('value') or {}
    qualified=(snapshot.get('connected') and all(fresh(n) for n in ('vehicle','guidance_current','navigation_status','route'))
      and v.get('virtual_gps') is False and status.get('mode')=='guiding' and status.get('guidance_active') is True
      and status.get('route_present') is True and status.get('off_route',False) is False)
    guide=items.get('guidance_current',{}).get('value') or {}
    turn=guide.get('turn_type');distance=guide.get('distance_m')
    qualified=qualified and type(distance) in (int,float) and math.isfinite(distance) and 0<=distance<=100000
    qualified=qualified and type(turn) is int and turn in nav_type_mapping
    coords=(v.get('lat'),v.get('lon'))
    qualified=bool(qualified and all(type(n) in (int,float) and math.isfinite(n) for n in coords)
      and -85.05112878<=coords[0]<=85.05112878 and -180<=coords[1]<=180 and coords!=(0,0))
    out=dict(valid=False,control_allowed=False,route_key=(snapshot.get('session_id'),snapshot.get('generation')),carrot={},native_source='jixiexiaoge/carrot@3615bf4',reason='sourceUnavailable')
    if not self.settings.enabled or not qualified or not vehicle_fresh:
      self.key=None;return out
    key=(snapshot.get('session_id'),snapshot.get('generation'))
    if key!=self.key:
      self.memory=Memory();self.core=NativeCarrot(self.params,self.memory);self.key=key
    self.params.settings=self.settings
    if not isinstance(getattr(self.core,'gps_sources',None),QualifiedGPS):self.core.gps_sources=QualifiedGPS()
    heading=v.get('heading_deg')
    self.core.gps_sources.heading_observed=bool(type(heading) in (int,float) and math.isfinite(heading) and 0<=heading<360)
    if self.last_ns is not None and 0<now_ns-self.last_ns<=250_000_000:
      self.distance+=max(0.,cs.vEgo)*(now_ns-self.last_ns)/1e9
    self.last_ns=now_ns
    payload=build_carrot_navi_payload(snapshot,publish_mono_ns=now_ns)
    sm={'carState':CarStateView(cs),'selfdriveState':N(distanceTraveled=self.distance),
        'carrotNavi':payload,'gpsLocationExternal':N(hasFix=False),'carControl':cc}
    class Services(dict):pass
    services=Services(sm);services.alive={k:k!='gpsLocationExternal' for k in sm}
    services.valid=dict(services.alive);services.updated={k:True for k in sm};services.recv_time={k:now_ns/1e9 for k in sm}
    sink=OutputSink()
    try:self.core.update_navi('cp-source',services,sink,250,[],[],250,'gpsLocationExternal')
    except (AttributeError,KeyError,TypeError,ValueError,RuntimeError,ZeroDivisionError) as error:
      out['reason']='nativeError:'+type(error).__name__;return out
    native=sink.messages.get('carrotMan',{})
    allowed=bool(getattr(cc,'latActive',False) and str(getattr(cs,'gearShifter','unknown'))=='drive'
      and not (getattr(cs,'steerFaultTemporary',False) or getattr(cs,'steerFaultPermanent',False)
      or getattr(cs,'brakePressed',True)
      or getattr(cs,'gasPressed',True) or getattr(cs,'steeringPressed',True) or cc.cruiseControl.override))
    road=(items.get('speed',{}).get('value') or {}).get('road_limit_kph') if fresh('speed') else None
    out.update(valid=True,control_allowed=allowed,carrot=native,raw_limit_kph=road,
               route_key=key,reason='ready' if allowed else 'driverOrAuthority')
    return out
