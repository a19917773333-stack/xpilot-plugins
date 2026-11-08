"""CP owns its master, execution modes and native navigation parameters."""
from dataclasses import dataclass


@dataclass(frozen=True)
class CPSettings:
  enabled: bool = False
  signals: bool = True
  lane_changes: bool = True
  speed_control: bool = True
  speed_raise: bool = False
  overtake_mode: int = 0
  driving_style: int = 1
  auto_turn: int = 2
  turn_kph: int = 20
  turn_end_s: int = 5
  decel_cms2: int = 120
  speed_factor_pct: int = 100
  road_offset_kph: int = 0
  speed_end_s: int = 5
  bump_kph: int = 30
  bump_time_s: int = 3
  rear_hold_m: int = 100
  curve_mode: int = 0
  curve_min_kph: int = 20
  curve_factor_pct: int = 100
  countdown_mode: int = 0
  max_kph: int = 120
  raise_step_kph: int = 10
  raise_interval_s: int = 3
  lane_delay_ms: int = 500
  overtake_min_kph: int = 70
  beep: bool = True


# Native keys are scoped aliases, never requests to mutate the SP/global keys.
NATIVE_KEYS = {
 'AutoNaviSpeedBumpSpeed':'bump_kph','AutoNaviSpeedBumpTime':'bump_time_s',
 'AutoNaviSpeedCtrlEnd':'speed_end_s','AutoNaviRearCameraHoldDistance':'rear_hold_m',
 'AutoNaviSpeedSafetyFactor':'speed_factor_pct','AutoNaviSpeedDecelRate':'decel_cms2',
 'AutoNaviCountDownMode':'countdown_mode','TurnSpeedControlMode':'curve_mode',
 'MapTurnSpeedFactor':'curve_factor_pct','AutoTurnControlSpeedTurn':'turn_kph',
 'AutoTurnControl':'auto_turn','AutoTurnControlTurnEnd':'turn_end_s',
 'AutoCurveSpeedLowerLimit':'curve_min_kph','AutoRoadSpeedLimitOffset':'road_offset_kph',
}


class NativeParams:
  def __init__(self, settings):self.settings=settings
  def get_int(self, key):
    if key in NATIVE_KEYS:return int(getattr(self.settings,NATIVE_KEYS[key]))
    if key=='AutoNaviSpeedCtrlMode':return 1
    return 0
  def get_float(self, key):return float(self.get_int(key))
  def get_bool(self, key):return key=='IsMetric'
  def get(self, key):
    if key=='LanguageSetting':return 'main_zh-CHS'
    return str(self.get_int(key))


BOUNDS = {
 'overtake_mode':(0,2),'driving_style':(0,2),'auto_turn':(0,3),
 'turn_kph':(10,40),'turn_end_s':(1,15),'decel_cms2':(50,250),
 'speed_factor_pct':(80,110),'road_offset_kph':(-20,20),'speed_end_s':(1,15),
 'bump_kph':(10,50),'bump_time_s':(1,10),'rear_hold_m':(0,500),
 'curve_mode':(0,0),'curve_min_kph':(10,60),'curve_factor_pct':(50,150),
 'countdown_mode':(0,0),'max_kph':(30,140),'raise_step_kph':(1,10),
 'raise_interval_s':(3,30),'lane_delay_ms':(500,5000),'overtake_min_kph':(70,120),
}


def param_key(name):
  return 'ExtCpNav'+''.join(part.capitalize() for part in name.split('_'))


def read(params):
  values={}
  for name, field in CPSettings.__dataclass_fields__.items():
    key=param_key(name)
    try:
      raw=params.get_bool(key) if isinstance(field.default,bool) else int(params.get(key,return_default=True))
    except (ValueError,TypeError,KeyError):raw=field.default
    if name in BOUNDS:
      low,high=BOUNDS[name];raw=max(low,min(high,raw))
    values[name]=raw
  return CPSettings(**values)
