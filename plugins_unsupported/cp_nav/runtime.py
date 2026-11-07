"""Independent CP data-to-decision lifecycle, with no live vehicle IO."""
from dataclasses import replace
from .engine import CPEngine
from .execution import CPExecution
from .overtake import CPOvertake
from .observations import build
from .blocker import LaneChangeBlocker


class CPRuntime:
  def __init__(self,settings):
    self.settings=settings;self.engine=CPEngine(settings);self.execution=CPExecution()
    self.passing=CPOvertake();self.route=None;self.blocker=LaneChangeBlocker()

  def tick(self,snapshot,cs,cc,model,model_ns,*,now_ns,vehicle_fresh,owner,oem,curvature):
    settings=self.settings if owner else replace(self.settings,enabled=False)
    self.engine.settings=settings
    state=self.engine.update(snapshot,cs,cc,now_ns=now_ns,vehicle_fresh=vehicle_fresh,model=model)
    state['event']=snapshot.get('event',0)
    obs=build(model,model_ns,cs,cc,now_ns=now_ns,vehicle_fresh=vehicle_fresh,
              oem=oem,curvature=curvature,snapshot=snapshot)
    if not settings.enabled:self.blocker.reset()
    left_blocked,right_blocked,_=self.blocker.update(oem,obs['topology'])
    for side,blocked in (('left',left_blocked),('right',right_blocked)):
      if blocked:
        obs['navigation_sides'][side]['allowed']=False
        obs['sides'][side]['allowed']=False
    obs['authority']=state.get('control_allowed') is True
    key=tuple(state.get('route_key') or ())
    if key!=self.route:self.passing=CPOvertake();self.route=key
    # Driver lamps must not trigger a fresh automatic passing proposal.
    if self.passing.pending is None and (getattr(cs,'leftBlinker',False) or getattr(cs,'rightBlinker',False)):
      obs['authority']=False
    passing=self.passing.update(obs,settings,now_ns)
    state.update(passingMode=settings.overtake_mode,passing=passing,passingSource=obs['passing_source'],overtakingAvailable=False)
    nav_obs=dict(obs,sides=obs['navigation_sides'])
    intent=self.execution.update(state,nav_obs,passing,settings,now_ns)
    return dict(state=state,intent=intent)
