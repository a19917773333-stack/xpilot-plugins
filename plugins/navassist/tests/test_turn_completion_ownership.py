"""Before-fix integration failures:
- advancing guidance during an observed turn must not replace the owned lamp ID;
- completion must still cancel after stable clear, route change, disable or stale data;
- opposite driver signals retain ownership; holding a lamp never grants lane change.
"""
from types import SimpleNamespace as N
import pytest
from navassist.intent import TurnSignalCoordinator
from navassist.turnsignal import TurnSignalController, checksum, decode


def nav(event=7, **changes):
  return dict(valid=True, linked=True, stale=False, sessionId='route', routeRevision=1,
              maneuverEventId=event, maneuver='turn_right', distanceM=80., **changes)


def observe(controller, now):
  template=bytearray(8); template[7]=checksum(template)
  controller.observe([(now, [(0x3E9, bytes(template), 1)])], now)


def start(side='right'):
  turns, wire=TurnSignalCoordinator(),TurnSignalController()
  n=nav();n['maneuver']='turn_'+side
  cs=N(leftBlinker=False,rightBlinker=False,brakePressed=False)
  cc=N(latActive=True)
  intent=turns.update(n,speed_mps=12.,now_ns=1_000_000_000)
  observe(wire,1_000_000_000)
  sent=wire.update(intent,cs,cc,1_000_000_000,enabled=True)
  assert len(sent)==1 and decode(sent[0][1])['turn']==(1 if side=='left' else 2)
  setattr(cs,side+'Blinker',True)
  return turns,wire,n,cs,cc


def next_instruction(n):
  return dict(n,maneuverEventId=8,maneuver='straight',distanceM=500.)


@pytest.mark.parametrize('side',['left','right'])
def test_guidance_advance_holds_same_wire_request_until_turn_completes(side):
  turns,wire,n,cs,cc=start(side)
  following=next_instruction(n)
  for now,geometry in [(1_100_000_000,True),(1_200_000_000,False),(1_600_000_000,False)]:
    intent=turns.update(following,speed_mps=6.,now_ns=now,turn_geometry_active=geometry)
    observe(wire,now)
    assert intent['signalRequested'] and intent['reason']=='turnCompletion'
    assert not intent['spLaneChangeReady'] and not intent['laneChangeAllowed']
    assert wire.update(intent,cs,cc,now,enabled=True)==[]
    assert wire.active['phase']=='active' and wire.active['requestId']==7
  now=1_700_000_001
  intent=turns.update(following,speed_mps=6.,now_ns=now,turn_geometry_active=False)
  observe(wire,now)
  assert not intent['signalRequested']
  assert decode(wire.update(intent,cs,cc,now,enabled=True)[0][1])['turn']==3


@pytest.mark.parametrize('cause',['revision','session','disabled','stale'])
def test_real_route_or_permission_change_still_releases_owned_lamp(cause):
  turns,wire,n,cs,cc=start()
  following=next_instruction(n)
  if cause=='revision':following['routeRevision']=2
  if cause=='session':following['sessionId']='other'
  if cause=='stale':following.update(valid=False,linked=False,stale=True)
  now=1_100_000_000
  intent=turns.update(following,speed_mps=6.,now_ns=now,turn_geometry_active=True)
  observe(wire,now)
  assert decode(wire.update(intent,cs,cc,now,enabled=cause!='disabled')[0][1])['turn']==3


def test_driver_opposite_signal_during_completion_is_never_cancelled():
  turns,wire,n,cs,cc=start()
  now=1_100_000_000
  intent=turns.update(next_instruction(n),speed_mps=6.,now_ns=now,turn_geometry_active=True)
  cs.leftBlinker=True
  observe(wire,now)
  assert wire.update(intent,cs,cc,now,enabled=True)==[]
  assert wire.active is None
