"""Independent CP navigation entry. No TesNav package dependency."""
from openpilot.tesla.plugin import Plugin
# Import-time capability gate: the old single-publisher host cannot run CP.
from openpilot.tesla.plugin_msgd import socket_path as _required_message_broker  # noqa: F401
from .settings import read
from .turnsignal import TurnSignalController
from .oem import OemLaneSignals


def always(started,params,CP):return True


class CPNav(Plugin):
  SERVICES=('carState','carControl')

  def __init__(self,CP,params):
    super().__init__(CP,params)
    self.params=params;self.settings=read(params);self.turns=TurnSignalController();self._msgs=None;self.oem=OemLaneSignals();self._next_oem=0


  def service_params(self,params):
    self.params=params;self.settings=read(params)

  def observe_can(self,can_list,now_ns):
    self.turns.observe(can_list,now_ns);self.oem.update(can_list,now_ns)
    if now_ns>=self._next_oem:
      self._next_oem=now_ns+100_000_000
      from openpilot.tesla import plugins
      plugins.send_msg(type(self),'oem.lanes',self.oem.payload(now_ns),350)
    return []

  def control_sends(self,CS,CC,now_ns):
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs=PluginMsgs()
    intent=self._msgs.fresh('lanes.intent').get('cp_nav') or {}
    return self.turns.update(intent,CS,CC,now_ns,enabled=self.settings.enabled and self.settings.signals)

  @classmethod
  def processes(cls):
    from openpilot.system.manager.process import PythonProcess
    return [PythonProcess('cp_navd',f'{__package__}.process',always)]

  @classmethod
  def lane_change_policy(cls,params):
    from .policy import CPLanePolicy
    return CPLanePolicy(params)

  @classmethod
  def long_target(cls,CP,params):
    from .target import CPTarget
    return CPTarget(CP,params)

  @classmethod
  def alert_source(cls,CP,params):
    from .chime import CPChime
    return CPChime(params)
