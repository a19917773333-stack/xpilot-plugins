from plugins.cruise_settings.settings import read


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
  assert out["IntelligentCruiseButtonManagement"] is False
  assert out["SmartCruiseControlVision"] is False
  assert out["InitialCruiseSpeedKph"] == 40


def test_values_and_clamp():
  view = View({"ExtCruiseIcbm": "0", "ExtCruiseSccVision": "1", "ExtCruiseInitialSpeed": "999"})
  out = read(view)
  assert out["IntelligentCruiseButtonManagement"] is False
  assert out["SmartCruiseControlVision"] is True
  assert out["InitialCruiseSpeedKph"] == 160


def test_bad_speed_falls_back():
  out = read(View({"ExtCruiseInitialSpeed": "fast"}))
  assert out["InitialCruiseSpeedKph"] == 40


def test_tesla_main_cruise_absent():
  out = read(View({}), host_has_main_cruise=False)
  assert "MadsMainCruiseAllowed" not in out
