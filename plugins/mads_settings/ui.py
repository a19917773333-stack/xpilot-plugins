"""Big-screen tile and page for the MADS switches: a small tile opens a native page with one row per setting."""
from openpilot.tesla.plugins import PLUGINS
from openpilot.tesla.ui.pages.base import Header, ListPage, SettingRow, params
from openpilot.tesla.ui.tile import Tile
from openpilot.tesla.ui.tiles import TileSpec

MODE_NAMES = {"0": "HOLD", "1": "PAUSE", "2": "OFF"}
ICON = "icons/chffr_wheel.png"  # steering wheel from the host assets


def _plugin():
  return next(p for p in PLUGINS if p.NAME == 'mads_settings')


class MadsPage(ListPage):
  def __init__(self):
    super().__init__()
    self.add(Header('MADS'))
    self.rows = [SettingRow(s) for s in _plugin().SETTINGS]
    self.add(*[r.item for r in self.rows])

  def refresh(self):
    for row in self.rows:
      row.refresh()


class MadsTile(Tile):
  SPEC = TileSpec('mads_settings', 'MADS', sizes=('small',), services=(), show='always', hz=2)
  PAGE = MadsPage

  def state(self, sm):
    p = params()
    enabled = bool(p.get_bool('ExtMadsEnabled'))
    mode = str(p.get('ExtMadsSteeringMode', return_default=True) or '0')
    return (enabled, MODE_NAMES.get(mode, mode))

  def draw(self, rect, size, state):
    self.face(rect, icon=ICON)
