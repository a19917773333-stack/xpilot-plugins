"""AMap-style navigation HUD. Draws only in the strip below the road view."""
import time
import pyray as rl
from openpilot.system.ui.lib.application import FontWeight
from openpilot.tesla.ui.plugin_ui import ScreenOverlay
from openpilot.tesla.ui.tile import text, lines_in
from .display import read_state, signal_status
from .hud import present_hud, hud_rect, signal_authority, floating_layout

CYAN=rl.Color(78,224,255,255)
WHITE=rl.Color(238,244,252,255)
DIM=rl.Color(142,159,180,255)
AMBER=rl.Color(255,191,87,255)


def arrow(x,y,size,direction,color):
  """Vector arrows avoid missing icon glyphs in C3 fonts."""
  left='left' in str(direction)
  right='right' in str(direction)
  mid=x+size*.5
  if left or right:
    side=x+size*(.16 if left else .84)
    pts=[(mid,y+size*.86),(mid,y+size*.35),(side,y+size*.35)]
    head=[(side+size*(.2 if left else -.2),y+size*.16),(side,y+size*.35),
          (side+size*(.2 if left else -.2),y+size*.54)]
  else:
    pts=[(mid,y+size*.86),(mid,y+size*.16)]
    head=[(x+size*.3,y+size*.36),(mid,y+size*.16),(x+size*.7,y+size*.36)]
  for path in (pts,head):
    for a,b in zip(path,path[1:]):rl.draw_line_ex(rl.Vector2(*a),rl.Vector2(*b),max(3,size*.065),color)


