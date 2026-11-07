"""CP AutoOvertakeManager state/threshold adaptation for native X-Pilot data.
Reference navipilot91d77de: three new frames, 2.5s preparation, 20s cooldown,
30s original-lane memory, 2s clear confirmation and 8km/h return advantage.
Unlike a missing side object, a fresh explicit observation may support a request.
Vehicle execution and completion are separately observed and gated.
"""
import math


def side_clear(side):
  return bool(side and all(side.get(k) is True for k in ('observed','neighbor','allowed','gap_clear','crossable'))
              and side.get('blindspot') is False)


class CPOvertake:
  def __init__(self):
    self.phase='idle';self.counter=0;self.pending=None;self.since=0;self.last_frame=-1
    self.net_changes=0;self.memory_since=0;self.passed_since=0;self.last_action=0
    self.saw_start=self.saw_finish=False
    self.candidate=None;self.request_id=0

  def cancel(self,reason):
    self.phase='blocked';self.counter=0;self.pending=None;self.passed_since=0;self.candidate=None
    self.saw_start=self.saw_finish=False
    return dict(state=self.phase,reason=reason,request_direction=None,net_changes=self.net_changes)

  def _result(self,reason='',request=None):
    return dict(state=self.phase,reason=reason,request_direction=request,request_id=self.request_id,net_changes=self.net_changes)

  def update(self,o,settings,now_ns):
    if not settings.enabled or settings.overtake_mode==0:
      self.net_changes=0;return self.cancel('disabled')
    if o.get('authority') is not True or o.get('fresh') is not True:
      self.net_changes=0;self.memory_since=0
      return self.cancel('authorityOrStale')
    frame=o.get('frame',-1)
    if type(frame) is not int or frame<=self.last_frame:return self._result('waitingNewModelFrame')
    self.last_frame=frame
    # Original CP driving-style multipliers; all apply before a new request,
    # and a route/road transition also retires an outstanding request.
    style=settings.driving_style
    factor={0:1.5,1:1.,2:.7}.get(style,1.)
    cooldown={0:30,1:20,2:10}.get(style,20)*1_000_000_000
    if o.get('road_type') not in (0,6,7):return self.cancel('roadTypeUnavailable')
    nav=o.get('nav_distance_m')
    if type(nav) not in (int,float) or not math.isfinite(nav) or nav<2000*factor:
      return self.cancel('navigationPriority')
    speed=o.get('speed_mps');steering=o.get('steering_deg');curve=o.get('curvature')
    if (any(type(v) not in (int,float) or not math.isfinite(v) for v in (speed,steering,curve))
        or speed<max(70,settings.overtake_min_kph)/3.6 or abs(steering)>15 or abs(curve)>.02):
      return self.cancel('speedOrCurve')
    sides=o.get('sides') or {}
    state=o.get('model_state','unknown');direction=o.get('model_direction','none')
    if state=='unknown':return self.cancel('modelStateUnavailable')
    if self.pending and self.phase in ('requested','changing'):
      if not side_clear(sides.get(self.pending)):return self.cancel('crossingUnavailable')
      if state in ('laneChangeStarting','laneChangeFinishing'):
        if direction!=self.pending:return self.cancel('unexpectedLaneChange')
        self.saw_start=True;self.saw_finish|=state=='laneChangeFinishing';self.phase='changing'
      elif state=='off' and self.saw_start and self.saw_finish:
        self.net_changes+=1 if self.pending=='left' else -1
        self.memory_since=now_ns if self.net_changes else 0
        self.pending=None;self.phase='passing' if self.net_changes else 'cooldown'
        self.saw_start=self.saw_finish=False
        return self._result('observedComplete')
      elif now_ns-self.since>10_000_000_000:return self.cancel('completionTimeout')
      return self._result(request=self.pending)
    if self.net_changes:
      if now_ns-self.memory_since>30_000_000_000:
        self.net_changes=0;return self.cancel('laneMemoryExpired')
      return_side='right' if self.net_changes>0 else 'left'
      if not side_clear(sides.get(return_side)) or o.get('passed_confirmed') is not True:
        self.passed_since=0;return self._result('waitingPassAndReturnGap')
      advantage=o.get('return_advantage_kph')
      if type(advantage) not in (int,float) or not math.isfinite(advantage) or advantage<8*{0:1.5,1:1.,2:.5}.get(style,1.):
        self.passed_since=0
        return self._result('returnAdvantageInsufficient')
      if not self.passed_since:self.passed_since=now_ns
      if now_ns-self.passed_since<2_000_000_000:return self._result('confirmingPass')
      if settings.overtake_mode!=2:return self._result('suggestReturn')
      self.request_id+=1;self.pending=return_side;self.phase='requested';self.since=now_ns;self.last_action=now_ns
      return self._result(request=return_side)
    if state!='off':return self.cancel('modelBusy')
    if self.last_action and now_ns-self.last_action<cooldown:
      self.phase='cooldown';return self._result('actionCooldown')
    lead=o.get('lead') or {};distance=lead.get('distance_m');lead_speed=lead.get('speed_mps')
    if (lead.get('observed') is not True or any(type(v) not in (int,float) or not math.isfinite(v) for v in (distance,lead_speed))
        or not 0<distance<80*{0:.8,1:1.,2:1.2}.get(style,1.)
        or lead_speed<50/3.6 or speed-lead_speed<10/3.6*factor):return self.cancel('noSlowLead')
    target=next((s for s in ('left','right') if side_clear(sides.get(s))),None)
    if target is None:return self.cancel('sideObservationUnavailable')
    bias=o.get('nav_direction')
    if bias in ('left','right') and nav<=3000 and target!=bias:
      required=15+(3000-max(1000,min(3000,nav)))/2000*25
      if nav<1000 or (speed-lead_speed)*3.6<required:
        return self.cancel('navigationDirectionPriority')
    if self.candidate!=target:
      self.candidate=target;self.counter=0

    if self.phase!='preparing' or self.pending!=target:
      self.counter+=1
      if self.counter<3:self.phase='observing';return self._result('confirmingSlowLead')
      self.phase='preparing';self.pending=target;self.since=now_ns
    if now_ns-self.since<2_500_000_000:return self._result('preparationDelay')
    if settings.overtake_mode!=2:return self._result('suggestPass')
    self.request_id+=1;self.phase='requested';self.last_action=now_ns
    return self._result(request=target)
