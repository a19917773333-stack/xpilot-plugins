"""Presentation only: preserve absence/staleness and never infer a current lane."""
import math
from .display import guidance_visible


def signal_authority(primary, lateral, alternative_experience):
  # Same native authority domain as the paired navassist safety plugin.
  return bool(primary or ((int(alternative_experience) & (1 << 10)) and lateral))


def hud_rect(bottom):
  x,y,w,h=bottom
  return x+16,y+16,max(0,w-32),max(0,h-32)


MANEUVERS=frozenset(('straight','turn_left','turn_right','sharp_left','sharp_right',
  'u_turn_left','u_turn_right','merge_left','merge_right','exit_left','exit_right',
  'ramp_left','ramp_right','slight_left','slight_right'))


def floating_layout(bottom):
  x,y,w,h=hud_rect(bottom)
  side=min(200,h-72)
  return dict(arrow=(x+16,y+46,side,side),route=(x+w*.76,y+12,w*.23,h-24))


def route_nodes(nav, active):
  nodes=[]
  if active:
    for maneuver,distance in ((nav.get('maneuver'),nav.get('distanceM')),
                              (nav.get('nextManeuver'),nav.get('nextDistanceM'))):
      if (maneuver in MANEUVERS and type(distance) in (int,float)
          and math.isfinite(distance) and distance>=0):
        nodes.append((maneuver,float(distance)))
      elif not nodes:
        break  # Never relabel a next-only instruction as the current maneuver.
  return tuple(nodes)


def present_hud(nav,intent,topology,*,car=None,authority=None):
  active=guidance_visible(nav)
  stale=bool(nav.get('routeActive') and nav.get('stale',True))
  distance=nav.get('distanceM')
  distance=distance if active and type(distance) in (int,float) and math.isfinite(distance) and distance>=0 else None
  count=nav.get('laneTotalCount',0)
  count=count if type(count) is int and 1<=count<=16 and active else 0
  recommended=tuple(sorted({r['index'] for r in nav.get('lanes',[]) if isinstance(r,dict)
    and r.get('recommended') and type(r.get('index')) is int and 0<=r['index']<count})) if count else ()
  ego=topology.get('absoluteEgoIndex')
  ego=ego if nav.get('valid') and topology.get('valid') and type(ego) is int and 0<=ego<count else None
  status='Navigation linked' if active else 'Navigation data delayed' if stale else 'Waiting for phone navigation'
  tone='cyan' if active and nav.get('valid') else 'amber' if active or stale else 'dim'
  if active and not nav.get('valid'):status='Guidance only'
  if intent.get('valid') and intent.get('signalRequested'):
    side=intent.get('direction')
    same=bool(car and side in ('left','right') and car.get(side+'Blinker') and not car.get(('right' if side=='left' else 'left')+'Blinker'))
    if same:status,tone='Vehicle signal confirmed','cyan'
    elif authority is False:status,tone='Auto signal permission unavailable','amber'
    else:status,tone='Waiting for vehicle signal','amber'
  mlane=topology.get('modelLaneIndex')
  mcount=topology.get('modelLaneCount')
  mvalid=bool(topology.get('modelLaneValid')) and type(mlane) is int and type(mcount) is int and 1<=mlane<=mcount
  model_lane=f'Ego lane {mlane} of {mcount}' if mvalid else 'Ego lane --'
  if mvalid and topology.get('modelLaneChanging'):
    model_lane+=' (changing)'
  phone_lane=nav.get('phoneLaneEvidence', {})
  phone_lane_message=''
  if active and phone_lane.get('valid'):
    label='Vision lane estimate'
    phone_lane_message=f"{label} {phone_lane['laneNumber']}/{phone_lane['laneCount']}"
  return dict(phone_lane_message=phone_lane_message,active=active,distance=distance,maneuver=nav.get('maneuver') if active else None,
    status=status,tone=tone,count=count,recommended=recommended,ego=ego,
    model_lane=model_lane,model_lane_valid=mvalid,model_ego=(mlane-1) if mvalid else None,
    lane_status='Lane position confirmed' if ego is not None else 'Lane position pending',
    route_nodes=route_nodes(nav,active),
    branch_message=nav.get('branchEvidence', {}).get('message', '') if active else '')
