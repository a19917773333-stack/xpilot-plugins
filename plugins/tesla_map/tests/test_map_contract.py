"""Failures: bus aliasing, unknown bounds, stale comparison and unrelated forks."""
from tesla_map.map_data import MapData, LimitComparison
from navassist.branch import BranchMatcher


def frame(code=13, distance=20, side='right', units=1, kind=1):
  value=(units<<7)|(code<<8)|(kind<<13)|(1<<28)|(distance<<32)|(1<<37)
  if side in ('left','both'): value|=1<<38
  if side in ('right','both'): value|=1<<39
  return value.to_bytes(8,'little')


def test_bus_time_unknown_and_bounds():
  m=MapData(); m.update([(10,[(0x238,frame(),0)])],10)
  assert not m.snapshot(10)['fresh']
  m.update([(10,[(0x238,frame(code=25,distance=31),1)])],10)
  s=m.snapshot(10)
  assert s['limit']['value']==120 and s['branch']['distanceM'] is None
  m.update([(9,[(0x238,frame(code=1),1)])],10)
  assert m.snapshot(10)['limit']['value']==120
  assert not m.snapshot(1_000_000_011)['fresh']
  for code in (0,30,31):
    m=MapData();m.update([(10,[(0x238,frame(code=code),1)])],10)
    assert m.snapshot(10)['limit']['value'] is None


def test_conflict_units_continuity_and_loss():
  m=MapData(); c=LimitComparison()
  for t in (1,1_000_000_001,2_000_000_001,3_000_000_001):
    m.update([(t,[(0x238,frame(code=13),1)])],t)
    s=c.update(m.snapshot(t),80/3.6,t)
  assert s['state']=='CONFLICT' and s['blockIncrease']
  assert c.update(m.snapshot(t+2_000_000_000),80/3.6,t+2_000_000_000)['state']=='SP_ONLY'
  m.update([(t+2_000_000_001,[(0x238,frame(code=13,units=0),1)])],t+2_000_000_001)
  assert c.update(m.snapshot(t+2_000_000_001),65*.44704,t+2_000_000_001)['state']=='AGREE'


def test_fork_is_advisory_event_bound_and_never_route_authority():
  m=MapData(); b=BranchMatcher()
  nav=dict(valid=True,stale=False,routeActive=True,sessionId='a',routeRevision=1,maneuverEventId=2,
           maneuver='exit_right',distanceM=200)
  for t,d in ((1,20),(500_000_001,19),(1_000_000_001,18)):
    m.update([(t,[(0x238,frame(distance=d),1)])],t)
    n=dict(nav,distanceM=d*10)
    s=b.update(n,m.snapshot(t),t)
  assert s['state']=='CONSISTENT' and not s['controlAuthorized']
  assert b.update(dict(n,maneuver='straight'),m.snapshot(t),t)['state']=='PASSING_FORK'
  assert b.update(dict(n,routeRevision=2),m.snapshot(t),t)['state']=='CHECKING'
  assert b.update(n,m.snapshot(t+2_000_000_000),t+2_000_000_000)['state']=='UNAVAILABLE'


def test_all_codes_and_malformed_frames():
  expected=[None,5,7,10,15,20,25,30,35,40,45,50,55,60,65,70,75,80,85,90,95,100,105,110,115,120,130,140,150,160,None,None]
  for code,value in enumerate(expected):
    m=MapData();m.update([(10,[(0x238,frame(code=code),1)])],10)
    assert m.snapshot(10)['limit']['value']==value
  for stamp,data,bus in ((11,b'bad',1),(12,frame(),0),(30,frame(),1)):
    m=MapData();m.update([(stamp,[(0x238,data,bus)])],20)
    assert not m.snapshot(20)['fresh']


def test_no_conflict_on_conditional_map_or_comparison_gap():
  for kind in (0,2,3,4,7):
    m=MapData();c=LimitComparison()
    for t in (1,1_000_000_001,2_000_000_001,3_000_000_001):
      m.update([(t,[(0x238,frame(kind=kind),1)])],t)
      assert not c.update(m.snapshot(t),100/3.6,t)['blockIncrease']
  m=MapData();c=LimitComparison()
  for t in (1,4_000_000_001):
    m.update([(t,[(0x238,frame(),1)])],t)
    assert not c.update(m.snapshot(t),100/3.6,t)['blockIncrease']


def test_duplicate_frames_and_both_exits_never_confirm():
  nav=dict(valid=True,stale=False,routeActive=True,sessionId='a',routeRevision=1,maneuverEventId=2,
           maneuver='exit_right',distanceM=200)
  m=MapData();b=BranchMatcher();m.update([(1,[(0x238,frame(),1)])],1)
  for t in (1,2,3,4):assert b.update(nav,m.snapshot(t),t)['state']=='CHECKING'
  m.update([(5,[(0x238,frame(side='both'),1)])],5)
  assert b.update(nav,m.snapshot(5),5)['state']=='DIFFERENT_FORK'


def test_consumers_ship_identical_decoder_without_sibling_imports():
  from pathlib import Path
  root=Path(__file__).resolve().parents[2]
  assert (root/'tesla_map/map_data.py').read_bytes()==(root/'navassist/map_data.py').read_bytes()
  assert (root/'tesla_map/map_data.py').read_bytes()==(root/'auto_speed/map_data.py').read_bytes()


def test_dbc_packer_matches_independent_literal_bits():
  from opendbc.can import CANPacker
  p=CANPacker('tesla_modely_hw4_perception')
  values=dict(UI_mapSpeedUnits=1,UI_mapSpeedLimit=25,UI_mapSpeedLimitType=1,UI_gpsRoadMatch=1,
              UI_nextBranchDist=250,UI_controlledAccess=1,UI_nextBranchRightOffRamp=1)
  packed=p.make_can_msg('UI_driverAssistMapData',1,values)
  assert packed[1]==frame(code=25,distance=25)
