"""Regression: card must not steal cp_navd's sole cereal pluginMsg publisher.

Before repair this raises while observe_can creates a second PubMaster. The
host's native multi-process E2E covers delivery, credentials, expiry and restart.
"""
import time
from types import SimpleNamespace as N


def test_card_oem_observation_uses_host_broker_without_opening_a_cereal_publisher(monkeypatch):
 from cp_nav import plugin as entry
 from openpilot.cereal import messaging
 from openpilot.tesla import plugins
 monkeypatch.setattr(entry,'read',lambda p:N(enabled=True,signals=True))
 def forbidden(*a,**k):raise AssertionError('card created a second pluginMsg publisher')
 monkeypatch.setattr(messaging,'PubMaster',forbidden)
 sent=[]
 monkeypatch.setattr(plugins,'send_msg',lambda *a,**k:sent.append((a,k)))
 obj=entry.CPNav(N(),N())
 assert obj.observe_can([],time.monotonic_ns())==[]
 assert len(sent)==1
 args,_=sent[0]
 assert args[0] is entry.CPNav and args[1]=='oem.lanes' and args[3]==350
