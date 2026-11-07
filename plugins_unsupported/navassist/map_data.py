"""Read-only VEH 0x238. Vendored identically in consumers for independent installation.

Bit layout: paired tesla_modely_hw4_perception.dbc; upper-bound code table:
legacy tesla_can_visualization.py. DBC agreement is not vehicle validation.
"""
import math

STALE_NS = 1_000_000_000
SPEED_LIMITS = {1: 5, 2: 7, **{i: (i-1)*5 for i in range(3, 26)}, 26: 130, 27: 140, 28: 150, 29: 160}
FIELDS = {
  'dependency': (0, 3), 'roadClass': (3, 3), 'supercharger': (6, 1), 'units': (7, 1),
  'limitCode': (8, 5), 'limitType': (13, 3), 'countryCode': (16, 10), 'streetCount': (26, 2),
  'gpsRoadMatch': (28, 1), 'navRouteActive': (29, 1), 'parallelAutopark': (30, 1),
  'perpendicularAutopark': (31, 1), 'branchCode': (32, 5), 'controlledAccess': (37, 1),
  'exitLeft': (38, 1), 'exitRight': (39, 1), 'rejectLeftLane': (40, 1), 'rejectRightLane': (41, 1),
  'rejectHPP': (42, 1), 'rejectNav': (43, 1), 'rejectLeftFreeSpace': (44, 1),
  'rejectRightFreeSpace': (45, 1), 'rejectAutosteer': (46, 1), 'rejectHandsOn': (47, 1),
  'acceptBottsDots': (48, 1), 'autosteerRestricted': (49, 1), 'pmmEnabled': (50, 1), 'scaEnabled': (51, 1),
}


class MapData:
  def __init__(self):
    self.stamp = 0
    self.raw = {}

  def update(self, batches, now_ns):
    for stamp, frames in batches:
      if type(stamp) is not int or not 0 < stamp <= now_ns or stamp <= self.stamp:
        continue
      for address, data, bus in frames:
        if address != 0x238 or bus != 1 or len(data) != 8:
          continue
        value = int.from_bytes(data, 'little')
        self.raw = {key: (value >> start) & ((1 << width)-1) for key, (start, width) in FIELDS.items()}
        self.stamp = stamp

  def snapshot(self, now_ns):
    r = self.raw
    fresh = bool(self.stamp and 0 <= now_ns-self.stamp <= STALE_NS)
    code = r.get('limitCode', 0)
    value = SPEED_LIMITS.get(code) if fresh else None
    unit = 'KPH' if r.get('units') else 'MPH'
    qualified = bool(fresh and r.get('gpsRoadMatch'))
    return dict(fresh=fresh, stampNs=self.stamp, ageMs=(now_ns-self.stamp)/1e6 if self.stamp else None,
      raw=dict(r), qualified=qualified,
      limit=dict(code=code, value=value, unit=unit, unlimited=bool(fresh and code == 30),
                 type=r.get('limitType'), dependency=r.get('dependency'),
                 comparable=bool(qualified and value is not None and r.get('limitType') == 1
                                 and r.get('dependency') == 0)),
      branch=dict(distanceM=r['branchCode']*10 if fresh and r.get('branchCode', 31) != 31 else None,
                  side='both' if r.get('exitLeft') and r.get('exitRight') else
                  'left' if r.get('exitLeft') else 'right' if r.get('exitRight') else 'none'))


class LimitComparison:
  def __init__(self):
    self.key = None
    self.since = self.last = 0

  def update(self, snapshot, fused_mps, now_ns):
    limit = snapshot['limit']
    sp = type(fused_mps) in (int, float) and math.isfinite(fused_mps) and fused_mps > 0
    map_ok = limit['comparable']
    unit = 1/3.6 if limit['unit'] == 'KPH' else .44704
    delta = fused_mps/unit-limit['value'] if sp and map_ok else None
    key = (limit['code'], limit['unit'], round(fused_mps/unit)) if delta is not None and abs(delta) >= 10 else None
    if key is None or key != self.key or not 0 <= now_ns-self.last <= STALE_NS:
      self.since = now_ns
    self.key, self.last = key, now_ns
    conflict = key is not None and now_ns-self.since >= 3_000_000_000
    state = ('CONFLICT' if conflict else 'CHECKING' if key is not None else 'AGREE') if sp and map_ok else (
      'SP_ONLY' if sp else 'MAP_ONLY' if map_ok else 'NONE')
    return dict(state=state, delta=delta, unit=limit['unit'], fusedMps=fused_mps if sp else None,
                blockIncrease=conflict, tolerance=5)
