"""Display-only absolute lane feedback; visible-only observations are insufficient."""
from pathlib import Path
import json
import time

POSITION_PATH = Path("/dev/shm/road_lane_position.json")
MAX_AGE_MS = 2000
REQUEST_TYPE = "lane_position_request"
MODEL_POSITION_PATH = Path('/dev/shm/phone_lane_estimate.json')


def lane_position_feedback(snapshot, *, path: Path = POSITION_PATH, now_ns: int | None = None, model_path=MODEL_POSITION_PATH) -> dict:
  unknown = {"version": 1, "valid": False, "laneIndex": None, "laneCount": None,
             "numbering": "leftToRight", "source": "commaCamera", "ageMs": 0,
             "validForMs": MAX_AGE_MS, "routeRevision": snapshot.route_revision}
  try:
    if model_path.stat().st_size <= 4096 and json.loads(model_path.read_text()).get('enabled') is True:
      model=lane_model_feedback(snapshot,path=model_path,now_ns=now_ns)
      return dict(unknown,valid=model['valid'],laneIndex=model['laneNumber'],laneCount=model['laneCount'],
        source='cpPhoneVision',scope='visibleCorridor',absoluteConfirmed=False,reason='modelEstimate',
        ageMs=model['ageMs'],validForMs=model['validForMs'])
  except (OSError,ValueError,TypeError,AttributeError):
    pass
  try:
    if path.stat().st_size > 4096:
      return unknown
    d = json.loads(path.read_text())
    current = time.monotonic_ns() if now_ns is None else now_ns
    captured = d.get("capture_mono_ns")
    index, count = d.get("lane_index"), d.get("lane_count")
    if (type(captured) is not int or not 0 <= current - captured < MAX_AGE_MS * 1_000_000 or
        type(d.get("version")) is not int or d["version"] != 1 or d.get("valid") is not True or
        d.get("absolute_confirmed") is not True or d.get("numbering") != "leftToRight" or
        d.get("nav_session_id") != snapshot.session_id or
        type(d.get("route_revision")) is not int or d["route_revision"] != snapshot.route_revision or
        type(d.get("stable_samples")) is not int or d["stable_samples"] < 3 or
        type(index) is not int or not 1 <= index <= 12 or
        (count is not None and (type(count) is not int or not index <= count <= 12))):
      return unknown
    return unknown | {"valid": True, "laneIndex": index, "laneCount": count,
                      "ageMs": (current - captured + 999_999) // 1_000_000}
  except (OSError, ValueError, TypeError, AttributeError):
    return unknown


def lane_model_feedback(snapshot, *, path=MODEL_POSITION_PATH, now_ns=None):
  """Opt-in model feedback; never relabel a visible corridor as absolute geometry."""
  unknown = dict(version=1,valid=False,laneNumber=None,laneCount=None,source='cpPhoneVision',
    scope='visibleCorridor',ageMs=0,validForMs=800,routeRevision=snapshot.route_revision)
  try:
    if path.stat().st_size>4096:return unknown
    d=json.loads(path.read_text())
    if d.get('enabled') is False:return None
    now=time.monotonic_ns() if now_ns is None else now_ns
    stamp=d.get('captureMonoNs');index,count=d.get('laneNumber'),d.get('laneCount')
    if (type(stamp) is not int or not 0<=now-stamp<800_000_000 or d.get('valid') is not True
        or type(d.get('version')) is not int or d['version']!=1
        or d.get('source')!='cpPhoneVision' or d.get('scope')!='visibleCorridor'
        or d.get('controlEligible') is not False or d.get('navSessionId')!=snapshot.session_id
        or type(d.get('routeRevision')) is not int or d['routeRevision']!=snapshot.route_revision
        or type(index) is not int or type(count) is not int or not 1<=index<=count<=5):return unknown
    return dict(unknown,valid=True,laneNumber=index,laneCount=count,ageMs=(now-stamp+999_999)//1_000_000)
  except (OSError,ValueError,TypeError,AttributeError):return unknown
