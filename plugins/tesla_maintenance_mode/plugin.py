"""One-click Tesla maintenance command: 0x339 on CAN2, fixed payload, exactly one frame."""
from opendbc.car.can_definitions import CanData
from openpilot.tesla.plugin import Plugin

from .pulse import MaintenancePulse

ADDRESS = 0x339
BUS = 1
DATA = bytes((0x00, 0x00, 0x00, 0x00, 0x00, 0x80, 0x00, 0x00))
TRIGGER_PARAM = "ExtTeslaMaintenanceModeSend"


class TeslaMaintenanceMode(Plugin):
  def __init__(self, CP, params):
    super().__init__(CP, params)
    self.pulse = MaintenancePulse()
    self._last_trigger = False
    # A stale true value must never turn into a CAN frame after a restart.
    if params.get_bool(TRIGGER_PARAM):
      params.put_bool(TRIGGER_PARAM, False, block=True)

  def service_params(self, params) -> None:
    trigger = params.get_bool(TRIGGER_PARAM)
    if trigger and not self._last_trigger:
      self.pulse.request()
    self._last_trigger = trigger
    if trigger:
      params.put_bool(TRIGGER_PARAM, False, block=True)
      self._last_trigger = False

  def control_sends(self, CS, CC, now_ns: int) -> list:
    return [CanData(ADDRESS, DATA, BUS)] if self.pulse.take(now_ns) else []