class NavAssistOverlay(ScreenOverlay):
  def __init__(self):
    self.nav={};self.intent={};self.oem={};self.topology={}
    self._msgs=None;self.car=None;self.authority=None

  def update(self,sm):
    try:
      if self._msgs is None:
        from openpilot.tesla.plugins import PluginMsgs
        self._msgs=PluginMsgs()
      for key,value in read_state(self._msgs).items():setattr(self,key,value)
    except Exception:self.nav,self.intent,self.oem,self.topology={},{},{},{}
    self.car=None;self.authority=None
    now=time.monotonic_ns()
    try:
      if sm.alive['carState'] and sm.valid['carState'] and 0<=now-sm.logMonoTime['carState']<=500_000_000:
        cs=sm['carState'];self.car=dict(leftBlinker=bool(cs.leftBlinker),rightBlinker=bool(cs.rightBlinker))
      if sm.alive['pandaStates'] and sm.valid['pandaStates'] and 0<=now-sm.logMonoTime['pandaStates']<=500_000_000:
        states=[p for p in sm['pandaStates'] if str(p.safetyModel)=='tesla']
        if states:self.authority=any(signal_authority(p.controlsAllowed, getattr(p,'controlsAllowedLateral',False), p.alternativeExperience) for p in states)
    except (KeyError,AttributeError,TypeError):pass

  @staticmethod
  def _side_rect(zones):
    view=zones.get('view'); left=zones.get('left'); right=zones.get('right')
    if view is None or left is None or right is None:return None
    zone=right if right.width>=left.width else left
    if zone.width<160 or view.height<220:return None
    return rl.Rectangle(zone.x,view.y,zone.width,view.height)

  def _draw_side(self,rect,state):
    rl.draw_rectangle_rec(rect,rl.BLACK)
    tint=CYAN
    pad=14
    distance=state['distance']
    value='--' if distance is None else distance_text(distance)
    if state['maneuver']:
      size=max(40,min(rect.width-2*pad,rect.height*.50))
      ax=rect.x+(rect.width-size)/2
      ay=rect.y+pad
      arrow(ax,ay,size,state['maneuver'],tint)
      font_size=max(40,min(110,int(rect.height*.17)))
      width=font_size*.62*len(value)
      text(FontWeight.BOLD,value,rect.x+(rect.width-width)/2,ay+size+18,font_size,WHITE)
    else:
      font_size=max(40,min(110,int(rect.height*.20)))
      width=font_size*.62*len(value)
      text(FontWeight.BOLD,value,rect.x+(rect.width-width)/2,rect.y+(rect.height-font_size)/2,font_size,WHITE)

  def draw(self,zones):
    state=present_hud(self.nav,self.intent,self.topology,car=self.car,authority=self.authority)
    side=self._side_rect(zones)
    if side is not None:
      self._draw_side(side,state)
      return
    bottom=zones.get('bottom')
    if bottom is None:return
    x,y,w,h=hud_rect((bottom.x,bottom.y,bottom.width,bottom.height))
    if w<1000 or h<180:return
    # Erase the old tile faces to the screen canvas. Guidance has no card,
    # capsule or colored panel background; every symbol/text floats directly.
    rl.draw_rectangle_rec(bottom,rl.BLACK)
    tint=CYAN
    text(FontWeight.MEDIUM,'AMap Navigation',x+26,y+10,26,DIM)
    layout=floating_layout((bottom.x,bottom.y,bottom.width,bottom.height))
    ax,ay,aw,ah=layout['arrow']
    if state['maneuver']:
      arrow(ax,ay,aw,state['maneuver'],tint)
    distance=state['distance']
    value='--' if distance is None else distance_text(distance)
    text(FontWeight.BOLD,value,x+242,y+67,86,WHITE)
    text(FontWeight.MEDIUM,maneuver_label(state['maneuver']),x+246,y+166,38,DIM)
    lx=x+w*.40
    text(FontWeight.MEDIUM,'Recommended lanes',lx,y+12,26,DIM)
    count=state['count']
    if count:
      step=min(58,(w*.32)/count)
      for index in range(count):
        bx=lx+index*step;selected=index in state['recommended']
        arrow(bx+2,y+58,step-8,'straight',CYAN if selected else DIM)
        if selected:rl.draw_line_ex(rl.Vector2(bx+8,y+124),rl.Vector2(bx+step-12,y+124),3,CYAN)
        if state['ego']==index:rl.draw_circle(int(bx+step*.5),int(y+141),4,WHITE)
    else:text(FontWeight.MEDIUM,'Waiting for lane guidance',lx,y+74,27,DIM)
    lines=[state['lane_status'],state['status']]
    if state['phone_lane_message']:lines[0]=state['phone_lane_message']
    if state['branch_message']:lines.insert(0,state['branch_message'])
    if self.intent.get('signalRequested'):lines.append(signal_status(self.intent))
    lines_in(rl.Rectangle(lx,y+164,w*.34,h-164),lines,25,color=tint)
    rx,ry,rw,rh=layout['route']
    nodes=state['route_nodes']
    if len(nodes)>1:
      rl.draw_line_ex(rl.Vector2(rx+11,ry+42),rl.Vector2(rx+11,ry+rh*.5+42),2,rl.Color(78,224,255,115))
    for index,(maneuver,dist) in enumerate(nodes):
      ny=ry+index*rh*.5
      color=CYAN if index==0 else DIM
      rl.draw_circle(int(rx+11),int(ny+42),7 if index==0 else 5,color)
      text(FontWeight.MEDIUM,'Current maneuver' if index==0 else 'Next maneuver',rx+32,ny+13,24,DIM)
      arrow(rx+30,ny+44,49,maneuver,color)
      text(FontWeight.MEDIUM,maneuver_label(maneuver),rx+95,ny+42,28,color)
      text(FontWeight.BOLD,distance_text(dist),rx+95,ny+79,30,WHITE if index==0 else DIM)


def distance_text(distance):
  return f'{distance/1000:.1f} km' if distance>=1000 else f'{distance:.0f} m'


def maneuver_label(maneuver):
  return {'turn_left':'TURN L','turn_right':'TURN R','sharp_left':'SHARP L','sharp_right':'SHARP R',
    'u_turn_left':'U-TURN L','u_turn_right':'U-TURN R','merge_left':'MERGE L','merge_right':'MERGE R',
    'exit_left':'EXIT L','exit_right':'EXIT R','ramp_left':'RAMP L','ramp_right':'RAMP R',
    'slight_left':'KEEP L','slight_right':'KEEP R','straight':'STRAIGHT'}.get(maneuver,'')
