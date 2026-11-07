"""Cruise settings plugin: switches live in plugin.json, the process mirrors them to the host params."""
from openpilot.tesla.plugin import Plugin


def always(started, params, CP):
  return True


class CruiseSettings(Plugin):
  @classmethod
  def processes(cls):
    from openpilot.system.manager.process import PythonProcess
    return [PythonProcess('cruise_settingsd', f'{__package__}.service', always)]
