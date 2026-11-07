"""Failures first: two unacknowledged requests cancel after ~0.2 s despite
2.5 s feedback allowance; the same failed event restarts every few cycles;
a cancellation/new-event boundary bypasses the global CAN send interval.
"""
from types import SimpleNamespace as N
from navassist.turnsignal import TurnSignalController,checksum,decode,FEEDBACK_TIMEOUT_NS,SEND_INTERVAL_NS


def setup():
  wire=TurnSignalController()
  intent=dict(valid=True,signalRequested=True,direction='right',sessionId='s',routeRevision=1,requestId=7)
  cs=N(leftBlinker=False,rightBlinker=False,brakePressed=False)
  return wire,intent,cs,N(latActive=True)


def tick(wire,intent,cs,cc,now):
  template=bytearray(8);template[7]=checksum(template)
  wire.observe([(now,[(0x3e9,bytes(template),1)])],now)
  return wire.update(intent,cs,cc,now,enabled=True)


def test_wait_for_feedback_instead_of_cancelling_after_retry():
  w,i,c,a=setup();base=1_000_000_000
  assert decode(tick(w,i,c,a,base)[0][1])['turn']==2
  assert decode(tick(w,i,c,a,base+SEND_INTERVAL_NS)[0][1])['turn']==2
  for offset in (2*SEND_INTERVAL_NS,500_000_000,1_000_000_000,FEEDBACK_TIMEOUT_NS):
    assert tick(w,i,c,a,base+offset)==[]
  c.rightBlinker=True
  assert tick(w,i,c,a,base+FEEDBACK_TIMEOUT_NS+1)==[]
  assert w.active['phase']=='active'


def test_failed_event_expires_once_and_cannot_restart_until_a_new_event():
  w,i,c,a=setup();base=1_000_000_000
  tick(w,i,c,a,base);tick(w,i,c,a,base+SEND_INTERVAL_NS)
  now=base+FEEDBACK_TIMEOUT_NS+1
  assert decode(tick(w,i,c,a,now)[0][1])['turn']==3
  for offset in (10_000_000,200_000_000,1_000_000_000,60_000_000_000):
    assert tick(w,i,c,a,now+offset)==[]
  i['requestId']=8
  assert decode(tick(w,i,c,a,now+60_000_000_000+SEND_INTERVAL_NS)[0][1])['turn']==2


def test_new_request_after_cancel_still_obeys_global_rate_limit():
  w,i,c,a=setup();base=1_000_000_000
  tick(w,i,c,a,base)
  i['signalRequested']=False
  assert decode(tick(w,i,c,a,base+SEND_INTERVAL_NS)[0][1])['turn']==3
  i.update(signalRequested=True,requestId=8)
  assert tick(w,i,c,a,base+SEND_INTERVAL_NS+10_000_000)==[]
  assert decode(tick(w,i,c,a,base+2*SEND_INTERVAL_NS)[0][1])['turn']==2
