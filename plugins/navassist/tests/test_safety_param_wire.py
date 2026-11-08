"""Runtime rules must leave the OEM CarParamsSP safety schema untouched.

Failure modes: setup mutates native safetyParam/flags, setup is not idempotent,
    or the plugin starts depending on a retired per-feature safety bit.
"""
from types import SimpleNamespace as N
import pytest
from opendbc.car import structs
from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP
from openpilot.selfdrive.car.helpers import convert_to_capnp
from navassist.plugin import NavAssist


@pytest.mark.parametrize('initial', [0, 1, 3, 0x4000, 0x7fff])
def test_setup_preserves_native_carparams_and_safety_param(initial):
  cp = structs.CarParamsSP()
  cp.flags = int(TeslaFlagsSP.HAS_VEHICLE_BUS)
  cp.safetyParam = initial
  plugin = N(MANIFEST=N(safety={'param_bit': '0x8000'}))
  NavAssist.setup(plugin, cp)
  assert cp.flags == int(TeslaFlagsSP.HAS_VEHICLE_BUS)
  assert cp.safetyParam == initial
  decoded = convert_to_capnp(cp)
  assert decoded.safetyParam == initial
  NavAssist.setup(plugin, cp)
  assert cp.safetyParam == initial


def test_setup_does_not_add_a_legacy_bit_without_vehicle_bus():
  cp = structs.CarParamsSP()
  cp.flags = 0
  cp.safetyParam = 3
  NavAssist.setup(N(MANIFEST=N(safety={'param_bit': '0x8000'})), cp)
  assert cp.flags == 0
  assert cp.safetyParam == 3
