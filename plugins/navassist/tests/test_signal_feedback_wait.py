"""Failures first: unacknowledged requests retry once per second, stop after
four bounded attempts, and cannot restart until a new event; a cancellation/
new-event boundary still obeys the global CAN send interval."""
from types import SimpleNamespace as N
from navassist.turnsignal import TurnSignalController,checksum,decode,SEND_INTERVAL_NS


def setup():
  wire=TurnSignalController()
  intent=dict(valid=True,signalRequested=True,direction='right',sessionId='s',routeRevision=1,requestId=7)
  cs=N(leftBlinker=False,rightBlinker=False,brakePressed=False)
  return wire,intent,cs,N(latActive=True)


def tick(wire,intent,cs,cc,now):
  template=bytearray(8);template[7]=checksum(template)
  wire.observe([(now,[(0x3e9,bytes(template),1)])],now)
  return wire.update(intent,cs,cc,now,enabled=True)


def test_retries_each_second_then_waits_for_feedback_before_cancel():
  w,i,c,a=setup();base=1_000_000_000
  assert decode(tick(w,i,c,a,base)[0][1])['turn']==2
  assert tick(w,i,c,a,base+500_000_000)==[]
  for attempt in range(1,4):
    assert decode(tick(w,i,c,a,base+attempt*1_000_000_000)[0][1])['turn']==2
  c.rightBlinker=True
  assert tick(w,i,c,a,base+3_000_000_001)==[]
  assert w.active['phase']=='active' and w.active['action_attempts']==4


def test_failed_event_expires_once_and_cannot_restart_until_a_new_event():
  w,i,c,a=setup();base=1_000_000_000
  for offset in range(4):
    assert decode(tick(w,i,c,a,base+offset*1_000_000_000)[0][1])['turn']==2
  now=base+4_000_000_000
  assert decode(tick(w,i,c,a,now)[0][1])['turn']==3
  for offset in (10_000_000,200_000_000,1_000_000_000,60_000_000_000):
    assert tick(w,i,c,a,now+offset)==[]
  i['requestId']=8
  assert decode(tick(w,i,c,a,now+60_000_000_000+SEND_INTERVAL_NS)[0][1])['turn']==2




def test_physical_feedback_stops_resend_without_cancelling():
  w,i,c,a=setup();base=1_000_000_000
  assert decode(tick(w,i,c,a,base)[0][1])['turn']==2
  c.rightBlinker=True
  assert tick(w,i,c,a,base+1_000_000_000)==[]
  assert w.active['phase']=='active' and w.active['action_attempts']==1


def test_new_request_after_cancel_still_obeys_global_rate_limit():
  w,i,c,a=setup();base=1_000_000_000
  tick(w,i,c,a,base)
  i['signalRequested']=False
  assert decode(tick(w,i,c,a,base+SEND_INTERVAL_NS)[0][1])['turn']==3
  i.update(signalRequested=True,requestId=8)
  assert tick(w,i,c,a,base+SEND_INTERVAL_NS+10_000_000)==[]
  assert decode(tick(w,i,c,a,base+2*SEND_INTERVAL_NS)[0][1])['turn']==2
