"""Read-only optional host marking codes. Missing SP fields are never dashed."""
from pathlib import Path
import json
import time

PATH = Path('/dev/shm/nav_vehicle_feedback.json')
MAX_AGE_NS = 500_000_000


def decode(code):
  out = dict(code=None,type='unknown',color='unknown')
  if type(code) is not int or code not in (-1,0,1,10,11,20,21,30,31):return out
  if code == -1:return dict(out,code=code,type='unreported')
  return dict(code=code,type='dashed' if code%10==0 else 'solid',
              color={1:'white',2:'yellow',3:'blue'}.get(code//10,'unknown'))


def observe(car, stamp, now, *, enabled, vehicle_fresh):
  supported=hasattr(car,'leftLaneLine') or hasattr(car,'rightLaneLine')
  fresh=bool(enabled and vehicle_fresh and type(stamp) is int and 0<stamp<=now and now-stamp<MAX_AGE_NS)
  return dict(version=1,source='carState',supported=supported,
    left=decode(getattr(car,'leftLaneLine',None) if fresh else None),
    right=decode(getattr(car,'rightLaneLine',None) if fresh else None))


def feedback(snapshot, *, path=PATH, now_ns=None):
  try:
    if path.stat().st_size>8192:return {}
    d=json.loads(path.read_text());now=time.monotonic_ns() if now_ns is None else now_ns
    stamp=d.get('captureMonoNs')
    if (d.get('enabled') is not True or type(stamp) is not int or not 0<=now-stamp<MAX_AGE_NS
        or d.get('sessionId')!=snapshot.session_id or d.get('routeRevision')!=snapshot.route_revision):return {}
    lines=d['lines']
    result={'vehicleLines':dict(version=1,source='carState',supported=lines['supported'],
      leftCode=lines['left']['code'],rightCode=lines['right']['code'],
      ageMs=(now-stamp+999_999)//1_000_000,validForMs=500)}
    intent=d.get('intent',{})
    if isinstance(intent.get('reason'),str):
      result['laneDecision']=dict(sessionId=snapshot.session_id,reason=intent['reason'],
        signalRequested=intent.get('signalRequested') is True,direction=intent.get('direction','none'))
    lamp=d.get('lamp',{})
    if isinstance(lamp.get('reason'),str):result['lampStatus']=lamp['reason']
    return result
  except (OSError,ValueError,TypeError,AttributeError,KeyError):return {}
