"""Radar backend selection in plugin.py.

Failure cases:
- OEM must leave the port's radar alone (return None), never replace it with a second parser.
- ARS408 must return the vendor interface, not the OEM one.
- Off must return the silent base interface so radarTracks go empty instead of stale.
- Unknown or missing setting must fall back to OEM, not raise or guess a backend.
"""
import sys
import types

from opendbc.car import structs
from opendbc.car.interfaces import RadarInterfaceBase

fake = types.ModuleType("openpilot.tesla.plugin")


class Plugin:
  def __init__(self, CP, params):
    pass


fake.Plugin = Plugin
sys.modules.setdefault("openpilot.tesla", types.ModuleType("openpilot.tesla"))
sys.modules["openpilot.tesla.plugin"] = fake

from ..plugin import OEM, OFF, ARS408, TeslaRadar  # noqa: E402
from ..radar import ARS408RadarInterface  # noqa: E402


class Params:
  def __init__(self, value):
    self.value = value

  def get(self, _key):
    return self.value


def select(value):
  cp = structs.CarParams()
  cp.radarUnavailable = False
  return TeslaRadar.radar_interface(cp, structs.CarParamsSP(), Params(value))


def test_oem_keeps_port_radar():
  assert select(OEM) is None


def test_ars408_replaces_with_vendor_interface():
  radar = select(ARS408)
  assert isinstance(radar, ARS408RadarInterface)


def test_off_is_silent_base_interface():
  radar = select(OFF)
  assert isinstance(radar, RadarInterfaceBase) and not isinstance(radar, ARS408RadarInterface)


def test_unknown_or_missing_setting_falls_back_to_oem():
  assert select(9) is None
  assert select(None) is None
  assert select("ars408") is None