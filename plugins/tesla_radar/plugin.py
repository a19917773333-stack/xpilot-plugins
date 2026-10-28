"""Tesla radar plugin: the sunnypilot radar backends (OEM / Continental ARS408 / off) behind source:radar.

Failure cases:
- Unknown backend value: keep the port's radar (return None) instead of guessing.
- CP.radarUnavailable: the interface returns empty RadarData, same as the port.
- Plugin disabled or conflicting: the host never calls this and keeps the port's radar.
- Parser, tracker or the CAN DBC raising: the host falls back to the port's radar for the rest of the drive.
"""
from opendbc.car.interfaces import RadarInterfaceBase
from openpilot.tesla.plugin import Plugin

from .radar import ARS408RadarInterface

OEM, ARS408, OFF = 0, 1, 2
BACKEND_PARAM = "XpilotTeslaRadarBackend"


class TeslaRadar(Plugin):
  """Selects the radar source. Only ARS408 replaces the port's interface; OEM is the port itself."""

  @classmethod
  def radar_interface(cls, CP, CP_SP, params):
    try:
      backend = int(params.get(BACKEND_PARAM))
    except (TypeError, ValueError):
      return None
    if backend == ARS408:
      return ARS408RadarInterface(CP, CP_SP)
    if backend == OFF:
      return RadarInterfaceBase(CP, CP_SP)
    return None