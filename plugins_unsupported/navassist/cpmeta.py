"""CP compact metadata: native car state only; no image or invented side radar.

Missing line categories retain compatibility zero per the user policy. Existing native
codes are forwarded; neither road geometry nor phone lane count invents paint.

CP-only fields absent in SP (softHold/carrotCruise/gearStep/line categories/urea/
TPMS) are wire padding, not capabilities. Capability metadata explicitly lists
those omissions. BSM false means not triggered, never proof of rear clearance.
"""

import struct
import threading
import time

SERVICES = [
  "carState",
  "controlsState",
  "deviceState",
  "carrotMan",
  "selfdriveState",
  "gpsLocationExternal",
  "longitudinalPlan",
  "modelV2",
  "lateralPlan",
  "radarState",
  "carControl",
  "carrotNavi",
]
GEARS = ["unknown", "park", "drive", "neutral", "reverse", "sport", "low", "brake", "eco", "manumatic"]


def car_state_frame(cs, sequence):
  def value(name, default=0):
    return getattr(cs, name, default)

  def marking(name):
    code = value(name, 0)
    return code if type(code) is int and code in (-1, 0, 1, 10, 11, 20, 21, 30, 31) else -1

  gear = str(value("gearShifter", "unknown"))
  payload = struct.pack(
    "<5f?3hf???2hB??2f4f",
    *[float(value(k)) for k in ("vEgo", "aEgo", "vEgoCluster", "vCruiseCluster", "steeringAngleDeg")],
    bool(value("brakeHoldActive")),
    0,
    0,
    0,
    0.0,
    bool(value("brakeLights")),
    bool(value("leftBlindspot")),
    bool(value("rightBlindspot")),
    marking("leftLaneLine"),
    marking("rightLaneLine"),
    GEARS.index(gear) if gear in GEARS else 0,
    bool(value("leftBlinker")),
    bool(value("rightBlinker")),
    float(value("fuelGauge")),
    0.0,
    0.0,
    0.0,
    0.0,
    0.0,
  )
  return b"CVS1" + struct.pack("<BBH", 1, 0, sequence % 65536) + payload


class Metadata:
  def __init__(self):
    self.lock = threading.Lock()
    self.packet = None
    self.stamp = 0
    self.sequence = 0

  def update(self, cs, stamp):
    with self.lock:
      if stamp <= self.stamp:
        return
      self.sequence = (self.sequence + 1) % 65536
      self.packet = car_state_frame(cs, self.sequence)
      self.stamp = stamp

  def read(self):
    with self.lock:
      if not 0 <= time.monotonic_ns() - self.stamp < 250_000_000:
        return None
      return self.stamp, self.packet
