"""Jetlink tile: the link setting and what the phone last did."""
from openpilot.tesla.ui.tile import Tile
from openpilot.tesla.ui.tiles import TileSpec

from .status import tile_state


class JetlinkTile(Tile):
  SPEC = TileSpec("jetlink", "Jetlink", sizes=("small", "medium"), show="offroad", order=5)

  def state(self, sm):
    from openpilot.common.params import Params
    from openpilot.tesla.plugin_params import ParamsView
    params = ParamsView(Params())
    return tile_state(params.get("XpilotJetlinkMode"), params.get("XpilotJetlinkStatus"),
                     params.get("XpilotJetlinkProgress"), params.get("XpilotJetlinkSpec"))

  def draw(self, rect, size, state):
    self.draw_value(rect, "jetlink", sub=state or "link off")
