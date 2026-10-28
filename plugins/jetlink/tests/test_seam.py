"""The adapter against jetlink's own conformance check, so a member that drifts fails here and not on the road."""
import sys
from pathlib import Path

import pytest

from .. import seam

HERE = Path(__file__).resolve().parents[2]  # the plugins directory pytest put on sys.path, which holds this package


def real_jetlink_adapter():
  """jetlink's package and an Adapter built from it, or None.

  From plugins/ this package is imported as `jetlink`, so jetlink's own package only resolves once this one is off
  sys.path and out of sys.modules; the Adapter is built inside that window, because it imports jetlink when it is
  made. Everything is put back afterwards, so later tests still see this plugin.
  """
  saved_path = list(sys.path)
  saved_modules = {name: module for name, module in sys.modules.items() if name == "jetlink" or name.startswith("jetlink.")}
  sys.path[:] = [path for path in saved_path if Path(path or ".").resolve() != HERE]
  for name in saved_modules:
    sys.modules.pop(name)
  try:
    import jetlink.openpilot
    return sys.modules["jetlink.openpilot"], seam.Adapter()
  except ImportError:
    return None
  finally:
    sys.path[:] = saved_path
    for name in [name for name in sys.modules if name == "jetlink" or name.startswith("jetlink.")]:
      sys.modules.pop(name)
    sys.modules.update(saved_modules)


def test_adapter_conforms_to_jetlink_api():
  found = real_jetlink_adapter()
  if found is None:
    pytest.skip("jetlink (the phone package) is not installed here")
  interface, adapter = found
  assert interface.API == seam.API, "the adapter is written to another jetlink API"
  problems = interface.conformance(adapter, interface.Openpilot)
  assert problems == [], problems