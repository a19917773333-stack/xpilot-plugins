"""Read only bounded plugin messages, never CAN or settings."""
import time
from openpilot.tesla.plugins import PluginMsgs
from openpilot.tesla.ui.tile import Tile
from openpilot.tesla.ui.tiles import TileSpec
from .view import lines


class TeslaMapTile(Tile):
  SPEC = TileSpec('tesla_map', 'Tesla Map', sizes=('medium', 'wide'), show='onroad', hz=2, order=55)

  def state(self, sm):
    if not hasattr(self, '_messages'):
      self._messages = PluginMsgs()
    snapshot = self._messages.fresh('tesla.map').get('tesla_map', {})
    stamp = snapshot.get('stampNs', 0)
    if not stamp or not 0 <= time.monotonic_ns()-stamp <= 1_000_000_000:
      snapshot = {}
    return lines(snapshot)

  def draw(self, rect, size, state):
    self.draw_lines(rect, list(state))
