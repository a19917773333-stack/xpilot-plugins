"""Parked configuration of existing SP controls; no vehicle control hooks."""
from openpilot.tesla.plugin import Plugin


class TurnLaneSettings(Plugin):
  """The master switch shows the optional parked summary tile only."""
