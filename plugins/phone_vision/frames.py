from __future__ import annotations
import time,json,math,threading,secrets,hashlib,base64
from pathlib import Path
from .limits import MAX_AGE_NS
from .lane import validate as validate_lane
from collections import OrderedDict
import os

def read_observation(path, now_ns):
  """Read-only observer: process death cannot leave a permanently fresh result."""
  unavailable = {'valid': False, 'status': 'unknown', 'control_eligible': False,
                 'reason': 'missing_malformed_or_stale', 'left': None, 'right': None}
  try:
    with Path(path).open() as f:
      raw = f.read(16_385)
    if len(raw) > 16_384:
      return unavailable
    data = json.loads(raw)
    if not isinstance(data, dict):
      return unavailable
    stamp = data.get('updated_mono_ns')
    if (data.get('valid') is not True or data.get('control_eligible') is not False or
        type(stamp) is not int or not 0 <= now_ns-stamp <= MAX_AGE_NS):
      return unavailable
    return dict(data, status='observation_only')
  except (OSError, ValueError, TypeError):
    return unavailable


class FrameStore:
  def __init__(self, output: Path, clock=time.monotonic_ns):
    self.output, self.clock = output, clock
    self.lock = threading.Lock()
    self.condition = threading.Condition(self.lock)
    self.frame_requested = threading.Event()
    self.last_encoded_at = float("-inf")
    self.last_issued_generation = 0
    self.generation = 0
    self.camera_capture_ns = 0
    self.latest = None
    self.stream_id = secrets.token_hex(16)
    self.issued = OrderedDict()
    self.last_accepted_capture = -1
    self.last_result = None
    self._unavailable_reason = None
    self._invalidate('starting')

  def _persist(self, result):
    self.output.parent.mkdir(parents=True, exist_ok=True)
    tmp = self.output.with_suffix('.tmp')
    tmp.write_text(json.dumps(result, allow_nan=False))
    os.replace(tmp, self.output)

  def _invalidate(self, reason):
    if self._unavailable_reason == reason:
      return
    self._unavailable_reason = reason
    self._persist(dict(version=1, source='tesnav-phone', valid=False,
                       status='unknown', reason=reason, stream_id=self.stream_id,
                       updated_mono_ns=max(0, self.last_accepted_capture),
                       checked_mono_ns=self.clock(), left=None, right=None,
                       experimental=True, control_eligible=False))

  def expire(self):
    with self.lock:
      now = self.clock()
      if not self.camera_capture_ns or not 0 <= now-self.camera_capture_ns <= MAX_AGE_NS:
        self._invalidate('camera_unavailable_or_stale')
      elif self.last_result is None or not 0 <= now-self.last_accepted_capture <= MAX_AGE_NS:
        self._invalidate('phone_result_unavailable_or_stale')

  def claim_capture(self, now, hz):
    if not self.frame_requested.is_set() or now-self.last_encoded_at < 1/hz:
      return False
    self.frame_requested.clear()
    self.last_encoded_at = now
    return True

  def camera_seen(self, capture_ns):
    with self.lock:
      self.camera_capture_ns = capture_ns

  def publish(self, frame):
    with self.condition:
      self.latest = frame
      self.camera_capture_ns = frame['capture_mono_ns']
      self.generation += 1
      self.condition.notify_all()

  def new_stream(self):
    with self.lock:
      self.stream_id = secrets.token_hex(16)
      self.issued.clear()
      self.latest = None
      self.camera_capture_ns = 0
      self.last_result = None
      self._invalidate('camera_restarting')

  def issue(self, fresh=False, timeout=.5, buffered=False):
    started_ns = self.clock()
    with self.condition:
      if fresh:
        generation = self.generation
        # One unused, young prefetch may be delivered immediately. Never serve
        # the same generation twice, or keep streaming JPEGs without requests.
        age = self.clock()-self.latest['capture_mono_ns'] if self.latest is not None else -1
        ready = buffered and self.generation > self.last_issued_generation and 0 <= age <= 150_000_000
        if not ready:
          self.frame_requested.set()
          if not self.condition.wait_for(lambda: self.latest is not None and self.generation > generation, timeout):
            raise ValueError('camera_unavailable_or_stale')
      if self.latest is None or not 0 <= self.clock()-self.latest['capture_mono_ns'] <= MAX_AGE_NS:
        raise ValueError('camera_unavailable_or_stale')
      self.last_issued_generation = self.generation
      if buffered:
        self.frame_requested.set()  # Prepare at most one frame ahead.
      packet = dict(self.latest)
      packet['bridge_wait_ms'] = max(0, (self.clock()-started_ns)/1_000_000)
      packet['capture_age_ms'] = (self.clock()-packet['capture_mono_ns'])/1_000_000
      packet['stream_id'] = self.stream_id
      packet['request_id'] = secrets.token_hex(16)
      self.issued[packet['request_id']] = (packet['capture_mono_ns'], packet['frame_id'])
      while len(self.issued) > 16:
        self.issued.popitem(last=False)
      return packet

  def accept(self, data):
    with self.lock:
      issued = self.issued.pop(data.get('request_id', ''), None)
      if issued is None:
        raise ValueError('unknown_or_replayed_request')
      capture, frame_id = issued
      if not 0 <= self.clock()-capture <= MAX_AGE_NS or capture <= self.last_accepted_capture:
        raise ValueError('stale_or_out_of_order_result')
      if data.get('frame_id') != frame_id:
        raise ValueError('wrong_frame')
      lane = validate_lane(data.get("lane_cp"))
      sides = {}
      for side in ('left', 'right'):
        value = data.get(side)
        if value is not None:
          if not isinstance(value, dict):
            raise ValueError('invalid_side')
          for key in ('distance_m', 'relative_speed_mps', 'absolute_speed_mps'):
            x = value.get(key)
            if x is not None and (type(x) not in (int, float) or not math.isfinite(x)):
              raise ValueError('non_finite_metric')
          distance = value.get('distance_m')
          if distance is not None and not 2 <= distance <= 100:
            raise ValueError('distance_out_of_bounds')
          if type(value.get('hits')) is not int or not 1 <= value['hits'] <= 100000:
            raise ValueError('invalid_hits')
          sides[side] = {k: value.get(k) for k in ('track_id', 'distance_m', 'relative_speed_mps', 'absolute_speed_mps', 'hits', 'confidence')}
        else:
          sides[side] = None
      result = dict(version=1, source='tesnav-phone', valid=True,
                    updated_mono_ns=capture, received_mono_ns=self.clock(), frame_id=frame_id, stream_id=self.stream_id,
                    experimental=True, control_eligible=False, lane_cp=lane, **sides)
      self._persist(result)
      self.last_accepted_capture = capture
      self.last_result = result
      self._unavailable_reason = None
      return result

