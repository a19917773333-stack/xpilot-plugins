"""Radar backend selection in plugin.py.

Failure cases:
- OEM must defer to the port's radar, never replace it with a second parser or suppress its output.
- ARS408 must return the vendor interface, not the OEM one.
- Off must return the silent base interface so radarTracks go empty instead of stale.
- Unknown or missing setting must fall back to OEM, not raise or guess a backend.
"""
import pytest

from opendbc.car import structs
from opendbc.car.interfaces import RadarInterfaceBase

# Needs the host's Plugin base; a checkout without xpilot on PYTHONPATH skips instead of stubbing it into
# sys.modules, which would hand every later plugin in the same session a fake base.
pytest.importorskip("openpilot.tesla.plugin")

from ..plugin import OEM, OFF, ARS408, OEMRadarInterface, TeslaRadar
from ..radar import ARS408RadarInterface


class Params:
  def __init__(self, value):
    self.value = value

  def get(self, _key):
    return self.value


def select(value):
  cp = structs.CarParams()
  cp.radarUnavailable = False
  return TeslaRadar.radar_interface(cp, structs.CarParamsSP(), Params(value))


def test_oem_defers_to_port_radar():
  radar = select(OEM)
  assert isinstance(radar, OEMRadarInterface)
  assert radar.uses_port_radar
  assert radar.update([]) is None


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
