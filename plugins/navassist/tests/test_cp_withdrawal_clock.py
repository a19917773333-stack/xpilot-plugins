"""Before-fix contract: CP8 withdrawal time and sensor time are different clocks.

Failure modes: fresh GPS after withdrawal is rejected; old GPS revives after a
withdrawal; heartbeats renew old observations; replay/future/stale frames pass;
or a withdrawal fails to clear an observation with a slightly later source time.
The first test uses timing differences from the real CP8 phone trace, no GPS.
"""
import pytest
from navassist.cpnav import CPStore


def sender():
  clock = [1_000_000]
  store = CPStore(clock_ms=lambda: clock[0], clock_ns=lambda: clock[0]*1_000_000)

  def send(seq, stamp, present=True, *, now=None, sent=None):
    clock[0] = stamp if now is None else now
    return store.accept(dict(type='item_update', protocol_version=2,
      session_id=store.session, kind='json', name='vehicle', manifest_revision=1,
      stream_handle=store.handles['vehicle'], schema_version=1, sequence=seq,
      source_timestamp_ms=stamp, sent_at_ms=stamp if sent is None else sent,
      present=present, value={'sample': stamp} if present else None))
  return store, clock, send


def test_actual_cp8_new_gps_77ms_before_withdrawal_time_is_accepted():
  store, clock, send = sender()
  send(1, 1_000_770, now=1_002_150, sent=1_001_726)
  send(2, 1_002_135, False, now=1_002_546, sent=1_002_136)
  assert store._value('vehicle', clock[0]*1_000_000) == {}
  assert send(3, 1_002_058, now=1_002_574, sent=1_002_136)['accepted']
  assert store._value('vehicle', clock[0]*1_000_000) == {'sample': 1_002_058}


def test_initial_withdrawal_does_not_become_a_sensor_watermark():
  store, clock, send = sender()
  send(1, 1_000_000, False)
  send(2, 999_922, now=1_000_010, sent=1_000_010)
  assert store._value('vehicle', clock[0]*1_000_000)


@pytest.mark.parametrize('stamp', [999_999, 1_000_000])
def test_old_or_same_sensor_sample_cannot_revive_after_withdrawal(stamp):
  store, clock, send = sender()
  send(1, 1_000_000)
  send(2, 1_000_010, False)
  with pytest.raises(ValueError):
    send(3, stamp, now=1_000_020, sent=1_000_020)
  assert store._value('vehicle', clock[0]*1_000_000) == {}


def test_repeated_present_sample_does_not_extend_source_expiry():
  store, clock, send = sender()
  send(1, 1_000_000)
  send(2, 1_000_000, now=1_001_000, sent=1_001_000)
  assert store._value('vehicle', 1_001_501_000_000) == {}
  with pytest.raises(ValueError):
    send(3, 1_000_000, now=1_001_501, sent=1_001_501)


@pytest.mark.parametrize('seq,stamp,sent', [(1,1_000_010,1_000_010),
  (2,998_000,1_000_010), (2,1_000_600,1_000_600), (2,1_000_010,1_000_009)])
def test_transport_replay_stale_future_and_invalid_send_time_still_rejected(seq,stamp,sent):
  store, clock, send = sender()
  send(1, 1_000_000)
  with pytest.raises(ValueError):
    send(seq, stamp, now=1_000_010, sent=sent)


def test_withdrawal_always_clears_even_if_sensor_was_slightly_in_future():
  store, clock, send = sender()
  send(1, 1_000_400, now=1_000_000, sent=1_000_400)
  send(2, 1_000_010, False)
  assert store._value('vehicle', clock[0]*1_000_000) == {}


def test_new_session_clears_both_withdrawal_and_sensor_watermarks():
  store, clock, send = sender()
  send(1, 1_000_000)
  send(2, 1_000_010, False)
  store.restart()
  assert send(1, 999_990, now=1_000_020, sent=1_000_020)['accepted']
