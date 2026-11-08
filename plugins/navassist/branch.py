"""Advisory fork corroboration. Never invent route intent or crossing permission."""
import math


class BranchMatcher:
  def __init__(self):
    self.event = None
    self.last_stamp = 0
    self.last_distance = None
    self.samples = 0
    self.travel = 0.
    self.last_side = None

  def update(self, nav, snapshot, now_ns):
    event = tuple(nav.get(k) for k in ('sessionId', 'routeRevision', 'maneuverEventId'))
    if event != self.event:
      self.__init__()
      self.event = event
    branch = snapshot['branch']
    distance, side = branch['distanceM'], branch['side']
    out = dict(state='UNAVAILABLE', distanceM=distance, side=side, controlAuthorized=False,
               event=list(event), samples=0, message='')
    if not snapshot['qualified'] or distance is None or side == 'none':
      self.samples = 0
      self.last_distance = None
      self.travel = 0.
      return out
    if not nav.get('valid') or nav.get('stale') or not nav.get('routeActive'):
      out.update(state='FORK_ONLY', message=f'Fork {side.upper()} {distance} m - route unconfirmed')
      self.samples = 0
      return out
    maneuver = nav.get('maneuver', '')
    desired = next((s for s in ('left', 'right') if maneuver in ('exit_'+s, 'ramp_'+s, 'merge_'+s)), None)
    if desired is None:
      out.update(state='PASSING_FORK', message=f'Fork {side.upper()} {distance} m - follow route')
      self.samples = 0
      return out
    route_distance = nav.get('distanceM')
    numeric = type(route_distance) in (int, float) and math.isfinite(route_distance) and route_distance >= 0
    stamp = snapshot['stampNs']
    continuous = bool(self.last_stamp and 0 < stamp-self.last_stamp <= 1_000_000_000)
    same = side == desired and numeric and abs(route_distance-distance) <= 40
    if stamp != self.last_stamp:
      if not same or not continuous or side != self.last_side or (
          self.last_distance is not None and distance > self.last_distance+10):
        self.samples, self.travel = 0, 0.
      if same:
        self.samples += 1
        if continuous and self.last_distance is not None:
          self.travel += max(0, self.last_distance-distance)
      self.last_stamp, self.last_distance, self.last_side = stamp, distance, side
    state = 'CONSISTENT' if same and self.samples >= 3 and self.travel >= 20 else 'CHECKING' if same else 'DIFFERENT_FORK'
    out.update(state=state, samples=self.samples,
      message=f'Fork {side.upper()} {distance} m - '+{
        'CONSISTENT': 'route consistent', 'CHECKING': 'checking route',
        'DIFFERENT_FORK': 'may be another fork'}[state])
    return out
