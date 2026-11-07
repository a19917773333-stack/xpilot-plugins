"""Big-screen tile and page for the cruise switches."""
from pathlib import Path

import pyray as rl

from openpilot.tesla.plugins import PLUGINS
from openpilot.tesla.ui.pages.base import Header, ListPage, SettingRow, params
from openpilot.tesla.ui.tile import Tile
from openpilot.tesla.ui.tiles import TileSpec


_ICON = None


def _icon():
  """The plugin ships its own cruise icon; load it once from this directory."""
  global _ICON
  if _ICON is None:
    image = rl.load_image(str(Path(__file__).with_name('icons') / 'cruise.png'))
    _ICON = rl.load_texture_from_image(image)
    rl.unload_image(image)
  return _ICON


def _plugin():
  return next(p for p in PLUGINS if p.NAME == 'cruise_settings')


class CruisePage(ListPage):
  def __init__(self):
    super().__init__()
    self.add(Header('CRUISE'))
    self.rows = [SettingRow(s) for s in _plugin().SETTINGS]
    self.add(*[r.item for r in self.rows])

  def refresh(self):
    for row in self.rows:
      row.refresh()


class CruiseTile(Tile):
  SPEC = TileSpec('cruise_settings', 'CRUISE', sizes=('small',), services=(), show='always', hz=2)
  PAGE = CruisePage

  def state(self, sm):
    p = params()
    icbm = bool(p.get_bool('ExtCruiseIcbm'))
    speed = str(p.get('ExtCruiseInitialSpeed', return_default=True) or '40')
    return (icbm, speed)

  def draw(self, rect, size, state):
    self.face(rect)
    texture = _icon()
    side = min(rect.width, rect.height) * 0.42
    rl.draw_texture_ex(texture, rl.Vector2(rect.x + (rect.width - side) / 2, rect.y + rect.height * 0.34 - side / 2),
                       0.0, side / texture.width, rl.WHITE)
