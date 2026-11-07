"""Parked-only native settings and a read-only summary tile."""
from pathlib import Path
from openpilot.tesla import manifest
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.system.ui.lib.multilang import tr
from openpilot.tesla.ui.tile import Tile
from openpilot.tesla.ui.tiles import TileSpec
from openpilot.tesla.ui.pages.base import Header, ListPage, SettingRow


class TurnLanePage(ListPage):
  def __init__(self):
    super().__init__()
    settings=manifest.parse(Path(__file__).with_name('plugin.json')).settings
    self.rows=[SettingRow(setting) for setting in settings]
    self.add(Header('Existing SP controls'), *[row.item for row in self.rows])

  def show_event(self):
    super().show_event()
    for row in self.rows:
      row.refresh()


class TurnLaneTile(Tile):
  SPEC=TileSpec('turn_lane_settings','Turn & Lane Settings',sizes=('small','medium'),show="offroad",hz=.5,order=4)
  PAGE=TurnLanePage

  def state(self,sm):
    p=ui_state.params
    mph=float(p.get('LaneTurnValue',return_default=True))
    mode=int(p.get('AutoLaneChangeTimer',return_default=True))
    delay={-1:'Off',0:'Steering nudge',1:'0.05 s',2:'0.5 s',3:'1 s',4:'2 s',5:'3 s'}.get(mode,'Check settings')
    return p.get_bool('LaneTurnDesire'),round(mph*1.609344,1),delay

  def draw(self,rect,size,state):
    enabled,kph,delay=state
    self.draw_lines(rect,[tr('Turn intent on' if enabled else 'Turn intent off'),
                          f'{kph:.1f} km/h',tr(delay)],size=34)
