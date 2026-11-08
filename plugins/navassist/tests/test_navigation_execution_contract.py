"""Failures: ready intent bypasses SP wait; execution is silent; a cleared
blindspot stays stuck; turn-only is misrepresented as permission to change.
"""
from types import SimpleNamespace as N
from openpilot.cereal import log
from .test_migration_contract import Params, Messages


def test_navigation_ready_never_overrides_sp_wait_or_driver_veto():
  from navassist.policy import NavLanePolicy
  p = NavLanePolicy(Params())
  p._msgs = Messages({'lanes.intent': {'navassist': dict(valid=True, signalRequested=True,
    direction='left', targetLaneIndex=0, spLaneChangeReady=True, laneChangeAllowed=True)}})
  assert not p.allow(None, 1, False)
  assert p.allow(None, 1, True)


def test_chime_waits_for_execution_after_clearance():
  from navassist.chime import NavigationChime
  from .test_signal_and_buzzer_admission import State
  def state(meta):
    sm = State()
    sm['modelV2'].meta = meta
    sm['carState'].leftBlinker, sm['carState'].rightBlinker = True, False
    return sm
  chime = NavigationChime(Params())
  chime.settings = N(enabled=True, beep_enabled=True)
  intent = dict(valid=True, signalRequested=True, direction='left', targetLaneIndex=0,
                spLaneChangeReady=False, laneChangeAllowed=False,
                sessionId='s', routeRevision=1, maneuverEventId=9, requestId=1)
  chime._msgs = Messages({'lanes.intent': {'navassist': intent}})
  assert chime.update(state(N(laneChangeState=log.LaneChangeState.preLaneChange, laneChangeDirection=log.LaneChangeDirection.left))) == []
  assert chime.update(state(N(laneChangeState='preLaneChange', laneChangeDirection='left'))) == []
  intent.update(spLaneChangeReady=True, laneChangeAllowed=True)
  assert chime.update(state(N(laneChangeState='preLaneChange', laneChangeDirection='left'))) == []
  executing = state(N(laneChangeState=log.LaneChangeState.laneChangeStarting, laneChangeDirection=log.LaneChangeDirection.left))
  assert len(chime.update(executing)) == 1
  assert chime.update(executing) == []
  intent['requestId'] = 2
  chime.settings.beep_enabled = False
  assert chime.update(state(N(laneChangeState='preLaneChange', laneChangeDirection='left'))) == []
  chime.settings.beep_enabled = True
  intent['valid'] = False
  assert chime.update(state(N(laneChangeState='preLaneChange', laneChangeDirection='left'))) == []


def test_turn_only_status_and_waiting_are_distinct():
  from navassist.display import signal_status
  assert signal_status(dict(signalRequested=True, direction='left', targetLaneIndex=-1)) == 'TURN SIGNAL ONLY'
  assert signal_status(dict(signalRequested=True, direction='left', targetLaneIndex=0,
                            reason='heuristicWaitingBlindspot')) == 'WAIT BLINDSPOT'
  assert signal_status(dict(signalRequested=True, direction='left', targetLaneIndex=0,
                            spLaneChangeReady=True)) == 'READY - SP CHECKS'


def test_clearance_recovery_keeps_request_and_rechecks_before_ready():
  from .test_legacy_lane_intent import plan, topology, vehicle
  from navassist.coordinator import NavLaneIntentCoordinator
  c = NavLaneIntentCoordinator()
  c.update(plan(), topology(left_cross=True), vehicle(left_blinker=True), now_ns=1_000_000_000)
  blocked = c.update(plan(), topology(left_cross=True), vehicle(left_blinker=True,bsm_left=True), now_ns=1_600_000_000)
  assert blocked.signal_requested and not blocked.lane_change_ready
  clear = c.update(plan(), topology(left_cross=True), vehicle(left_blinker=True), now_ns=1_700_000_000)
  assert clear.signal_requested and not clear.lane_change_ready
  ready = c.update(plan(), topology(left_cross=True), vehicle(left_blinker=True), now_ns=2_100_000_000)
  assert ready.lane_change_ready and ready.request_id == blocked.request_id
