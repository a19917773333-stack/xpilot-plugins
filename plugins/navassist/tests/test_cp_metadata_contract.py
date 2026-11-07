"""Metadata wire checks specified before encoding: native BSM, no invented rear tracks."""

from types import SimpleNamespace as N
from navassist.cpmeta import car_state_frame


def test_native_bsm_binary_layout_and_no_side_radar():
  cs = N(
    vEgo=15.0,
    aEgo=0.0,
    vEgoCluster=15.0,
    vCruiseCluster=80.0,
    steeringAngleDeg=1.0,
    brakeHoldActive=False,
    brakeLights=False,
    leftBlindspot=True,
    rightBlindspot=False,
    gearShifter="park",
    leftBlinker=False,
    rightBlinker=True,
    fuelGauge=0.5,
  )
  b = car_state_frame(cs, 7)
  assert b[:8] == b"CVS1\x01\x00\x07\x00"
  # Five floats, bool, three shorts, float, brake bool, then native BSM flags.
  assert b[40:42] == bytes([1, 0])
  assert len(b) == 73


def test_missing_line_categories_preserve_user_selected_zero():
  # Failure contract: missing fields retain compatibility zero per user request;
  # genuine native codes and invalid-value handling must remain unchanged.
  import struct
  from cp_nav.cpmeta import car_state_frame as cp_frame
  for encode in (car_state_frame, cp_frame):
    assert struct.unpack_from('<2h', encode(N(), 1), 42) == (0, 0)
    assert struct.unpack_from('<2h', encode(N(leftLaneLine=10,rightLaneLine=21),1),42) == (10,21)
    assert struct.unpack_from('<2h', encode(N(leftLaneLine=True,rightLaneLine=99),1),42) == (-1,-1)
