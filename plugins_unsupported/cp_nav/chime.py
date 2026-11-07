"""One host buzzer notice per CP-owned maneuver; settings are cached once a second."""

from openpilot.tesla.plugin import PluginAlert
from .settings import CPSettings


class CPChime:
  def __init__(self, params):
    self.params = params
    self._msgs = None
    self.previous = None

  def _read(self):
    # Only these two BOOLs are consumed here; avoid reading all native tuning keys
    # each frame while keeping explicit disable effective immediately.
    return CPSettings(enabled=self.params.get_bool('ExtCpNavEnabled'), beep=self.params.get_bool('ExtCpNavBeep'))

  def update(self, sm):
    settings = self._read()
    if not settings.enabled or not settings.beep:
      return []
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs = PluginMsgs()
    d = self._msgs.fresh('lanes.intent').get('cp_nav') or {}
    if not (d.get('valid') is True and d.get('signalRequested') is True):
      return []
    key = (d.get('sessionId'), d.get('routeRevision'),
           d.get('maneuverEventId', d.get('requestId')), str(d.get('direction', 'none')))
    if key == self.previous:
      return []
    self.previous = key
    return [PluginAlert('warning', 'CP navigation signal', str(d.get('direction', 'none')).capitalize())]
