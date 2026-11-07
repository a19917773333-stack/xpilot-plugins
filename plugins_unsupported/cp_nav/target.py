"""Fresh CP native cruise targets, independent of the TesNav target hook."""
import time
from .settings import read
from .speed import CPSpeedPolicy


class CPTarget:
  def __init__(self,CP,params):
    self.params=params;self.policy=CPSpeedPolicy();self._msgs=None

  def update(self,sm,v_ego,v_cruise):
    settings=read(self.params)
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs=PluginMsgs()
    state=self._msgs.fresh('cp.state').get('cp_nav') or {}
    cs=sm['carState'];cc=sm['carControl'];now=time.monotonic_ns()
    fresh=all(sm.alive[n] and sm.valid[n] and 0<=now-sm.logMonoTime[n]<=250_000_000
              for n in ('carState','carControl')) if settings.enabled else False
    return self.policy.update(state,v_cruise=v_cruise,v_ego=v_ego,
      long_active=bool(fresh and cc.enabled and cc.longActive),
      override=bool(cs.gasPressed or cs.brakePressed or cc.cruiseControl.override),
      settings=settings,now_ns=now)
