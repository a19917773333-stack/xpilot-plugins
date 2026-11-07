import pytest

from plugins.mads_settings.settings import read


class View:
  def __init__(self, values):
    self.values = values
  def get(self, key, return_default=False):
    return self.values.get(key)
  def get_bool(self, key):
    if key not in self.values:
      raise KeyError(key)
    return self.values[key]


def test_defaults():
  out = read(View({}))
  assert out["Mads"] is True
  assert out["MadsSteeringMode"] == 2
  assert out["TeslaMadsScreenButton"] == 0
  assert out["MadsUnifiedEngagementMode"] is True


def test_choices_and_bools():
  view = View({"ExtMadsEnabled": "0", "ExtMadsSteeringMode": "1", "ExtMadsScreenButton": "2", "ExtMadsUnified": "0"})
  out = read(view)
  assert out["Mads"] is False
  assert out["MadsSteeringMode"] == 1
  assert out["TeslaMadsScreenButton"] == 2
  assert out["MadsUnifiedEngagementMode"] is False


def test_bad_values_fall_back():
  view = View({"ExtMadsSteeringMode": "9", "ExtMadsScreenButton": "x"})
  out = read(view)
  assert out["MadsSteeringMode"] == 2
  assert out["TeslaMadsScreenButton"] == 0


def test_main_cruise_moved_out():
  out = read(View({}))
  assert "MadsMainCruiseAllowed" not in out
