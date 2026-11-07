"""Native calculation dependencies and internal-only result capture.
No live cereal publishers, host Params writes or operating-system commands.
"""
import math
import time
import json
import collections
import numpy as np
from openpilot.common.constants import CV
from .gps import GPSSources


class MyMovingAverage:
  def __init__(self, window_size, value=None):
    self.window_size = window_size
    self.values = collections.deque([value] * window_size if value is not None else (), maxlen=window_size)
    self.sum = value * window_size if value is not None else 0
    self.result = value if value is not None else 0

  def set(self, value):
    self.values.clear(); self.values.append(value); self.sum = self.result = value
    return value

  def set_all(self, value):
    self.values = collections.deque([value] * self.window_size, maxlen=self.window_size)
    self.sum = value * self.window_size; self.result = value
    return value

  def process(self, value, median=False):
    self.values.append(value); self.sum = sum(self.values)
    self.result = float(np.median(self.values)) if median else float(self.sum) / len(self.values)
    return self.result


class Record(dict):
  def __getattr__(self, key):
    if key not in self:self[key] = Record()
    return self[key]

  def __setattr__(self, key, value):self[key] = value

  def init(self, key, count):
    self[key] = [Record() for _ in range(count)]
    return self[key]


class _Messaging:
  @staticmethod
  def new_message(name):return Record({name: Record()})


messaging = _Messaging()


class OutputSink:
  def __init__(self):self.messages = {}
  def send(self, name, message):self.messages[name] = message[name]


class Memory:
  def __init__(self):self.values = {}
  def put_nonblocking(self, key, value):self.values[key] = value
  def put(self, key, value):self.values[key] = value
  def get(self, key, *args, **kwargs):return self.values.get(key)
  def remove(self, key):self.values.pop(key, None)
