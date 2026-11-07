# Adapted from jixiexiaoge/carrot 3615bf4 (MIT; see ../CARROT-LICENSE).
from __future__ import annotations
from .common import math, np, time, json, collections, CV, MyMovingAverage, GPSSources, messaging
from .control import CarrotNaviControl, parse_carrot_navi_control
from .constants import COUNTDOWN_NEW_TARGET_MIN_JUMP_M, SCHOOL_ZONE_GAS_OVERRIDE_TIMEOUT_S, nav_type_mapping

class Part0:
  def _initialize(self):
      self.nRoadLimitSpeed = 30
      self.nRoadLimitSpeed_last = 30
      self.nRoadLimitSpeed_counter = 0
      self.active_carrot = 0
      self.active_count = 0
      self.active_sdi_count = 0
      self.active_sdi_count_max = 200
      self.active_kisa_count = 0
      self.external_navigation_active = False
      self.nSdiType = -1
      self.nSdiSpeedLimit = 0
      self.nSdiSection = 0
      self.nSdiDist = 0
      self.nSdiBlockType = -1
      self.nSdiBlockSpeed = 0
      self.nSdiBlockDist = 0
      self.nTBTDist = 0
      self.nTBTTurnType = -1
      self.szTBTMainText = ''
      self.szNearDirName = ''
      self.szFarDirName = ''
      self.nTBTNextRoadWidth = 0
      self.nTBTDistNext = 0
      self.nTBTTurnTypeNext = -1
      self.szTBTMainTextNext = ''
      self.nGoPosDist = 0
      self.nGoPosTime = 0
      self.szPosRoadName = ''
      self.nSdiPlusType = -1
      self.nSdiPlusSpeedLimit = 0
      self.nSdiPlusDist = 0
      self.nSdiPlusBlockType = -1
      self.nSdiPlusBlockSpeed = 0
      self.nSdiPlusBlockDist = 0
      self.goalPosX = 0.0
      self.goalPosY = 0.0
      self.szGoalName = ''
      self.vpPosPointLatNavi = 0.0
      self.vpPosPointLonNavi = 0.0
      self.vpPosPointLat = 0.0
      self.vpPosPointLon = 0.0
      self.roadcate = 8
      self.nPosSpeed = 0.0
      self.nPosAngle = 0.0
      self.nPosAnglePhone = 0.0
      self.diff_angle_count = 0
      self.last_calculate_gps_time = 0
      self.position_mono_time = 0
      self.last_update_gps_time = 0
      self.last_update_gps_time_phone = 0
      self.last_update_gps_time_navi = 0
      self.bearing_offset = 0.0
      self.bearing_measured = 0.0
      self.bearing = 0.0
      self.gps_valid = False
      self.phone_gps_accuracy = 0.0
      self.gps_accuracy_device = 0.0
      self.phone_latitude = 0.0
      self.phone_longitude = 0.0
      self.phone_gps_frame = 0
      self.totalDistance = 0
      self.xSpdLimit = 0
      self.xSpdDist = 0
      self.xSpdType = -1
      self.rear_camera_events = []
      self.xTurnInfo = -1
      self.xDistToTurn = 0
      self.xTurnInfoNext = -1
      self.xDistToTurnNext = 0
      (self.navType, self.navModifier) = ('invalid', '')
      (self.navTypeNext, self.navModifierNext) = ('invalid', '')
      self.carrotIndex = 0
      self.carrotCmdIndex = 0
      self.carrotCmd = ''
      self.carrotArg = ''
      self.carrotCmdIndex_last = 0
      self.traffic_light_q = collections.deque(maxlen=int(2.0 / 0.1))
      self.traffic_light_count = -1
      self.traffic_state = 0
      self.left_spd_sec = 100
      self.left_tbt_sec = 100
      self.speed_countdown_distance_last = 0.0
      self.turn_countdown_distance_last = 0.0
      self.left_sec = 100
      self.max_left_sec = 100
      self.carrot_left_sec = 100
      self.sdi_inform = False
      self.atc_paused = False
      self.atc_activate_count = 0
      self.gas_override_speed = 0
      self.gas_pressed_state = False
      self.speed_event_gas_pressed = False
      self.source_last = 'none'
      self.school_zone_gas_override_started_at = None
      self.school_zone_suppressed = False
      self.carrot_navi_session_id = ''
      self.carrot_navi_speed_sequence = -1
      self.carrot_navi_current_sequence = -1
      self.carrot_navi_next_sequence = -1
      self.carrot_navi_vehicle_sequence = -1
      self.carrot_navi_route_sequence = -1
      self.carrot_navi_active = False
      self.carrot_navi_has_control = False
      self.carrot_navi_road_limit_valid = False
      self.carrot_navi_off_route = False
      self.carrot_navi_traffic_active = False
      self.carrot_navi_control = None
      self.debugText = ''
      self.lang = 'en'
      self.update_params()

  def update_params(self):
      self.autoNaviSpeedBumpSpeed = float(self.params.get_int('AutoNaviSpeedBumpSpeed'))
      self.autoNaviSpeedBumpTime = float(self.params.get_int('AutoNaviSpeedBumpTime'))
      self.autoNaviSpeedBumpEndDistance = float(min(5000, max(0, self.params.get_int('AutoNaviSpeedBumpEndDistance')))) * 0.01
      self.autoNaviSpeedCtrlEnd = float(self.params.get_int('AutoNaviSpeedCtrlEnd'))
      self.autoNaviRearCameraHoldDistance = float(min(300, max(0, self.params.get_int('AutoNaviRearCameraHoldDistance'))))
      self.autoNaviSpeedCtrlMode = self.params.get_int('AutoNaviSpeedCtrlMode')
      self.vehicleNaviCanControl = min(3, max(0, self.params.get_int('VehicleNaviCanControl')))
      self.vehicleNaviSchoolZoneControl = self.params.get_bool('VehicleNaviSchoolZoneControl')
      self.vehicleSpeedCameraControlMode = min(3, max(0, self.params.get_int('VehicleSpeedCameraControlMode')))
      self.autoNaviSpeedSafetyFactor = float(self.params.get_int('AutoNaviSpeedSafetyFactor')) * 0.01
      self.autoNaviSpeedDecelRate = float(self.params.get_int('AutoNaviSpeedDecelRate')) * 0.01
      self.autoNaviCountDownMode = self.params.get_int('AutoNaviCountDownMode')
      self.turnSpeedControlMode = self.params.get_int('TurnSpeedControlMode')
      self.mapTurnSpeedFactor = self.params.get_float('MapTurnSpeedFactor') * 0.01
      self.autoTurnControlSpeedTurn = self.params.get_int('AutoTurnControlSpeedTurn')
      self.autoTurnMapChange = self.params.get_int('AutoTurnMapChange')
      self.autoTurnControl = self.params.get_int('AutoTurnControl')
      self.autoTurnControlTurnEnd = self.params.get_int('AutoTurnControlTurnEnd')
      self.autoCurveSpeedLowerLimit = int(self.params.get('AutoCurveSpeedLowerLimit'))
      self.is_metric = self.params.get_bool('IsMetric')
      self.autoRoadSpeedLimitOffset = self.params.get_int('AutoRoadSpeedLimitOffset')
      try:
          lang_val = self.params.get('LanguageSetting') or self.params.get('lang')
      except Exception:
          lang_val = None
      if isinstance(lang_val, bytes):
          try:
              lang_val = lang_val
          except Exception:
              lang_val = None
      if lang_val == 'main_ko':
          self.lang = 'ko'
      elif lang_val == 'main_zh-CHS':
          self.lang = 'zh'
      else:
          self.lang = 'en'

  def _update_cmd(self):
      if self.carrotCmdIndex != self.carrotCmdIndex_last:
          self.carrotCmdIndex_last = self.carrotCmdIndex
          command_handlers = {'DETECT': self._handle_detect_command}
          handler = command_handlers.get(self.carrotCmd)
          if handler:
              handler(self.carrotArg)
      self.traffic_light_q.append((-1, -1, 'none', 0.0))
      self.traffic_light_count -= 1
      if self.traffic_light_count < 0:
          self.traffic_light_count = -1
          self.traffic_state = 0

  def _handle_detect_command(self, xArg):
      elements = [e.strip() for e in xArg.split(',')]
      if len(elements) >= 4:
          try:
              state = elements[0]
              value1 = float(elements[1])
              value2 = float(elements[2])
              value3 = float(elements[3])
              self.traffic_light(value1, value2, state, value3)
              self.traffic_light_count = int(0.5 / 0.1)
          except ValueError:
              pass

  def traffic_light(self, x, y, color, cnf):
      traffic_red = 0
      traffic_green = 0
      traffic_left = 0
      traffic_red_trig = 0
      traffic_green_trig = 0
      traffic_left_trig = 0
      for pdata in self.traffic_light_q:
          (px, py, pcolor, pcnf) = pdata
          if abs(x - px) < 0.2 and abs(y - py) < 0.2:
              if pcolor in ['Green Light', 'Left turn']:
                  if color in ['Red Light', 'Yellow Light']:
                      traffic_red_trig += cnf
                      traffic_red += cnf
                  elif color in ['Green Light', 'Left turn']:
                      traffic_green += cnf
              elif pcolor in ['Red Light', 'Yellow Light']:
                  if color in ['Green Light']:
                      traffic_green_trig += cnf
                      traffic_green += cnf
                  elif color in ['Left turn']:
                      traffic_left_trig += cnf
                      traffic_left += cnf
                  elif color in ['Red Light', 'Yellow Light']:
                      traffic_red += cnf
      if traffic_red_trig > 0:
          self.traffic_state = 1
      elif traffic_green_trig > 0 and traffic_green > traffic_red:
          self.traffic_state = 2
      elif traffic_left_trig > 0:
          self.traffic_state = 3
      elif traffic_red > 0:
          self.traffic_state = 1
      elif traffic_green > 0:
          self.traffic_state = 2
      else:
          self.traffic_state = 0
      self.traffic_light_q.append((x, y, color, cnf))

  def calculate_current_speed(self, left_dist, safe_speed_kph, safe_time, safe_decel_rate):
      safe_speed = safe_speed_kph / 3.6
      safe_dist = safe_speed * safe_time
      decel_dist = left_dist - safe_dist
      if decel_dist <= 0:
          return safe_speed_kph
      temp = safe_speed ** 2 + 2 * safe_decel_rate * decel_dist
      if temp < 0:
          speed_mps = safe_speed
      else:
          speed_mps = math.sqrt(temp)
      return max(safe_speed_kph, min(250, speed_mps * 3.6))

  def _external_navigation_connected(self):
      return self.carrot_navi_active or self.active_count > 0 or self.active_kisa_count > 0

  def _update_navigation_source(self):
      external_active = self._external_navigation_connected()
      changed = external_active != self.external_navigation_active
      self.external_navigation_active = external_active
      if changed:
          self.rear_camera_events = []
          self.speed_countdown_distance_last = self.turn_countdown_distance_last = 0.0
          self.left_spd_sec = self.left_tbt_sec = 100
          self.gas_override_speed = 0
          self.school_zone_gas_override_started_at = None
          self.school_zone_suppressed = False
      return changed

  def _rear_camera_speed(self, CS, delta_dist):
      hold_distance = self.autoNaviRearCameraHoldDistance
      if CS is None or delta_dist < 0 or (not self.external_navigation_active) or (self.autoNaviSpeedCtrlMode <= 0) or (hold_distance <= 0) or self.carrot_navi_off_route:
          self.rear_camera_events = []
          return (250.0, 0.0)
      self.rear_camera_events = [event for event in self.rear_camera_events if event['target'] + hold_distance > self.totalDistance]
      if self.active_carrot > 1 and self.xSpdType in (75, 76) and (0 < self.xSpdDist <= 50) and (self.xSpdLimit > 0):
          target = self.totalDistance + self.xSpdDist
          matching = next((event for event in self.rear_camera_events if abs(event['target'] - target) <= 40), None)
          if matching is None:
              self.rear_camera_events.append({'target': target, 'speed': self.xSpdLimit})
          else:
              matching['speed'] = min(matching['speed'], self.xSpdLimit)
      if not self.rear_camera_events:
          return (250.0, 0.0)
      event = min(self.rear_camera_events, key=lambda event: event['speed'])
      return (event['speed'], max(0.0, event['target'] + hold_distance - self.totalDistance))

  def _vehicle_speed_camera_enabled(self, CS):
      return not self.external_navigation_active and self.vehicleSpeedCameraControlMode > 0 and (CS.speedLimit > 0) and (CS.speedLimitDistance > 0) and (not (CS.schoolZoneActive and self.school_zone_suppressed)) and (not (self.vehicleSpeedCameraControlMode == 3 and CS.gasPressed))

  def _speed_bump_control_active(self, distance):
      return distance > self.autoNaviSpeedBumpEndDistance

  def _vehicle_speed_bump_enabled(self, CS):
      return not self.external_navigation_active and self.vehicleNaviCanControl and (self.autoNaviSpeedCtrlMode >= 2) and self._speed_bump_control_active(CS.speedBumpDistance)

  def _vehicle_school_zone_enabled(self, CS):
      if not CS.schoolZoneActive:
          self.school_zone_gas_override_started_at = None
          self.school_zone_suppressed = False
          return False
      return not self.external_navigation_active and self.vehicleNaviSchoolZoneControl and (self.vehicleSpeedCameraControlMode > 0) and (not self.school_zone_suppressed) and (not (self.vehicleSpeedCameraControlMode == 3 and CS.gasPressed))

  def _vehicle_school_zone_speed(self, CS):
      return 30 if self._vehicle_school_zone_enabled(CS) else 250

  def _vehicle_section_zone_enabled(self, CS):
      return not self.external_navigation_active and self.vehicleNaviCanControl and (self.vehicleSpeedCameraControlMode > 0) and getattr(CS, 'vehicleNaviSectionActive', False) and (getattr(CS, 'vehicleNaviSpeed', 0) > 0) and (not (self.vehicleSpeedCameraControlMode == 3 and CS.gasPressed))

  def _vehicle_navigation_display(self, CS):
      if self.external_navigation_active or CS is None or (not self.vehicleNaviCanControl) or (not getattr(CS, 'vehicleNaviActive', False)):
          return (False, 0, False)
      if CS.schoolZoneActive:
          speed = 30
      elif getattr(CS, 'vehicleNaviSpeed', 0) > 0:
          speed = int(CS.vehicleNaviSpeed * self.autoNaviSpeedSafetyFactor)
      elif self._speed_bump_control_active(CS.speedBumpDistance):
          speed = int(self.autoNaviSpeedBumpSpeed)
      else:
          speed = 0
      return (speed > 0, speed, bool(getattr(CS, 'vehicleNaviSectionActive', False)))

  def _speed_countdown_distance(self, CS):
      distances = []
      legacy_bump_suppressed = self.xSpdType == 22 and self.autoNaviCountDownMode == 1
      if self.external_navigation_active and self.xSpdDist > 0 and (not legacy_bump_suppressed):
          distances.append(self.xSpdDist)
      vehicle_navi_active = not self.external_navigation_active and CS is not None and self.vehicleNaviCanControl and getattr(CS, 'vehicleNaviActive', False)
      if vehicle_navi_active:
          camera_distance = getattr(CS, 'speedLimitDistance', 0)
          if camera_distance > 0:
              distances.append(camera_distance)
          bump_distance = getattr(CS, 'speedBumpDistance', 0)
          if self.autoNaviCountDownMode >= 2 and bump_distance > 0:
              distances.append(bump_distance)
      return min(distances, default=0)

  def _update_countdown_alert(self, left_sec, source, v_ego_kph):
      if left_sec > 11:
          self.left_sec = 100
          self.max_left_sec = 100
          self.carrot_left_sec = 100
          self.sdi_inform = False
          return
      self.sdi_inform = source in ('cam', 'hda')
      self.max_left_sec = min(11, max(6, int(v_ego_kph / 10) + 1))
      if left_sec != self.left_sec:
          if left_sec == self.max_left_sec and self.sdi_inform:
              self.carrot_left_sec = 11
          elif 1 <= left_sec < self.max_left_sec:
              self.carrot_left_sec = left_sec
          elif left_sec == 0 and self.left_sec == 1:
              self.carrot_left_sec = left_sec
          self.left_sec = left_sec

  @staticmethod
  def _countdown_channel(distance, previous_distance, previous_left_sec, v_ego):
      if distance <= 0:
          return (100, 0.0, False)
      calculated = int(max(distance - v_ego, 1) / max(1, v_ego) + 0.5)
      new_target = previous_distance > 0 and distance - previous_distance > max(COUNTDOWN_NEW_TARGET_MIN_JUMP_M, v_ego * 2.0)
      rearmed = new_target and previous_left_sec <= 11
      left_sec = calculated if new_target else min(previous_left_sec, calculated)
      return (100 if rearmed else left_sec, float(distance), rearmed)
