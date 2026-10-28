"""Jetlink tile: the link setting and what the phone last did."""
from openpilot.tesla.ui.tile import Tile
from openpilot.tesla.ui.tiles import TileSpec


class JetlinkTile(Tile):
  SPEC = TileSpec("jetlink", "Jetlink", sizes=("small", "medium"), show="offroad", order=5)

  def state(self, sm):
    from openpilot.common.params import Params
    params = Params()
    return params.get("XpilotJetlinkStatus") or ""

  def draw(self, rect, size, state):
    self.draw_value(rect, "jetlink", sub=state or "link off")