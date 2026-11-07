"""Chime contract: only a fresh navigation-owned signal, once per request.
Manual changes, expired input and disabled settings stay silent; navigation execution announces once.
"""
from types import SimpleNamespace as N
from openpilot.cereal import log
from .test_migration_contract import Params, Messages


def test_navigation_start_chime_is_single_and_never_manual():
  from navassist.chime import NavigationChime
  source = NavigationChime(Params())
  source.settings = N(enabled=True, beep_enabled=True)
  source._msgs = Messages({})
  from .test_signal_and_buzzer_admission import State
  sm = State()
  sm['modelV2'].meta.laneChangeDirection = log.LaneChangeDirection.left
  sm['carState'].leftBlinker, sm['carState'].rightBlinker = True, False
  assert source.update(sm) == []
  intent = dict(valid=True, signalRequested=True, direction='left', targetLaneIndex=0,
                spLaneChangeReady=True, laneChangeAllowed=True, requestId=4,
                sessionId='s', routeRevision=1, maneuverEventId=9)
  source._msgs = Messages({'lanes.intent': {'navassist': intent}})
  sm['modelV2'].meta.laneChangeState = log.LaneChangeState.preLaneChange
  assert source.update(sm) == []
  sm['modelV2'].meta.laneChangeState = log.LaneChangeState.laneChangeStarting
  assert len(source.update(sm)) == 1
  assert source.update(sm) == []
  source.settings.beep_enabled = False
  intent['requestId'] = 5
  assert source.update(sm) == []
  source.settings.beep_enabled = True
  intent['targetLaneIndex'] = -1
  intent['laneChangeAllowed'] = False
  assert source.update(sm) == []
  assert source.update(sm) == []
