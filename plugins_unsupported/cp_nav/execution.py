"""Native Carrot maneuver outputs -> bounded lamp/preparation intents.
Only SP can start a crossing. A route-turn lamp carries turn intent; a fork
lamp waits through a veto. One observed completion consumes a route maneuver.
"""
from .overtake import side_clear


class CPExecution:
  def __init__(self):
    self.key=None;self.request=0;self.since=0;self.started=self.finished=False
    self.consumed=set()

  def update(self,state,observations,passing,settings,now_ns):
    out=dict(valid=False,signalRequested=False,laneChangeAllowed=False,
      turnOnly=False,direction='none',sessionId='',routeRevision=0,
      requestId=self.request,reason='unavailable')
    if not (settings.enabled and settings.signals and state.get('valid') is True
            and state.get('control_allowed') is True):
      self.key=None;return out
    route=tuple(state.get('route_key') or ('',0));event=state.get('event',0)
    kind=(state.get('carrot') or {}).get('atcType','none')
    # Preserve native prepare/cancel boundaries; do not infer withdrawn turns.
    if kind not in ('fork left','fork right','turn left','turn right','atc left','atc right'):
      kind='none'
    side=kind.rsplit(' ',1)[-1] if kind!='none' else passing.get('request_direction')
    turn=kind.startswith(('turn ','atc '));fork=kind.startswith('fork ')
    key=(route,event,side,'turn' if turn else 'fork' if fork else ('pass',passing.get('request_id')))
    if side not in ('left','right') or key in self.consumed:
      self.key=None;return out
    if key!=self.key:
      self.key=key;self.request+=1;self.since=now_ns;self.started=self.finished=False
    model_state=observations.get('model_state');model_side=observations.get('model_direction')
    if not turn and model_side==side:
      self.started|=model_state=='laneChangeStarting'
      self.finished|=self.started and model_state=='laneChangeFinishing'
    if not turn and self.started and self.finished and model_state=='off':
      self.consumed.add(key)
      if len(self.consumed)>64:self.consumed={key}
      self.key=None;out['reason']='observedComplete';return out
    # Signals remain useful preparation while BSM/paint vetoes the crossing.
    ready=bool(not turn and settings.lane_changes and observations.get('fresh') is True
      and side_clear((observations.get('sides') or {}).get(side))
      and now_ns-self.since>=max(500,settings.lane_delay_ms)*1_000_000)
    out.update(valid=True,signalRequested=True,laneChangeAllowed=ready,turnOnly=turn,
      direction=side,sessionId=route[0],routeRevision=route[1],maneuverEventId=event,
      requestId=self.request,reason='turn' if turn else 'ready' if ready else 'preparation')
    return out
