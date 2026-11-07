"""Before-fix contract for the real card startup crash, not a mock serializer.

Failure modes: migration to runtime rules still mutates CarParamsSP Int16; native OEM flags change;
repeated setup flips bits; or the vehicle-harness gate is bypassed. Panda reads
the signed schema field into uint16_t, so the 16 wire bits must stay identical.
"""
from types import SimpleNamespace as N
import pytest
from opendbc.car import structs
from opendbc.sunnypilot.car.tesla.values import TeslaFlagsSP
from openpilot.cereal import custom
from openpilot.selfdrive.car.helpers import convert_to_capnp
from navassist.plugin import NavAssist


@pytest.mark.parametrize('initial', [0,1,3,0x4000,0x7fff,-32768,-32765])
def test_real_capnp_int16_roundtrip_preserves_panda_uint16_bits(initial):
  cp = structs.CarParamsSP()
  cp.flags = int(TeslaFlagsSP.HAS_VEHICLE_BUS)
  cp.safetyParam = initial
  plugin = N(MANIFEST=N(safety={'param_bit':'0x8000'}))
  NavAssist.setup(plugin,cp)
  expected = initial & 0xffff
  assert -32768 <= cp.safetyParam <= 32767
  message = convert_to_capnp(cp)
  with custom.CarParamsSP.from_bytes(message.to_bytes()) as decoded:
    assert decoded.safetyParam & 0xffff == expected
  first = cp.safetyParam
  NavAssist.setup(plugin,cp)
  assert cp.safetyParam == first


def test_no_vehicle_harness_does_not_enable_navassist_panda_bit():
  cp = structs.CarParamsSP()
  cp.flags = 0
  cp.safetyParam = 3
  NavAssist.setup(N(MANIFEST=N(safety={'param_bit':'0x8000'})),cp)
  assert convert_to_capnp(cp).safetyParam == 3
