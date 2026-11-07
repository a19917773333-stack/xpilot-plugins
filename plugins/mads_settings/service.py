"""Mirror the plugin switches to the host MADS params, only while parked."""
import time

from openpilot.common.params import Params
from openpilot.common.swaglog import cloudlog
from openpilot.tesla.plugin_params import ParamsView

from .settings import read

PERIOD = 1.0


def apply(host, view) -> None:
  for key, value in read(view).items():
    if isinstance(value, bool):
      if host.get_bool(key) != value:
        host.put_bool(key, value, block=True)
    elif host.get(key, return_default=True) != value:
      host.put(key, value, block=True)


def main():
  host = Params()
  view = ParamsView(host)
  while True:
    try:
      if host.get_bool('IsOffroad'):
        apply(host, view)
    except Exception:
      cloudlog.exception('mads_settings.sync')
    time.sleep(PERIOD)


if __name__ == '__main__':
  main()
