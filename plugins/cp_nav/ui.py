"""Floating CP navigation status. Display only; no parameter or control writes."""
from openpilot.system.ui.lib.application import FontWeight
from openpilot.tesla.ui.plugin_ui import ScreenOverlay
from openpilot.tesla.ui.tile import text
import pyray as rl


class CPNavigationOverlay(ScreenOverlay):
  def __init__(self):self._msgs=None;self.state={};self.intent={}

  def update(self,sm):
    if self._msgs is None:
      from openpilot.tesla.plugins import PluginMsgs
      self._msgs=PluginMsgs()
    self.state=self._msgs.fresh('cp.state').get('cp_nav') or {}
    self.intent=self._msgs.fresh('lanes.intent').get('cp_nav') or {}

  def draw(self,zones):
    rect=zones.get('bottom')
    if rect is None or rect.width<600 or rect.height<100:return
    x=rect.x+20;y=rect.y+12
    text(FontWeight.MEDIUM,'CP navigation',x,y,28,rl.SKYBLUE)
    native=self.state.get('carrot') or {}
    valid=self.state.get('valid') is True
    text(FontWeight.MEDIUM,'CP navigation ready' if valid else 'CP source unavailable',x+240,y,28,rl.WHITE)
    if not valid:return
    side=self.intent.get('direction','none');size=min(100,rect.height-70)
    cx=x+size*.5;cy=y+65
    if side in ('left','right'):
      ex=cx+(-size*.4 if side=='left' else size*.4)
      for a,b in (((cx,cy+size*.5),(cx,cy)),((cx,cy),(ex,cy)),
                  ((ex,cy),(ex+(size*.2 if side=='left' else -size*.2),cy-size*.2))):
        rl.draw_line_ex(rl.Vector2(*a),rl.Vector2(*b),6,rl.SKYBLUE)
    distance=native.get('xDistToTurn')
    if isinstance(distance,(int,float)) and distance>=0:
      text(FontWeight.BOLD,f'{int(distance)} m',x+140,y+65,50,rl.WHITE)
    target=native.get('desiredSpeed')
    if isinstance(target,(int,float)) and 0<target<250:
      text(FontWeight.MEDIUM,'CP target',x+370,y+65,28,rl.SKYBLUE)
      text(FontWeight.BOLD,f'{int(target)} km/h',x+370,y+100,38,rl.WHITE)
    if self.state.get('passingMode',0)>0 and self.state.get('overtakingAvailable') is not True:
      text(FontWeight.MEDIUM,'CP passing unavailable',x+650,y+65,26,rl.ORANGE)
