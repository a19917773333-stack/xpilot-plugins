# Adapted from jixiexiaoge/carrot 3615bf4 (MIT; see ../CARROT-LICENSE).
from __future__ import annotations
from .common import math, np, time, json, collections, CV, MyMovingAverage, GPSSources, messaging
from .control import CarrotNaviControl, parse_carrot_navi_control
from .constants import COUNTDOWN_NEW_TARGET_MIN_JUMP_M, SCHOOL_ZONE_GAS_OVERRIDE_TIMEOUT_S, nav_type_mapping

class Part1:
  def _update_school_zone_gas_override(self, override_active):
      if not override_active:
          self.school_zone_gas_override_started_at = None
          return
      now = time.monotonic()
      if self.school_zone_gas_override_started_at is None:
          self.school_zone_gas_override_started_at = now
      elif now - self.school_zone_gas_override_started_at >= SCHOOL_ZONE_GAS_OVERRIDE_TIMEOUT_S:
          self.school_zone_suppressed = True

  def _apply_speed_source_gas_floor(self, CS, desired_speed, source, v_ego_kph, road_speed_limit_changed):
      speed_event_gas_rising = CS.gasPressed and (not self.speed_event_gas_pressed)
      self.speed_event_gas_pressed = CS.gasPressed
      if source in ('hda', 'hda_section', 'hda_bump', 'school'):
          gas_floor_active = source == 'hda_bump' or self.vehicleSpeedCameraControlMode == 2
          if not gas_floor_active:
              self.gas_override_speed = 0
          else:
              reset_floor = source != self.source_last or CS.vEgo < 0.1 or desired_speed > 150 or CS.brakePressed or road_speed_limit_changed
              if reset_floor:
                  self.gas_override_speed = 0
              if self.gas_override_speed <= 0:
                  if speed_event_gas_rising and (not CS.brakePressed) and (CS.vEgo >= 0.1) and (desired_speed <= 150) and (desired_speed < v_ego_kph):
                      self.gas_override_speed = v_ego_kph
              elif CS.gasPressed:
                  self.gas_override_speed = max(v_ego_kph, self.gas_override_speed)
          self.source_last = source
          override_active = gas_floor_active and desired_speed < self.gas_override_speed
          if source == 'school':
              self._update_school_zone_gas_override(override_active)
          elif not self.school_zone_suppressed:
              self.school_zone_gas_override_started_at = None
          if override_active:
              return (self.gas_override_speed, 'gas')
          return (desired_speed, source)
      if source != self.source_last:
          self.gas_override_speed = 0
          self.gas_pressed_state = CS.gasPressed
      reset_floor = CS.vEgo < 0.1 or desired_speed > 150 or source in ['cam', 'section', 'police'] or CS.brakePressed or road_speed_limit_changed
      if reset_floor:
          self.gas_override_speed = 0
      elif source == 'bump':
          if self.gas_override_speed <= 0:
              if speed_event_gas_rising and desired_speed < v_ego_kph:
                  self.gas_override_speed = v_ego_kph
          elif CS.gasPressed:
              self.gas_override_speed = max(v_ego_kph, self.gas_override_speed)
      elif CS.gasPressed and (not self.gas_pressed_state):
          self.gas_override_speed = max(v_ego_kph, self.gas_override_speed)
      else:
          self.gas_pressed_state = False
      self.source_last = source
      if desired_speed < self.gas_override_speed:
          return (self.gas_override_speed, 'gas')
      return (desired_speed, source)

  def _update_tbt(self):
      turn_type_mapping = {12: ('turn', 'left', 1), 16: ('turn', 'sharp left', 1), 13: ('turn', 'right', 2), 19: ('turn', 'sharp right', 2), 102: ('off ramp', 'slight left', 3), 105: ('off ramp', 'slight left', 3), 112: ('off ramp', 'slight left', 3), 115: ('off ramp', 'slight left', 3), 101: ('off ramp', 'slight right', 4), 104: ('off ramp', 'slight right', 4), 111: ('off ramp', 'slight right', 4), 114: ('off ramp', 'slight right', 4), 7: ('fork', 'left', 3), 44: ('fork', 'left', 3), 17: ('fork', 'left', 3), 75: ('fork', 'left', 3), 76: ('fork', 'left', 3), 118: ('fork', 'left', 3), 6: ('fork', 'right', 4), 43: ('fork', 'right', 4), 73: ('fork', 'right', 4), 74: ('fork', 'right', 4), 123: ('fork', 'right', 4), 124: ('fork', 'right', 4), 117: ('fork', 'right', 4), 131: ('rotary', 'slight right', 5), 132: ('rotary', 'slight right', 5), 140: ('rotary', 'slight left', 5), 141: ('rotary', 'slight left', 5), 133: ('rotary', 'right', 5), 134: ('rotary', 'sharp right', 5), 135: ('rotary', 'sharp right', 5), 136: ('rotary', 'sharp left', 5), 137: ('rotary', 'sharp left', 5), 138: ('rotary', 'sharp left', 5), 139: ('rotary', 'left', 5), 142: ('rotary', 'straight', 5), 14: ('turn', 'uturn', 7), 201: ('arrive', 'straight', 8), 51: ('notification', 'straight', 0), 52: ('notification', 'straight', 0), 53: ('notification', 'straight', 0), 54: ('notification', 'straight', 0), 55: ('notification', 'straight', 0), 153: ('', '', 6), 154: ('', '', 6), 249: ('', '', 6)}
      if self.nTBTTurnType in turn_type_mapping:
          (self.navType, self.navModifier, self.xTurnInfo) = turn_type_mapping[self.nTBTTurnType]
      else:
          (self.navType, self.navModifier, self.xTurnInfo) = ('invalid', '', -1)
      if self.nTBTTurnTypeNext in turn_type_mapping:
          (self.navTypeNext, self.navModifierNext, self.xTurnInfoNext) = turn_type_mapping[self.nTBTTurnTypeNext]
      else:
          (self.navTypeNext, self.navModifierNext, self.xTurnInfoNext) = ('invalid', '', -1)
      if self.nTBTDist > 0 and self.xTurnInfo > 0:
          self.xDistToTurn = self.nTBTDist
      if self.nTBTDistNext > 0 and self.xTurnInfoNext > 0:
          self.xDistToTurnNext = self.nTBTDistNext + self.nTBTDist

  def _get_sdi_descr(self, nSdiType):
      sdi_ko = {75: '후면 과속 단속', 76: '후면 신호·과속 단속', 0: '신호과속', 1: '과속 (고정식)', 2: '구간단속 시작', 3: '구간단속 끝', 4: '구간단속중', 5: '꼬리물기단속카메라', 6: '신호 단속', 7: '과속 (이동식)', 8: '고정식 과속위험 구간(박스형)', 9: '버스전용차로구간', 10: '가변 차로 단속', 11: '갓길 감시 지점', 12: '끼어들기 금지', 13: '교통정보 수집지점', 14: '방범용cctv', 15: '과적차량 위험구간', 16: '적재 불량 단속', 17: '주차단속 지점', 18: '일방통행도로', 19: '철길 건널목', 20: '어린이 보호구역(스쿨존 시작 구간)', 21: '어린이 보호구역(스쿨존 끝 구간)', 22: '과속방지턱', 23: 'lpg충전소', 24: '터널 구간', 25: '휴게소', 26: '톨게이트', 27: '안개주의 지역', 28: '유해물질 지역', 29: '사고다발', 30: '급커브지역', 31: '급커브구간1', 32: '급경사구간', 33: '야생동물 교통사고 잦은 구간', 34: '우측시야불량지점', 35: '시야불량지점', 36: '좌측시야불량지점', 37: '신호위반다발구간', 38: '과속운행다발구간', 39: '교통혼잡지역', 40: '방향별차로선택지점', 41: '무단횡단사고다발지점', 42: '갓길 사고 다발 지점', 43: '과속 사발 다발 지점', 44: '졸음 사고 다발 지점', 45: '사고다발지점', 46: '보행자 사고다발지점', 47: '차량도난사고 상습발생지점', 48: '낙석주의지역', 49: '결빙주의지역', 50: '병목지점', 51: '합류 도로', 52: '추락주의지역', 53: '지하차도 구간', 54: '주택밀집지역(교통진정지역)', 55: '인터체인지', 56: '분기점', 57: '휴게소(lpg충전가능)', 58: '교량', 59: '제동장치사고다발지점', 60: '중앙선침범사고다발지점', 61: '통행위반사고다발지점', 62: '목적지 건너편 안내', 63: '졸음 쉼터 안내', 64: '노후경유차단속', 65: '터널내 차로변경단속', 66: ''}
      sdi_en = {75: 'Rear speed camera', 76: 'Rear signal and speed camera', 0: 'Signal speed enforcement', 1: 'Speed camera (fixed)', 2: 'Section control start', 3: 'Section control end', 4: 'Under section control', 5: 'Block-the-box camera', 6: 'Signal violation enforcement', 7: 'Speed camera (mobile)', 8: 'Fixed speed camera zone (box)', 9: 'Bus-only lane zone', 10: 'Reversible/variable lane enforcement', 11: 'Shoulder surveillance point', 12: 'No cut-in', 13: 'Traffic data collection point', 14: 'Security CCTV', 15: 'Overloaded vehicle risk zone', 16: 'Improper loading enforcement', 17: 'Parking enforcement point', 18: 'One-way road', 19: 'Railroad crossing', 20: 'School zone start', 21: 'School zone end', 22: 'Speed bump', 23: 'LPG station', 24: 'Tunnel section', 25: 'Rest area', 26: 'Toll gate', 27: 'Fog caution area', 28: 'Hazardous materials area', 29: 'Accident-prone section', 30: 'Sharp curve area', 31: 'Sharp curve section 1', 32: 'Steep slope section', 33: 'Wild animal crossing area', 34: 'Poor visibility (right)', 35: 'Poor visibility', 36: 'Poor visibility (left)', 37: 'Frequent signal violations', 38: 'Frequent speeding', 39: 'Traffic congestion area', 40: 'Lane selection by direction', 41: 'Frequent jaywalking accidents', 42: 'Frequent shoulder accidents', 43: 'Frequent speeding accidents', 44: 'Frequent drowsy driving accidents', 45: 'Accident-prone spot', 46: 'Frequent pedestrian accidents', 47: 'Frequent vehicle theft', 48: 'Falling rock caution area', 49: 'Icy road caution area', 50: 'Bottleneck point', 51: 'Merging road', 52: 'Cliff/Drop caution area', 53: 'Underpass section', 54: 'Residential area (traffic calming)', 55: 'Interchange', 56: 'Junction', 57: 'Rest area (LPG available)', 58: 'Bridge', 59: 'Frequent brake failure accidents', 60: 'Center line invasion accidents', 61: 'Violation-of-passage accidents', 62: 'Destination on opposite side', 63: 'Drowsy rest area', 64: 'Old diesel control', 65: 'Lane change enforcement in tunnel', 66: ''}
      sdi_zh = {75: '后向测速摄像头', 76: '后向闯红灯及测速摄像头', 0: '信号测速/闯灯拍照', 1: '固定测速摄像头', 2: '区间测速开始', 3: '区间测速结束', 4: '区间测速中', 5: '路口压线摄像头', 6: '闯红灯拍照', 7: '流动测速摄像头', 8: '测速拍照', 9: '公交专用车道区间', 10: '可变/潮汐车道拍照', 11: '应急车道拍照', 12: '禁止加塞', 13: '交通信息采集点', 14: '治安监控', 15: '超载车辆风险区', 16: '装载不当拍照', 17: '违停拍照点', 18: '单行道', 19: '铁路道口', 20: '学校区域开始', 21: '学校区域结束', 22: '减速带', 23: 'LPG加气站', 24: '隧道区间', 25: '服务区', 26: 'ETC计费拍照', 27: '多雾路段', 28: '危险品区域', 29: '事故多发路段', 30: '急弯路段', 31: '急弯区段1', 32: '陡坡路段', 33: '野生动物出没路段', 34: '右侧视野不良点', 35: '视野不良点', 36: '左侧视野不良点', 37: '闯红灯多发', 38: '超速多发', 39: '交通拥堵区域', 40: '按方向选择车道点', 41: '行人乱穿马路多发处', 42: '应急车道事故多发', 43: '超速事故多发', 44: '疲劳驾驶事故多发', 45: '事故多发点', 46: '行人事故多发点', 47: '车辆盗窃多发点', 48: '落石危险路段', 49: '路面结冰危险', 50: '瓶颈路段', 51: '汇入道路', 52: '坠落危险路段', 53: '地下车道区间', 54: '居民区（交通缓和）', 55: '立交', 56: '分岔点', 57: '服务区（可加气）', 58: '桥梁', 59: '制动故障事故多发点', 60: '越线事故多发点', 61: '违法通行事故多发点', 62: '目的地在对面', 63: '瞌睡停车区', 64: '老旧柴油车管制', 65: '隧道内变道拍照', 66: ''}
      sdi_map = sdi_en
      if self.lang == 'ko':
          sdi_map = sdi_ko
      elif self.lang == 'zh':
          sdi_map = sdi_zh
      return sdi_map.get(nSdiType, '')

  def _update_sdi(self):
      if self.nSdiType in [0, 1, 2, 3, 4, 7, 8, 75, 76] and self.nSdiSpeedLimit > 0 and (self.autoNaviSpeedCtrlMode > 0):
          self.xSpdLimit = self.nSdiSpeedLimit * self.autoNaviSpeedSafetyFactor
          self.xSpdDist = self.nSdiDist
          self.xSpdType = self.nSdiType
          if self.nSdiBlockType in [2, 3]:
              self.xSpdDist = self.nSdiBlockDist
              self.xSpdType = 4
          elif self.nSdiType == 7 and self.autoNaviSpeedCtrlMode < 3:
              self.xSpdLimit = self.xSpdDist = 0
      elif (self.nSdiPlusType == 22 or self.nSdiType == 22) and self.roadcate > 1 and (self.autoNaviSpeedCtrlMode >= 2):
          self.xSpdLimit = self.autoNaviSpeedBumpSpeed
          self.xSpdDist = self.nSdiPlusDist if self.nSdiPlusType == 22 else self.nSdiDist
          self.xSpdType = 22
      else:
          self.xSpdLimit = 0
          self.xSpdType = -1
          self.xSpdDist = 0

  def _reset_carrot_navi_sequences(self, session_id):
      self.rear_camera_events = []
      self.carrot_navi_session_id = session_id
      self.carrot_navi_speed_sequence = -1
      self.carrot_navi_current_sequence = -1
      self.carrot_navi_next_sequence = -1
      self.carrot_navi_vehicle_sequence = -1
      self.carrot_navi_route_sequence = -1

  def _clear_carrot_navi_traffic(self):
      if not getattr(self, 'carrot_navi_traffic_active', False):
          return
      params_memory = getattr(self, 'params_memory', None)
      if params_memory is not None:
          try:
              params_memory.remove('TrafficLight')
          except Exception:
              pass
      self.carrot_navi_traffic_active = False

  def _clear_carrot_navi_control(self):
      self.rear_camera_events = []
      self.active_count = 0
      self.active_sdi_count = 0
      self.carrot_navi_has_control = False
      self.carrot_navi_road_limit_valid = False
      self.carrot_navi_off_route = False
      self.carrot_navi_control = None
      self._reset_carrot_navi_sequences('')
      self.nSdiType = self.nSdiBlockType = self.nSdiPlusType = self.nSdiPlusBlockType = -1
      self.nSdiSection = -1
      self.nSdiSpeedLimit = self.nSdiDist = 0
      self.nSdiBlockSpeed = self.nSdiBlockDist = 0
      self.nSdiPlusSpeedLimit = self.nSdiPlusDist = 0
      self.nSdiPlusBlockSpeed = self.nSdiPlusBlockDist = 0
      self.xSpdType = -1
      self.xSpdLimit = self.xSpdDist = 0
      self.nTBTTurnType = self.nTBTTurnTypeNext = -1
      self.nTBTDist = self.nTBTDistNext = 0
      self.xTurnInfo = self.xTurnInfoNext = -1
      self.xDistToTurn = self.xDistToTurnNext = 0
      self.navType = self.navTypeNext = 'invalid'
      self.navModifier = self.navModifierNext = ''
      self.nGoPosDist = self.nGoPosTime = 0
      self.last_update_gps_time_navi = 0
      self._gps_sources().remove('external_navi')
      self.szPosRoadName = ''
      self._clear_carrot_navi_traffic()

  def _apply_carrot_navi_speed(self, navi: CarrotNaviControl):
      speed = navi.speed
      self.carrot_navi_road_limit_valid = speed.road_limit_kph is not None
      if speed.road_limit_kph is not None:
          self.nRoadLimitSpeed = speed.road_limit_kph
      if speed.section_active:
          self.nSdiType = 4
          self.nSdiSpeedLimit = speed.section_speed_limit_kph
          self.nSdiDist = speed.section_remaining_distance_m
          self.nSdiSection = 1
          self.nSdiBlockType = 2
          self.nSdiBlockSpeed = speed.section_speed_limit_kph
          self.nSdiBlockDist = speed.section_remaining_distance_m
      elif speed.sdi_present:
          self.nSdiType = speed.sdi_type
          self.nSdiSpeedLimit = speed.sdi_speed_limit_kph
          self.nSdiDist = speed.sdi_distance_m
          self.nSdiSection = speed.sdi_section_type
          self.nSdiBlockType = speed.sdi_block_type
          self.nSdiBlockSpeed = speed.sdi_block_speed_kph
          self.nSdiBlockDist = speed.sdi_block_distance_m
      else:
          self.nSdiType = -1
          self.nSdiSpeedLimit = 0
          self.nSdiDist = 0
          self.nSdiSection = -1
          self.nSdiBlockType = -1
          self.nSdiBlockSpeed = 0
          self.nSdiBlockDist = 0
      if speed.secondary_sdi_present:
          self.nSdiPlusType = speed.secondary_sdi_type
          self.nSdiPlusSpeedLimit = speed.secondary_sdi_speed_limit_kph
          self.nSdiPlusDist = speed.secondary_sdi_distance_m
          self.nSdiPlusBlockType = speed.secondary_sdi_block_type
          self.nSdiPlusBlockSpeed = speed.secondary_sdi_block_speed_kph
          self.nSdiPlusBlockDist = speed.secondary_sdi_block_distance_m
      else:
          self.nSdiPlusType = -1
          self.nSdiPlusSpeedLimit = 0
          self.nSdiPlusDist = 0
          self.nSdiPlusBlockType = -1
          self.nSdiPlusBlockSpeed = 0
          self.nSdiPlusBlockDist = 0
      self._update_sdi()

  def _apply_carrot_navi_vehicle(self, navi: CarrotNaviControl):
      vehicle = navi.vehicle
      if not vehicle.present:
          self.last_update_gps_time_navi = 0
          self._gps_sources().remove('external_navi')
          self.szPosRoadName = ''
          return
      if vehicle.sequence == self.carrot_navi_vehicle_sequence:
          return
      now = time.monotonic()
      received = vehicle.received_mono_time_ns / 1000000000.0 if vehicle.received_mono_time_ns else now
      if received > now:
          return
      self.carrot_navi_vehicle_sequence = vehicle.sequence
      self.vpPosPointLatNavi = vehicle.latitude
      self.vpPosPointLonNavi = vehicle.longitude
      self.nPosAngle = vehicle.heading_deg
      self.nPosSpeed = vehicle.speed_kph
      self.szPosRoadName = vehicle.road_name
      self.last_update_gps_time_navi = self.last_calculate_gps_time = received
      self._gps_sources().put('external_navi', vehicle.latitude, vehicle.longitude, vehicle.heading_deg, vehicle.speed_kph / 3.6, received)

  def _apply_carrot_navi_route(self, navi: CarrotNaviControl):
      route = navi.route
      self.carrot_navi_route_sequence = route.sequence
      self.nGoPosDist = route.remaining_distance_m if route.present else 0
      self.nGoPosTime = route.remaining_time_sec if route.present else 0

  def _apply_carrot_navi_traffic(self, navi: CarrotNaviControl):
      traffic = navi.traffic
      if not traffic.present or not traffic.visible or (not traffic.lamp) or (traffic.remain_sec <= 0):
          self._clear_carrot_navi_traffic()
          return
      params_memory = getattr(self, 'params_memory', None)
      if params_memory is None:
          return
      value = {'distance': traffic.distance_m, 'lamp': traffic.lamp, 'remain': traffic.remain_sec, 'source': traffic.source, 'ts': time.monotonic()}
      try:
          params_memory.put_nonblocking('TrafficLight', json.dumps(value))
          self.carrot_navi_traffic_active = True
      except Exception:
          pass

  def _apply_carrot_navi_guidance(self, navi: CarrotNaviControl, force=False):
      current = navi.current
      current_changed = force or current.sequence != self.carrot_navi_current_sequence
      next_guidance = navi.next
      next_changed = force or next_guidance.sequence != self.carrot_navi_next_sequence
      if not current_changed and (not next_changed):
          return
      old_current_dist = self.xDistToTurn
      old_next_dist = self.xDistToTurnNext
      if current_changed:
          self.carrot_navi_current_sequence = current.sequence
          self.nTBTDist = current.distance_m if current.present else 0
          self.nTBTTurnType = current.turn_type if current.present else -1
          self.szTBTMainText = current.main_text if current.present else ''
          self.szNearDirName = current.near_direction if current.present else ''
          self.szFarDirName = current.far_direction if current.present else ''
      if next_changed:
          self.carrot_navi_next_sequence = next_guidance.sequence
          self.nTBTDistNext = next_guidance.distance_m if next_guidance.present else 0
          self.nTBTTurnTypeNext = next_guidance.turn_type if next_guidance.present else -1
          self.szTBTMainTextNext = next_guidance.main_text if next_guidance.present else ''
      self._update_tbt()
      if not current_changed:
          self.xDistToTurn = old_current_dist
      if not next_changed:
          self.xDistToTurnNext = old_next_dist

  def _update_carrot_navi(self, sm):
      service_active = sm.alive['carrotNavi'] and sm.valid['carrotNavi']
      if service_active and (not sm.updated['carrotNavi']):
          if self.carrot_navi_active and self.carrot_navi_has_control:
              self.active_count = 80
              self.active_sdi_count = self.active_sdi_count_max
          return self.carrot_navi_active and self.carrot_navi_has_control
      navi = parse_carrot_navi_control(sm['carrotNavi']) if service_active else None
      was_active = self.carrot_navi_active
      self.carrot_navi_active = navi is not None
      if navi is None:
          if was_active:
              self._clear_carrot_navi_control()
          return False
      self.carrot_navi_control = navi
      new_session = navi.session_id != self.carrot_navi_session_id
      if navi.session_id != self.carrot_navi_session_id:
          self._reset_carrot_navi_sequences(navi.session_id)
      off_route_changed = navi.off_route != self.carrot_navi_off_route
      self.carrot_navi_off_route = navi.off_route
      self.carrot_navi_road_limit_valid = navi.speed.road_limit_kph is not None
      self.carrot_navi_has_control = navi.speed.present or navi.current.present or navi.next.present or navi.guidance_active or navi.route.present
      if new_session or off_route_changed or navi.speed.sequence != self.carrot_navi_speed_sequence:
          self.carrot_navi_speed_sequence = navi.speed.sequence
          self._apply_carrot_navi_speed(navi)
      self._apply_carrot_navi_vehicle(navi)
      self._apply_carrot_navi_traffic(navi)
      if new_session or navi.route.sequence != self.carrot_navi_route_sequence:
          self._apply_carrot_navi_route(navi)
      if navi.road_category is not None:
          self.roadcate = navi.road_category
      self._apply_carrot_navi_guidance(navi, force=new_session or off_route_changed)
      if self.carrot_navi_has_control:
          self.active_count = 80
          self.active_sdi_count = self.active_sdi_count_max
      return self.carrot_navi_has_control

  def _gps_sources(self):
      if not hasattr(self, 'gps_sources'):
          self.gps_sources = GPSSources()
      return self.gps_sources
