"""Read-only map diagnostics. No CAN sends, route claims, or actuation permission."""
import time
from openpilot.tesla.plugin import Plugin
from openpilot.tesla import plugins
from .map_data import MapData, LimitComparison


class TeslaMap(Plugin):
  def __init__(self, CP, params):
    super().__init__(CP, params)
    self.map = MapData()
    self.comparison = LimitComparison()
    self.fused = 0.
    self.fused_stamp = 0
    self.next_publish = 0

  def publish_state(self, CS_SP):
    self.fused = float(CS_SP.speedLimit)
    self.fused_stamp = time.monotonic_ns()

  def observe_can(self, can_list, now_ns):
    self.map.update(can_list, now_ns)
    if now_ns >= self.next_publish:
      self.next_publish = now_ns+500_000_000
      snapshot = self.map.snapshot(now_ns)
      fused = self.fused if 0 <= now_ns-self.fused_stamp <= 500_000_000 else 0.
      snapshot['comparison'] = self.comparison.update(snapshot, fused, now_ns)
      plugins.send_msg(type(self), 'tesla.map', snapshot, 750)
    return []
