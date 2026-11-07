"""Carrot speed results -> bounded X-Pilot cruise targets.
Raises are explicit, source-bound and cancelled by driver setpoint changes.
"""
import math


class CPSpeedPolicy:
  def __init__(self):
    self.key=None;self.anchor=None;self.target=None;self.last_step=0;self.blocked=False

  def update(self,state,*,v_cruise,v_ego,long_active,override,settings,now_ns):
    key=tuple(state.get('route_key') or ('',0))
    if key!=self.key:
      self.key=key;self.anchor=None;self.target=None;self.last_step=0;self.blocked=False
    valid=(settings.enabled and settings.speed_control and long_active and not override
           and state.get('valid') is True and state.get('control_allowed') is True
           and all(math.isfinite(v) and v>=0 for v in (v_cruise,v_ego)))
    if not valid:
      if self.anchor is not None:self.blocked=True
      return None
    raw=state.get('raw_limit_kph');native=state.get('carrot') or {}
    speed=native.get('desiredSpeed')
    if type(speed) not in (int,float) or not math.isfinite(speed) or speed<=0:return None
    goal=min(speed,settings.max_kph)/3.6
    if goal<v_cruise:return max(0.,goal)
    if not settings.speed_raise or self.blocked or native.get('desiredSource')!='road':return None
    if type(raw) is not int or not 10<=raw<=200:return None
    goal=min(goal,(raw+settings.road_offset_kph)/3.6,settings.max_kph/3.6)
    if self.anchor is not None and abs(v_cruise-self.anchor)>.3:
      self.blocked=True;return None
    if self.anchor is None:
      self.anchor=v_cruise;self.target=v_cruise
    if self.last_step==0 or now_ns-self.last_step>=max(1,settings.raise_interval_s)*1_000_000_000:
      self.target=min(goal,self.target+max(1,settings.raise_step_kph)/3.6);self.last_step=now_ns
    return max(v_cruise,min(self.target,goal))
