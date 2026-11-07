"""Absolute lane feedback from independent road-edge and map evidence.

No camera client. A local corridor alone is never an absolute lane number.
Only distinct fresh frames confirm it; missing evidence clears it.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path


class AbsolutePosition:
  def __init__(self):
    self.identity = None
    self.key = None
    self.samples = 0
    self.last_ns = -1
    self.last_frame = -1
    self.last = None

  def update(self, topology, nav, now_ns):
    identity = (nav.get('sessionId'), nav.get('routeRevision'))
    if identity != self.identity:
      self.__init__()
      self.identity = identity
    captured, frame = topology.get('captureMonoNs'), topology.get('frameId')
    unknown = dict(version=1, valid=False, absolute_confirmed=False, lane_index=None,
                   lane_count=None, numbering='leftToRight', source='commaCamera',
                   nav_session_id=identity[0], route_revision=identity[1], stable_samples=0,
                   capture_mono_ns=captured if type(captured) is int else now_ns)

    def reject(reason):
      self.key, self.samples, self.last = None, 0, unknown | {'reason': reason}
      return self.last

    if (not topology.get('valid') or topology.get('stale') or nav.get('stale')
        or not nav.get('valid') or not identity[0] or type(captured) is not int
        or not 0 <= now_ns-captured <= 150_000_000):
      return reject('unavailable')
    if captured == self.last_ns and frame == self.last_frame:
      return self.last or reject('duplicate')
    if captured <= self.last_ns or type(frame) is not int or frame <= self.last_frame:
      self.last_ns, self.last_frame = captured, frame
      return reject('streamChanged')
    if self.last_ns > 0 and captured-self.last_ns > 700_000_000:
      self.key, self.samples = None, 0
    self.last_ns, self.last_frame = captured, frame
    count = nav.get('laneTotalCount')
    ys, ego = topology.get('boundaryYs', []), topology.get('egoLaneIndexFromLeft', -1)
    if type(count) is not int or not 1 <= count <= 12:
      return reject('laneTotalUnavailable')
    if not topology.get('rightCarriagewayAnchored') or not 0 <= ego < len(ys)-1:
      return reject('physicalAnchorUnavailable')
    if not all(type(y) in (int, float) and math.isfinite(y) for y in ys):
      return reject('malformedGeometry')
    # Refuse spans that could hide another minimum-width lane. The map cannot
    # resolve unobserved dividers next to the ego or between visible boundaries.
    if not 0 < ys[ego+1] <= 2.2 or any(not 2.2 <= b-a < 4.4 for a, b in zip(ys, ys[1:])):
      return reject('ambiguousSpan')
    right = len(ys)-2-ego
    index = count-right
    if not 1 <= index <= count or len(ys)-1 > count:
      return reject('mapTotalInconsistent')
    key = (index, count)
    self.samples = self.samples+1 if key == self.key else 1
    self.key = key
    self.last = unknown | dict(valid=self.samples >= 3, absolute_confirmed=self.samples >= 3,
                               lane_index=index if self.samples >= 3 else None,
                               lane_count=count if self.samples >= 3 else None,
                               stable_samples=self.samples,
                               reason='confirmed' if self.samples >= 3 else 'stabilizing')
    return self.last


def publish(record, path=Path('/dev/shm/road_lane_position.json')):
  data = json.dumps(record, allow_nan=False, separators=(',', ':'))
  temp = path.with_suffix('.tmp')
  temp.write_text(data)
  os.replace(temp, path)
