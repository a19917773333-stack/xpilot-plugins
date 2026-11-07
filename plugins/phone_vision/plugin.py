"""Opt-in camera transport; phone inference remains on the phone."""
from openpilot.tesla.plugin import Plugin

def ready(started, params, CP):
  return True

class PhoneVision(Plugin):
  @classmethod
  def processes(cls):
    from openpilot.system.manager.process import PythonProcess
    return [PythonProcess('phone_visiond', f'{__package__}.worker', ready)]
