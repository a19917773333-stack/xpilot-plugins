"""Failure first: a navigation warning reaches the host's ordinary prompt but
C3XL's actual GPIO backend discards it. Verify the full producer/host/backend
chain with GPIO dispatch mocked, plus existing dedup and critical-tone routing.
Never construct Beepd or open a real GPIO device in this check.
"""
from types import SimpleNamespace as N
from openpilot.cereal import log
from unittest.mock import Mock
import pytest
from navassist.chime import NavigationChime
from .test_migration_contract import Params,Messages
from openpilot.tesla import plugins,alerts
from openpilot.sunnypilot.system.alert_output import Beepd,AudibleAlert


def backend():
  b=Beepd.__new__(Beepd)
  b.current_alert=AudibleAlert.none
  b.prompt_suppress_until=0
  b.dispatch_beep=Mock()
  return b


def test_navigation_execution_reaches_c3xl_buzzer_once(monkeypatch):
  monkeypatch.setattr(alerts,'current',{})
  c=NavigationChime(Params());c.plugin_name='navassist'
  c.settings=N(enabled=True,beep_enabled=True)
  intent=dict(valid=True,signalRequested=True,direction='right',sessionId='s',routeRevision=1,
              maneuverEventId=3,requestId=3,spLaneChangeReady=True,laneChangeAllowed=True,targetLaneIndex=2)
  c._msgs=Messages({'lanes.intent':{'navassist':intent}})
  events=[]
  from .test_signal_and_buzzer_admission import State
  sm=State()
  plugins.update_alerts([c],sm,N(add=events.append))
  assert events==[alerts.EVENT_NAMES['warning']]
  alert=alerts._callback('warning')(None,None,{},False,0,None)
  assert alert.audible_alert==AudibleAlert.prompt and alert.duration>=5
  b=backend()
  for _ in range(5):b.update_alert(alert.audible_alert)
  b.dispatch_beep.assert_called_once_with(b.engage)
  plugins.update_alerts([c],sm,N(add=events.append))
  assert not alerts.current  # the same navigation request does not create another notice


@pytest.mark.parametrize('sound',[AudibleAlert.warningSoft,AudibleAlert.warningImmediate])
def test_critical_beeps_keep_their_existing_warning_pattern(sound):
  b=backend();b.update_alert(sound);b.update_alert(sound)
  b.dispatch_beep.assert_called_once_with(b.warning)
