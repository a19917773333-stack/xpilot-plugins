"""MADS settings plugin: the switches live in plugin.json, the process mirrors them to the host MADS params."""
from openpilot.tesla.plugin import Plugin


def always(started, params, CP):
  return True


class MadsSettings(Plugin):
  @classmethod
  def processes(cls):
    from openpilot.system.manager.process import PythonProcess
    return [PythonProcess('mads_settingsd', f'{__package__}.service', always)]
