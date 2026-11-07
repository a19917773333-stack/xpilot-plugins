"""CP compact metadata: native car state plus modelV2 road geometry.

CP-only fields absent in SP (softHold/carrotCruise/gearStep/line categories/urea/
TPMS) are wire padding, not capabilities. Capability metadata explicitly lists
those omissions. BSM false means not triggered, never proof of rear clearance.
modelV2 is encoded with the CVS1 service-9 schema the phone decoder expects.
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


def _ucm(v):
  return max(0, min(65535, int(round(float(v) * 100))))


def _mm(v):
  return max(-32768, min(32767, int(round(float(v) * 1000))))


def _cm(v):
  return max(-32768, min(32767, int(round(float(v) * 100))))


def _xyz(points):
  xs = [p[0] for p in points]
  ys = [p[1] for p in points]
  zs = [p[2] for p in points]
  return (struct.pack("<H2H", 2, _ucm(xs[0]), _ucm(xs[1])) +
          struct.pack("<H2h", 2, _mm(ys[0]), _mm(ys[1])) +
          struct.pack("<H2h", 2, _mm(zs[0]), _mm(zs[1])))


def _velocity(values):
  return struct.pack("<H2h", 2, _cm(values[0]), _cm(values[1]))


def _fs(values, n=4):
  vals = list(values)[:n]
  vals += [0.0] * (n - len(vals))
  return struct.pack("<H", n) + struct.pack(f"<{n}f", *[float(v) for v in vals])


def _l_xyz(points_list):
  return struct.pack("<B", len(points_list)) + b"".join(_xyz(p) for p in points_list)


def _sample(line, xm):
  xs = [float(v) for v in line.x]
  ys = [float(v) for v in line.y]
  if not xs or len(xs) != len(ys):
    return 0.0, 0.0
  if xm <= xs[0]:
    return xs[0], ys[0]
  if xm >= xs[-1]:
    return xs[-1], ys[-1]
  for i in range(1, len(xs)):
    if xs[i] >= xm:
      t = (xm - xs[i-1]) / max(1e-6, xs[i] - xs[i-1])
      return xm, ys[i-1] + t * (ys[i] - ys[i-1])
  return xs[-1], ys[-1]


def _line_points(line, xms=(0.0, 20.0)):
  out = []
  for xm in xms:
    x, y = _sample(line, xm)
    out.append((x, y, 0.0))
  return out


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


def model_frame(model, sequence):
  fid = int(getattr(model, "frameId", 0)) & 0xFFFFFFFF
  pos = list(zip(model.position.x, model.position.y, model.position.z))[:2] or [(0.0, 0.0, 0.0)]
  while len(pos) < 2:
    pos.append(pos[0])
  vel = [float(v) for v in model.velocity.x][:2] or [0.0]
  while len(vel) < 2:
    vel.append(vel[0])
  lines = [_line_points(line) for line in list(model.laneLines)[:4]]
  edges = [_line_points(e) for e in list(model.roadEdges)[:2]]
  probs = list(model.laneLineProbs)
  stds = list(getattr(model, "laneLineStds", []) or [])
  age = int(getattr(model, "frameAge", 0) or 0)
  payload = b"".join([
    struct.pack("<II", fid, 0),
    _xyz(pos), _velocity(vel),
    _l_xyz(lines), _fs(probs, 4),
    _l_xyz(edges), _fs([0.0], 4),
    struct.pack("<B", 0),            # leadsV3
    _fs(stds, 4),
    struct.pack("<i", max(-2, min(2, age))),
    struct.pack("<ff", 0.0, 0.0),    # frameDropPerc, modelExecutionTime
  ])
  return b"CVS1" + struct.pack("<BBH", 9, 0, sequence % 65536) + payload


class Metadata:
  def __init__(self):
    self.lock = threading.Lock()
    self.packet = None
    self.stamp = 0
    self.sequence = 0

  def update(self, cs, model, stamp):
    with self.lock:
      if stamp <= self.stamp:
        return
      self.sequence = (self.sequence + 1) % 65536
      frames = [car_state_frame(cs, self.sequence)]
      if model is not None:
        try:
          frames.append(model_frame(model, self.sequence))
        except Exception:
          pass
      body = b"".join(struct.pack("<I", len(f)) + f for f in frames)
      self.packet = b"CVB1" + struct.pack("<H", len(frames)) + body
      self.stamp = stamp

  def read(self):
    with self.lock:
      if not 0 <= time.monotonic_ns() - self.stamp < 250_000_000:
        return None
      return self.stamp, self.packet
