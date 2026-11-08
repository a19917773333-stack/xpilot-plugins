"""Failure cases before repair: held lamp survives plugin disable or loss of
lateral engagement; a transient invalid intent holds the owned lamp indefinitely.
The driver's opposite lamp must still win. All frames and state are isolated.
"""
from types import SimpleNamespace as N
import pytest
from cp_nav.turnsignal import TurnSignalController, checksum, decode

@pytest.mark.parametrize('cause', ['disabled', 'disengaged', 'source_timeout'])
def test_owned_held_lamp_releases_on_hard_gate_or_bounded_source_gap(cause):
    w = TurnSignalController()
    i = dict(valid=True, signalRequested=True, direction='right', sessionId='s', routeRevision=1,
             requestId=7, maneuverEventId=7)
    c, a = N(leftBlinker=False, rightBlinker=False, brakePressed=False), N(latActive=True)
    def tick(now, enabled=True):
        b = bytearray(8); b[7] = checksum(b)
        w.observe([(now, [(0x3e9, bytes(b), 1)])], now)
        return w.update(i, c, a, now, enabled=enabled)
    assert decode(tick(1_000_000_000)[0][1])['turn'] == 2
    c.rightBlinker = True
    if cause == 'disengaged':
        a.latActive = False
    if cause == 'source_timeout':
        i['valid'] = False
        assert tick(1_200_000_000) == []
    frames = tick(3_000_000_000, enabled=cause != 'disabled')
    assert frames and decode(frames[0][1])['turn'] == 3
