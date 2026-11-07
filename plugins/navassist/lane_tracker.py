"""Temporal ego-lane tracker over the model-only lane geometry.

A single frame can flip the provisional index at dashes and merges. This tracker confirms an index over
several consecutive frames, holds the confirmed value through short model gaps, and clears it when the
geometry is gone or ambiguous. It never guesses a lane and never authorizes a lane change.
"""
from __future__ import annotations

CONFIRM_FRAMES = 3
HOLD_NS = 1_500_000_000
MAX_FRAME_GAP = 40  # 2 s at the 20 Hz model rate


class LaneIndexTracker:
  def __init__(self):
    self.index = None
    self.count = None
    self.changing = False
    self._candidate = None
    self._confirmations = 0
    self._last_frame = None
    self._last_seen_ns = 0

  def reset(self):
    self.index = None
    self.count = None
    self.changing = False
    self._candidate = None
    self._confirmations = 0
    self._last_frame = None
    self._last_seen_ns = 0

  def update(self, frame_id, index, count, status, now_ns):
    if status == 'Maneuvering':
      self.changing = True
      self._candidate = None
      self._confirmations = 0
      return self._output(now_ns)

    if frame_id is None or type(frame_id) is not int or frame_id < 0:
      self._candidate = None
      self._confirmations = 0
      self._last_frame = None
      return self._output(now_ns)

    if self._last_frame is not None:
      delta = frame_id - self._last_frame
      if delta <= 0 or delta > MAX_FRAME_GAP:
        self._candidate = None
        self._confirmations = 0
    self._last_frame = frame_id

    if (type(index) is not int or type(count) is not int or not 1 <= count <= 16
        or not 1 <= index <= count):
      self._candidate = None
      self._confirmations = 0
      return self._output(now_ns)

    candidate = (index, count)
    if candidate == self._candidate:
      self._confirmations = min(CONFIRM_FRAMES, self._confirmations + 1)
    else:
      self._candidate = candidate
      self._confirmations = 1
    if self._confirmations >= CONFIRM_FRAMES:
      self.index, self.count = candidate
      self._last_seen_ns = int(now_ns)
      self.changing = False
    return self._output(now_ns)

  def _output(self, now_ns):
    valid = self.index is not None and self.count is not None and 0 <= now_ns-self._last_seen_ns <= HOLD_NS
    if not valid:
      self.index = None
      self.count = None
    age_ms = max(0, now_ns-self._last_seen_ns)/1e6 if self.index is not None else 0.0
    return dict(index=self.index, count=self.count, valid=valid, changing=self.changing, ageMs=age_ms)
