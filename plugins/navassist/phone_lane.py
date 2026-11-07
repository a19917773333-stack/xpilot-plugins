"""Frame-bound CP phone lane candidates. Single-frame estimates; no model-only absolute lane promotion."""
from .phone import bounded_json, OBSERVATION_PATH

MIN_PLANNING_SAMPLES = 3


def read_observation():
  try:
    return bounded_json(OBSERVATION_PATH)
  except (OSError,ValueError,TypeError,RecursionError):
    return None


class PhoneLaneEvidence:
  def __init__(self):
    self.identity = None
    self.stream = None
    self.last_stamp = -1
    self.last_frame = -1
    self.key = None
    self.samples = 0

  def update(self, record, nav, now_ns, *, enabled=False):
    unknown = dict(valid=False,laneNumber=None,laneCount=None,absoluteConfirmed=False,
                   source='cpPhoneVision',scope='visibleCorridor',samples=0,controlEligible=False)
    identity = (nav.get('sessionId'),nav.get('routeRevision'))
    if not enabled or not nav.get('valid') or not identity[0] or identity != self.identity:
      previous = (self.last_stamp, self.last_frame, self.stream)
      self.__init__()
      self.last_stamp, self.last_frame, self.stream = previous
      self.identity = identity
      if not enabled or not nav.get('valid') or not identity[0]:return unknown
    def reject():
      self.key,self.samples=None,0
      return unknown
    if not isinstance(record,dict):return reject()
    stamp,frame,stream = (record.get(k) for k in ('updated_mono_ns','frame_id','stream_id'))
    lane=record.get('lane_cp')
    if (type(record.get('version')) is not int or record.get('version') != 1 or record.get('source') != 'tesnav-phone'
        or record.get('valid') is not True or record.get('control_eligible') is not False
        or type(stamp) is not int or not 0 <= now_ns-stamp <= 800_000_000
        or type(frame) is not int or frame < 0 or not isinstance(stream,str) or not 8 <= len(stream) <= 128
        or not isinstance(lane,dict)):
      return reject()
    if self.stream is not None and stream != self.stream:
      self.key,self.samples=None,0
      if stamp <= self.last_stamp:return reject()
      self.last_frame=-1
    self.stream=stream
    if any(type(lane.get(k)) is not int for k in ('version','leftClass','rightClass','laneNumber','laneCount')):
      return reject()
    left,right=lane['leftClass'],lane['rightClass']
    if (lane['version'] != 1 or not 1 <= left <= 3 or not 1 <= right <= 3
        or lane['laneNumber'] != left or lane['laneCount'] != left+right-1
        or lane.get('scope') != 'visibleCorridor' or lane.get('control_eligible') is not False
        or lane.get('model') not in ('vlaneDay.mnn','vlaneNight.mnn')):
      return reject()
    if stamp < self.last_stamp or frame < self.last_frame:return reject()
    if (stamp == self.last_stamp) != (frame == self.last_frame):return reject()
    key=(left,right,lane['model'])
    if stamp != self.last_stamp and frame > self.last_frame:
      self.samples=self.samples+1 if key==self.key and stamp-self.last_stamp<=800_000_000 else 1
      self.key,self.last_stamp,self.last_frame=key,stamp,frame
    elif key != self.key:return reject()
    return dict(unknown,valid=True,laneNumber=left,laneCount=left+right-1,
                samples=self.samples,captureMonoNs=stamp,frameId=frame,streamId=stream,model=lane['model'])


def planning_index(candidate, nav, *, enabled=False):
  """Use a route-matched estimate for planning, without declaring it absolute."""
  if not enabled or not nav.get('valid') or not candidate.get('valid'):
    return None
  count, index = candidate.get('laneCount'), candidate.get('laneNumber')
  if type(count) is not int or type(index) is not int or not 1 <= index <= count <= 5:
    return None
  # 单帧估计不足以驱动变道：要求连续多帧一致，避免模型偶发误判把车并到错误车道。
  samples = candidate.get('samples')
  if type(samples) is not int or samples < MIN_PLANNING_SAMPLES:
    return None
  # 高德多数时候不给 laneTotalCount；缺省时信任手机的车道总数，只有两边都给出且矛盾才拒绝。
  total = nav.get('laneTotalCount')
  if type(total) is int and total > 0 and count != total:
    return None
  return index-1
