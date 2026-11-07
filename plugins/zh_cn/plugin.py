"""Presentation-only plugin: no vehicle hooks, process, network access or Params writes."""
from openpilot.tesla.plugin import Plugin


class SimplifiedChinese(Plugin):
  @classmethod
  def ui_translation(cls, params):
    from .catalog import ChineseCatalog
    return ChineseCatalog()
