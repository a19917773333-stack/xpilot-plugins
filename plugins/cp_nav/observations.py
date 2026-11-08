"""Read actual host observations. Unknown CP side tracks remain unavailable.
Navigation uses factory ALC/BSM and SP's ordinary gates. Automatic passing
additionally needs side-lead/return evidence; BSM false alone cannot supply it.
"""
import math
from .topology import from_model
from .oem import ALC_STALE_NS

_LANE_STATES = {0: 'off', 1: 'preLaneChange', 2: 'laneChangeStarting', 3: 'laneChangeFinishing'}
_LANE_DIRECTIONS = {0: 'none', 1: 'left', 2: 'right'}


def _enum_name(value, names, default):
  raw = getattr(value, 'raw', value)
  try:
    mapped = names.get(int(raw))
  except (TypeError, ValueError):
    mapped = None
  if mapped is not None:
    return mapped
  name = getattr(value, 'name', None)
  text = str(name if isinstance(name, str) else raw).split('.')[-1]
  normalized = ''.join(char for char in text.lower() if char.isalnum())
  for candidate in names.values():
    if normalized == candidate.lower():
      return candidate
  return default


def build(model,model_ns,cs,cc,*,now_ns,vehicle_fresh,oem,curvature,snapshot):
  topology=from_model(model,now_ns,model_ns)
  fresh=bool(vehicle_fresh and topology['valid'])
  alc=bool(oem.get('alcFresh') is True and 0<=now_ns-oem.get('alcStampNs',0)<=ALC_STALE_NS)
  navigation={};sides={}
  for side in ('left','right'):
    bsm=getattr(cs,side+'Blindspot',None)
    available=bool(fresh and alc and type(bsm) is bool)
    crossing=bool(available and oem.get(side+'CrossingAllowed') is True
      and not oem.get(side+'ExplicitBlock',False) and not oem.get('solidLine',False))
    navigation[side]=dict(observed=available,neighbor=topology[side+'NeighborExists'],
      allowed=crossing and bsm is False,blindspot=bsm,crossable=crossing,
      gap_clear=bool(available and bsm is False),clearance_policy='factory_BSM_ALC_and_SP')
    # Standard SP modelV2 has no native CP leadLeft/leadRight contract. Do not
    # serialize padding/absence as an independently observed clear side track.
    sides[side]=dict(navigation[side],gap_clear=False)
  items=snapshot.get('items',{});guide=(items.get('guidance_current') or {}).get('value') or {}
  lane=(items.get('lane_current') or {}).get('value') or {}
  category=lane.get('road_category');road_type=0 if category==1 else None
  meta=getattr(model,'meta',None);lead={}
  try:
    raw=model.leadsV3[0];distance=float(raw.x[0]);speed=float(raw.v[0])
    if raw.prob>=.5 and all(math.isfinite(v) for v in (distance,speed)):
      lead=dict(observed=True,distance_m=distance,speed_mps=speed)
  except (AttributeError,IndexError,TypeError,ValueError):pass
  return dict(fresh=fresh,authority=bool(vehicle_fresh and getattr(cc,'latActive',False)),
    navigation_sides=navigation,sides=sides,topology=topology,
    model_state=_enum_name(getattr(meta,'laneChangeState','unknown'),_LANE_STATES,'unknown'),
    model_direction=_enum_name(getattr(meta,'laneChangeDirection','none'),_LANE_DIRECTIONS,'none'),
    frame=topology['frameId'],speed_mps=getattr(cs,'vEgo',None),
    steering_deg=getattr(cs,'steeringAngleDeg',None),curvature=curvature,
    nav_distance_m=guide.get('distance_m'),road_type=road_type,lead=lead,
    passed_confirmed=False,return_advantage_kph=None,passing_source='unavailable_standard_host')
