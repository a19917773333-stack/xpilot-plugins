# Adapted from jixiexiaoge/carrot 3615bf4 (MIT; see ../CARROT-LICENSE).
from __future__ import annotations
from .common import math, np, time, json, collections, CV, MyMovingAverage, GPSSources, messaging
from .control import CarrotNaviControl, parse_carrot_navi_control
from .constants import COUNTDOWN_NEW_TARGET_MIN_JUMP_M, SCHOOL_ZONE_GAS_OVERRIDE_TIMEOUT_S, nav_type_mapping

class Part2:
  def _update_gps(self, v_ego, sm, gps_service):
      now = time.monotonic()
      sources = self._gps_sources()
      gps = sm[gps_service]
      if sm.updated[gps_service]:
          if sm.valid[gps_service] and gps.hasFix:
              sources.put('device', gps.latitude, gps.longitude, gps.bearingDeg, gps.speed, sm.recv_time[gps_service])
          else:
              sources.remove('device')
      if not sm.alive[gps_service] or not sm.valid[gps_service]:
          sources.remove('device')
      vehicle = sm['carState'].vehicleGps
      ego_speed = v_ego if math.isfinite(v_ego) and 0 <= v_ego <= 90 else 0.0
      if sm.alive['carState'] and sm.valid['carState'] and vehicle.valid:
          sources.put('vehicle', vehicle.latitude, vehicle.longitude, vehicle.headingDeg if vehicle.headingValid else None, ego_speed, vehicle.sampleMonoTime / 1000000000.0)
      else:
          sources.remove('vehicle')
      (source, fix) = sources.select(now)
      if source != getattr(self, 'position_source', 'none'):
          print(f'[GPS] source={source}', flush=True)
      self.position_source = source
      self.position_mono_time = now
      self.position_heading_valid = fix is not None and fix.heading is not None
      if fix is None:
          self.vpPosPointLat = self.vpPosPointLon = 0.0
          self.last_calculate_gps_time = 0.0
          return float(self.nPosAngle)
      self.last_calculate_gps_time = fix.stamp
      if fix.heading is not None:
          self.nPosAngle = fix.heading
      self.nPosSpeed = fix.speed * 3.6
      elapsed = now - fix.stamp if fix.heading is not None else 0.0
      (self.vpPosPointLat, self.vpPosPointLon) = self.estimate_position(fix.latitude, fix.longitude, ego_speed, self.nPosAngle, elapsed)
      return float(self.nPosAngle)

  def estimate_position(self, lat, lon, speed, angle, dt):
      R = 6371000
      angle_rad = math.radians(angle)
      delta_d = speed * dt
      delta_lat = delta_d * math.cos(angle_rad) / R
      new_lat = lat + math.degrees(delta_lat)
      delta_lon = delta_d * math.sin(angle_rad) / (R * math.cos(math.radians(lat)))
      new_lon = lon + math.degrees(delta_lon)
      return (new_lat, new_lon)

  def update_auto_turn(self, v_ego_kph, sm, x_turn_info, x_dist_to_turn, check_steer=False):
      turn_speed = self.autoTurnControlSpeedTurn
      fork_speed = self.nRoadLimitSpeed
      stop_speed = 1
      turn_dist_for_speed = self.autoTurnControlTurnEnd * turn_speed / 3.6
      fork_dist_for_speed = self.autoTurnControlTurnEnd * fork_speed / 3.6
      stop_dist_for_speed = 5
      start_fork_dist = np.interp(self.nRoadLimitSpeed, [30, 50, 100], [160, 200, 350])
      start_turn_dist = np.interp(self.nTBTNextRoadWidth, [5, 10], [43, 60])
      turn_info_mapping = {1: {'type': 'turn left', 'speed': turn_speed, 'dist': turn_dist_for_speed, 'start': start_fork_dist}, 2: {'type': 'turn right', 'speed': turn_speed, 'dist': turn_dist_for_speed, 'start': start_fork_dist}, 5: {'type': 'straight', 'speed': turn_speed, 'dist': turn_dist_for_speed, 'start': start_turn_dist}, 3: {'type': 'fork left', 'speed': fork_speed, 'dist': fork_dist_for_speed, 'start': start_fork_dist}, 4: {'type': 'fork right', 'speed': fork_speed, 'dist': fork_dist_for_speed, 'start': start_fork_dist}, 6: {'type': 'straight', 'speed': fork_speed, 'dist': fork_dist_for_speed, 'start': start_fork_dist}, 7: {'type': 'straight', 'speed': stop_speed, 'dist': stop_dist_for_speed, 'start': 1000}, 8: {'type': 'straight', 'speed': stop_speed, 'dist': stop_dist_for_speed, 'start': 1000}}
      default_mapping = {'type': 'none', 'speed': 0, 'dist': 0, 'start': 1000}
      mapping = turn_info_mapping.get(x_turn_info, default_mapping)
      atc_type = mapping['type']
      atc_speed = mapping['speed']
      atc_dist = mapping['dist']
      atc_start_dist = mapping['start']
      if x_dist_to_turn > atc_start_dist:
          atc_type += ' prepare'
          if check_steer:
              self.atc_activate_count = min(0, self.atc_activate_count - 1)
      else:
          if check_steer:
              self.atc_activate_count = max(0, self.atc_activate_count + 1)
          if atc_type in ['turn left', 'turn right'] and x_dist_to_turn > start_turn_dist:
              atc_type = 'atc left' if atc_type == 'turn left' else 'atc right'
      if self.autoTurnMapChange > 0 and check_steer:
          if self.atc_activate_count == 2:
              self.carrotCmdIndex += 100
              self.carrotCmd = 'DISPLAY'
              self.carrotArg = 'MAP'
          elif self.atc_activate_count == -50:
              self.carrotCmdIndex += 100
              self.carrotCmd = 'DISPLAY'
              self.carrotArg = 'ROAD'
      if check_steer:
          if 0 <= x_dist_to_turn < atc_start_dist and atc_type in ['fork left', 'fork right']:
              if not self.atc_paused:
                  steering_pressed = sm['carState'].steeringPressed
                  steering_torque = sm['carState'].steeringTorque
                  if steering_pressed and steering_torque < 0 and (atc_type in ['fork left', 'atc left']):
                      self.atc_paused = True
                  elif steering_pressed and steering_torque > 0 and (atc_type in ['fork right', 'atc right']):
                      self.atc_paused = True
          else:
              self.atc_paused = False
          if self.atc_paused:
              atc_type += ' canceled'
      atc_desired = 250
      if atc_speed > 0 and x_dist_to_turn > 0:
          decel = self.autoNaviSpeedDecelRate
          safe_sec = 2.0
          atc_desired = min(atc_desired, self.calculate_current_speed(x_dist_to_turn - atc_dist, atc_speed, safe_sec, decel))
      return (atc_desired, atc_type, atc_speed, atc_dist)

  def update_navi(self, remote_ip, sm, pm, vturn_speed, coords, distances, route_speed, gps_service):
      self.debugText = ''
      self.update_params()
      carrot_navi_active = self._update_carrot_navi(sm)
      if sm.alive['carState'] and sm.alive['selfdriveState']:
          CS = sm['carState']
          v_ego = CS.vEgo
          v_ego_kph = v_ego * 3.6
          distanceTraveled = sm['selfdriveState'].distanceTraveled
          delta_dist = distanceTraveled - self.totalDistance
          self.totalDistance = distanceTraveled
      else:
          v_ego = v_ego_kph = 0
          delta_dist = 0
          CS = None
      self.bearing = self._update_gps(v_ego, sm, gps_service)
      self.xSpdDist = max(self.xSpdDist - delta_dist, -1000)
      self.xDistToTurn = self.xDistToTurn - delta_dist
      self.xDistToTurnNext = self.xDistToTurnNext - delta_dist
      self.active_count = max(self.active_count - 1, 0)
      self.active_sdi_count = max(self.active_sdi_count - 1, 0)
      self.active_kisa_count = max(self.active_kisa_count - 1, 0)
      navigation_source_changed = self._update_navigation_source()
      if not self.external_navigation_active and CS is not None and (CS.speedLimit > 0):
          self.nRoadLimitSpeed = CS.speedLimit
      road_speed_limit_changed = self.nRoadLimitSpeed != self.nRoadLimitSpeed_last
      self.nRoadLimitSpeed_last = self.nRoadLimitSpeed
      if self.active_kisa_count > 0:
          self.active_carrot = 2
      elif self.active_count > 0:
          self.active_carrot = 2 if self.active_sdi_count > 0 else 1
      else:
          self.active_carrot = 0
      limit_speed = 200
      road_limit_valid = not carrot_navi_active or self.carrot_navi_road_limit_valid
      if self.autoRoadSpeedLimitOffset >= 0 and self.active_carrot >= 2 and road_limit_valid:
          if self.nRoadLimitSpeed >= 30:
              road_speed_limit_offset = self.autoRoadSpeedLimitOffset
              if not self.is_metric:
                  road_speed_limit_offset *= CV.KPH_TO_MPH
              limit_speed = self.nRoadLimitSpeed + road_speed_limit_offset
      if self.active_carrot <= 1:
          self.xSpdType = self.navType = self.xTurnInfo = self.xTurnInfoNext = -1
          self.nSdiType = self.nSdiBlockType = self.nSdiPlusBlockType = -1
          self.nTBTTurnType = self.nTBTTurnTypeNext = -1
          self.roadcate = 8
          self.nGoPosDist = 0
      if self.active_carrot <= 1 or self.active_kisa_count > 0:
          self.update_nav_instruction(sm)
      (rear_camera_speed, rear_camera_remaining) = self._rear_camera_speed(CS, delta_dist)
      if self.xSpdType < 0 or (self.xSpdType not in [100, 101] and self.xSpdDist <= 0) or (self.xSpdType in [100, 101] and self.xSpdDist < -250):
          self.xSpdType = -1
          self.xSpdDist = self.xSpdLimit = 0
      if self.xTurnInfo < 0 or self.xDistToTurn < -50:
          if self.xDistToTurn > 0:
              self.xDistToTurn = 0
          self.xTurnInfo = -1
          self.xDistToTurnNext = 0
          self.xTurnInfoNext = -1
      sdi_speed = 250
      vehicle_camera_speed = 250
      vehicle_speed_camera_active = CS is not None and self._vehicle_speed_camera_enabled(CS)
      vehicle_bump_active = CS is not None and self._vehicle_speed_bump_enabled(CS)
      vehicle_bump_speed = 250
      vehicle_school_zone_speed = 250
      vehicle_section_zone_speed = 250
      legacy_sdi_active = self.external_navigation_active and self.xSpdLimit > 0 and (self.xSpdDist > 0 or self.xSpdType in [100, 101]) and (self.active_carrot > 0) and (self.xSpdType != 22 or self._speed_bump_control_active(self.xSpdDist))
      if legacy_sdi_active:
          safe_sec = self.autoNaviSpeedBumpTime if self.xSpdType == 22 else self.autoNaviSpeedCtrlEnd
          decel = self.autoNaviSpeedDecelRate
          sdi_speed = min(sdi_speed, self.calculate_current_speed(self.xSpdDist, self.xSpdLimit, safe_sec, decel))
          self.active_carrot = 5 if self.xSpdType == 22 else 3
          if self.xSpdType == 4 or (self.xSpdType in [100, 101] and self.xSpdDist <= 0):
              sdi_speed = self.xSpdLimit
              self.active_carrot = 4
      if vehicle_speed_camera_active:
          vehicle_camera_speed = self.calculate_current_speed(CS.speedLimitDistance, CS.speedLimit * self.autoNaviSpeedSafetyFactor, self.autoNaviSpeedCtrlEnd, self.autoNaviSpeedDecelRate)
      if vehicle_bump_active:
          vehicle_bump_speed = self.calculate_current_speed(CS.speedBumpDistance, self.autoNaviSpeedBumpSpeed, self.autoNaviSpeedBumpTime, self.autoNaviSpeedDecelRate)
          self.active_carrot = 5
      if CS is not None:
          vehicle_school_zone_speed = self._vehicle_school_zone_speed(CS)
          if vehicle_school_zone_speed < 250:
              self.active_carrot = 6
          if self._vehicle_section_zone_enabled(CS):
              vehicle_section_zone_speed = CS.vehicleNaviSpeed * self.autoNaviSpeedSafetyFactor
              self.active_carrot = 4
      (atc_desired, self.atcType, self.atcSpeed, self.atcDist) = self.update_auto_turn(v_ego * 3.6, sm, self.xTurnInfo, self.xDistToTurn, True)
      (atc_desired_next, _, _, _) = self.update_auto_turn(v_ego * 3.6, sm, self.xTurnInfoNext, self.xDistToTurnNext, False)
      if self.nSdiType >= 0:
          pass
      else:
          pass
      if self.autoTurnControl not in [2, 3]:
          atc_desired = atc_desired_next = 250
      if self.autoTurnControl not in [1, 2]:
          self.atcType = 'none'
      rear_camera_holding = rear_camera_speed < 250 and rear_camera_speed <= sdi_speed
      sdi_speed = min(sdi_speed, rear_camera_speed)
      if rear_camera_holding:
          self.active_carrot = 3
      sdi_source = 'cam' if rear_camera_holding else 'bump' if self.xSpdType == 22 else 'section' if self.xSpdType == 4 else 'police' if self.xSpdType == 100 else 'waze' if self.xSpdType == 101 else 'cam'
      speed_n_sources = [(atc_desired, 'atc'), (atc_desired_next, 'atc2'), (sdi_speed, sdi_source), (vehicle_camera_speed, 'hda'), (vehicle_bump_speed, 'hda_bump'), (vehicle_school_zone_speed, 'school'), (vehicle_section_zone_speed, 'hda_section'), (limit_speed, 'road')]
      if self.turnSpeedControlMode in [1, 2]:
          speed_n_sources.append((max(abs(vturn_speed), self.autoCurveSpeedLowerLimit), 'vturn'))
      route_speed = max(route_speed * self.mapTurnSpeedFactor, self.autoCurveSpeedLowerLimit)
      if self.turnSpeedControlMode == 2:
          if -500 < self.xDistToTurn < 500:
              speed_n_sources.append((route_speed, 'route'))
      elif self.turnSpeedControlMode in [3, 4]:
          speed_n_sources.append((route_speed, 'route'))
      (desired_speed, source) = min(speed_n_sources, key=lambda x: x[0])
      if CS is not None:
          (desired_speed, source) = self._apply_speed_source_gas_floor(CS, desired_speed, source, v_ego_kph, road_speed_limit_changed)
          self.debugText += f'route={route_speed:.1f}'
      left_spd_sec = 100
      left_tbt_sec = 100
      speed_countdown_rearmed = False
      turn_countdown_rearmed = False
      if self.autoNaviCountDownMode > 0:
          speed_countdown_distance = self._speed_countdown_distance(CS)
          (left_spd_sec, self.speed_countdown_distance_last, speed_countdown_rearmed) = self._countdown_channel(speed_countdown_distance, self.speed_countdown_distance_last, self.left_spd_sec, v_ego)
          (left_tbt_sec, self.turn_countdown_distance_last, turn_countdown_rearmed) = self._countdown_channel(self.xDistToTurn, self.turn_countdown_distance_last, self.left_tbt_sec, v_ego)
      else:
          self.speed_countdown_distance_last = 0.0
          self.turn_countdown_distance_last = 0.0
      self.left_spd_sec = left_spd_sec
      self.left_tbt_sec = left_tbt_sec
      left_sec = 100 if navigation_source_changed or speed_countdown_rearmed or turn_countdown_rearmed else min(left_spd_sec, left_tbt_sec)
      self._update_countdown_alert(left_sec, source, v_ego_kph)
      self._update_cmd()
      msg = messaging.new_message('carrotMan')
      msg.valid = True
      msg.carrotMan.activeCarrot = self.active_carrot
      msg.carrotMan.nRoadLimitSpeed = int(self.nRoadLimitSpeed)
      msg.carrotMan.remote = remote_ip
      msg.carrotMan.xSpdType = int(self.xSpdType)
      msg.carrotMan.xSpdLimit = int(self.xSpdLimit)
      msg.carrotMan.xSpdDist = int(self.xSpdDist)
      msg.carrotMan.xSpdCountDown = int(left_spd_sec)
      msg.carrotMan.xTurnInfo = int(self.xTurnInfo)
      msg.carrotMan.xDistToTurn = int(self.xDistToTurn)
      msg.carrotMan.xTurnCountDown = int(left_tbt_sec)
      msg.carrotMan.atcType = self.atcType
      msg.carrotMan.vTurnSpeed = int(vturn_speed)
      msg.carrotMan.szPosRoadName = f'{self.szPosRoadName} {self.debugText}'.strip()
      msg.carrotMan.szTBTMainText = self.szTBTMainText
      msg.carrotMan.desiredSpeed = int(desired_speed)
      msg.carrotMan.desiredSource = source
      (vehicle_navi_active, vehicle_navi_speed, vehicle_navi_section_active) = self._vehicle_navigation_display(CS)
      msg.carrotMan.vehicleNaviActive = vehicle_navi_active
      msg.carrotMan.vehicleNaviSpeed = vehicle_navi_speed
      msg.carrotMan.vehicleNaviSectionActive = vehicle_navi_section_active
      msg.carrotMan.vehicleNaviAvailable = bool(getattr(CS, 'vehicleNaviAvailable', False))
      msg.carrotMan.carrotCmdIndex = int(self.carrotCmdIndex)
      msg.carrotMan.carrotCmd = self.carrotCmd
      msg.carrotMan.carrotArg = self.carrotArg
      msg.carrotMan.trafficState = self.traffic_state
      msg.carrotMan.xPosSpeed = float(v_ego_kph)
      msg.carrotMan.xPosAngle = float(self.bearing)
      msg.carrotMan.xPosLat = float(self.vpPosPointLat)
      msg.carrotMan.positionFixMonoTime = max(0, int(self.last_calculate_gps_time * 1000000000.0))
      msg.carrotMan.positionSource = getattr(self, 'position_source', 'none')
      msg.carrotMan.positionHeadingValid = getattr(self, 'position_heading_valid', False)
      msg.carrotMan.positionMonoTime = max(0, int(self.position_mono_time * 1000000000.0))
      msg.carrotMan.xPosLon = float(self.vpPosPointLon)
      msg.carrotMan.nGoPosDist = self.nGoPosDist
      msg.carrotMan.nGoPosTime = self.nGoPosTime
      msg.carrotMan.szSdiDescr = self._get_sdi_descr(-1 if self.nSdiType == 0 and self.nSdiDist == 0 else self.nSdiType)
      if rear_camera_holding and source == 'cam':
          label = {'ko': '후면단속 속도 유지', 'en': 'Rear camera speed hold', 'zh': '后向测速限速保持'}.get(self.lang, 'Rear camera speed hold')
          msg.carrotMan.szSdiDescr = f'{label} {math.ceil(rear_camera_remaining)}m'
      coords_str = ';'.join([f'{x:.2f},{y:.2f},{d:.2f}' for ((x, y), d) in zip(coords, distances, strict=False)])
      msg.carrotMan.naviPaths = coords_str
      msg.carrotMan.leftSec = int(self.carrot_left_sec)
      pm.send('carrotMan', msg)
      inst = messaging.new_message('navInstructionCarrot')
      if self.active_carrot > 1 and self.active_kisa_count <= 0:
          inst.valid = True
          instruction = inst.navInstructionCarrot
          instruction.distanceRemaining = self.nGoPosDist
          instruction.timeRemaining = self.nGoPosTime
          instruction.speedLimit = self.nRoadLimitSpeed / 3.6 if self.nRoadLimitSpeed > 0 else 0
          instruction.maneuverDistance = float(self.nTBTDist)
          instruction.maneuverSecondaryText = self.szNearDirName
          if self.szFarDirName and len(self.szFarDirName):
              instruction.maneuverSecondaryText += '[{}]'.format(self.szFarDirName)
          instruction.maneuverPrimaryText = self.szTBTMainText
          instruction.timeRemainingTypical = self.nGoPosTime
          (navType, navModifier, xTurnInfo1) = ('invalid', '', -1)
          if self.nTBTTurnType in nav_type_mapping:
              (navType, navModifier, xTurnInfo1) = nav_type_mapping[self.nTBTTurnType]
          (navTypeNext, navModifierNext, xTurnInfoNext) = ('invalid', '', -1)
          if self.nTBTTurnTypeNext in nav_type_mapping:
              (navTypeNext, navModifierNext, xTurnInfoNext) = nav_type_mapping[self.nTBTTurnTypeNext]
          instruction.maneuverType = navType
          instruction.maneuverModifier = navModifier
          maneuvers = []
          if self.nTBTTurnType >= 0:
              maneuver = {}
              maneuver['distance'] = float(self.xDistToTurn)
              maneuver['type'] = navType
              maneuver['modifier'] = navModifier
              maneuvers.append(maneuver)
              if self.nTBTDistNext >= self.nTBTDist:
                  maneuver = {}
                  maneuver['distance'] = float(self.nTBTDistNext)
                  maneuver['type'] = navTypeNext
                  maneuver['modifier'] = navModifierNext
                  maneuvers.append(maneuver)
          instruction.allManeuvers = maneuvers
      elif sm.alive['navInstruction'] and sm.valid['navInstruction']:
          inst.navInstructionCarrot = sm['navInstruction']
      pm.send('navInstructionCarrot', inst)
