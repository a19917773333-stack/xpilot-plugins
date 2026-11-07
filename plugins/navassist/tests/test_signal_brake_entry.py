"""Failures first: a brake-held initial request emits an active lamp frame;
road-edge/no-neighbor evidence suppresses a genuine junction lamp. Lane
crossing must still be denied, and hazards/driver lamps remain driver-owned.
"""
from types import SimpleNamespace as N
import pytest
from navassist.turnsignal import TurnSignalController, checksum, decode
from navassist.intent import build_intent,TurnSignalCoordinator,LaneIntentCoordinator
from navassist.settings import NavSettings


def test_brake_held_before_initial_request_does_not_emit_active_signal():
  controller=TurnSignalController();now=1_000_000_000
  template=bytearray(8);template[7]=checksum(template)
  controller.observe([(now,[(0x3e9,bytes(template),1)])],now)
  intent=dict(valid=True,signalRequested=True,direction='right',sessionId='s',routeRevision=1,requestId=7)
  cs=N(leftBlinker=False,rightBlinker=False,brakePressed=True)
  assert controller.update(intent,cs,N(latActive=True),now,enabled=True)==[]
  assert controller.active is None
  cs.brakePressed=False
  frames=controller.update(intent,cs,N(latActive=True),now+100_000_000,enabled=True)
  assert decode(frames[0][1])['turn']==2


@pytest.mark.parametrize('side',['left','right'])
def test_junction_at_road_edge_preserves_lamp_without_crossing_authority(side):
  nav=dict(valid=True,linked=True,stale=False,sessionId='s',routeRevision=1,maneuverEventId=7,
           maneuver='turn_'+side,distanceM=35.,laneTotalCount=1,lanes=[dict(index=0,recommended=True)])
  topology=dict(valid=True,visibleLaneCount=1,egoLaneIndexFromLeft=0,absoluteEgoIndex=0,
    leftNeighborExists=False,rightNeighborExists=False,leftRoadEdge=True,rightRoadEdge=True,
    leftCrossingAllowed=False,rightCrossingAllowed=False)
  result=build_intent(nav,topology,settings=NavSettings(),v_ego=5.,now_ns=1_000_000_000,
    left_blocked=True,right_blocked=True,blindspot_left=True,blindspot_right=True,lateral_active=True,
    turns=TurnSignalCoordinator(),lanes=LaneIntentCoordinator())
  assert result['signalRequested'] and result['direction']==side
  assert result['targetLaneIndex']==-1 and result['signalPurpose']=='junction'
  assert not result['laneChangeAllowed'] and not result['spLaneChangeReady']
