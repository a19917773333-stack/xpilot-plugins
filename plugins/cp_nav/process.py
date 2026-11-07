"""Independent CP receiver and native Carrot coordinator. No camera clients."""
import time
from openpilot.cereal import messaging
from openpilot.common.params import Params
from openpilot.common.realtime import Ratekeeper
from openpilot.tesla import plugins
from .ingress import CPStore
from .network import CPTransports
from .plugin import CPNav
from .runtime import CPRuntime
from .settings import read


def healthy(sm,names,now,age=250_000_000):
  return all(sm.seen[n] and sm.alive[n] and sm.valid[n] and 0<=now-sm.logMonoTime[n]<=age for n in names)


def parked_now(state):
  return bool(state.get('verified') is True and 0<=time.monotonic_ns()-state.get('stamp',0)<=250_000_000)


def publish(kind, payload, valid_for_ms):
  try:
    plugins.send_msg(CPNav, kind, payload, valid_for_ms)
  except Exception:
    pass  # keep the CP servers alive if the broker is missing or another publisher owns it


def main():
  params=plugins.view(Params());store=CPStore();runtime=CPRuntime(read(params))
  sm=messaging.SubMaster(['carState','carControl','controlsState','modelV2','deviceState'])
  msgs=plugins.PluginMsgs();parked={'verified':False}
  transports=CPTransports(store,params,lambda:parked_now(parked))
  rk=Ratekeeper(20);next_settings=0
  try:
    while True:
      sm.update(0);now=time.monotonic_ns();cs=sm['carState'];cc=sm['carControl']
      vehicle=healthy(sm,['carState','carControl','controlsState'],now)
      parked['stamp']=int(sm.logMonoTime['carState'])
      parked['verified']=bool(healthy(sm,['carState'],now) and str(cs.gearShifter)=='park' and cs.vEgo<.1)
      if now>=next_settings:
        runtime.settings=read(params);next_settings=now+1_000_000_000
      ingress=transports.servers[0]
      with ingress.lock:
        snapshot=store.snapshot(connected=bool(ingress.owner and ingress.applied),now_ns=now)
      model=sm['modelV2'] if healthy(sm,['modelV2'],now,150_000_000) else None
      if healthy(sm,['carState'],now):transports.metadata.update(cs,model,int(sm.logMonoTime['carState']))
      try:
        oem=msgs.fresh('oem.lanes').get('cp_nav') or {}
      except Exception:
        oem={}
      out=runtime.tick(snapshot,cs,cc,model,int(sm.logMonoTime['modelV2']),now_ns=now,
        vehicle_fresh=vehicle,owner=plugins.owner(params,'source:route')=='cp_nav',
        oem=oem,
        curvature=float(sm['controlsState'].desiredCurvature) if vehicle else None)
      publish('cp.state',out['state'],500)
      publish('lanes.intent',out['intent'],200)
      rk.keep_time()
  finally:
    transports.close()
    publish('cp.state',{'valid':False},100)
    publish('lanes.intent',{'valid':False,'signalRequested':False},100)


if __name__=='__main__':main()
