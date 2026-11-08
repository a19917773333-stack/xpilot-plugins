"""Model-only ego lane geometry, shared with the CP app's LaneGeometry contract.

Reads 7000 modelV2 (lane lines, probabilities/stds, road edges) plus the lateral lane-change state.
No camera or VisionIPC client. The result is an estimate for display/consistency checks: it does not
grant permission to cross a boundary, and control still requires a matched navigation state.
"""
from __future__ import annotations

MIN_OUTER_LANE_M = 2.0
MAX_OUTER_LANE_M = 5.0
MIN_EGO_LANE_M = 2.5
MAX_EGO_LANE_M = 4.5
LANE_CHANGE_STATES = frozenset({'preLaneChange', 'laneChangeStarting', 'laneChangeFinishing'})


def _floats(values):
  try:
    return [float(v) for v in values]
  except (TypeError, ValueError):
    return None


def _at(curve, x_m):
  xs, ys = _floats(getattr(curve, 'x', [])), _floats(getattr(curve, 'y', []))
  if xs is None or ys is None or len(xs) < 2 or len(xs) != len(ys):
    return None
  if any(b <= a for a, b in zip(xs, xs[1:])) or x_m < xs[0] or x_m > xs[-1]:
    return None
  i = next((k for k, x in enumerate(xs) if x >= x_m), 0)
  if i == 0:
    return ys[0]
  return ys[i-1] + (ys[i]-ys[i-1]) * (x_m-xs[i-1]) / (xs[i]-xs[i-1])


def measure(model, lateral_state=None):
  """Return lane width and a provisional 1-based left index; never raises on bad model data."""
  out = dict(status='Missing', widthM=None, leftSpaceM=None, rightSpaceM=None,
             leftWidthBands=None, rightWidthBands=None, provisionalIndex=None,
             laneCount=None)
  if model is None:
    return out
  probs = _floats(getattr(model, 'laneLineProbs', []))
  stds = _floats(getattr(model, 'laneLineStds', []))
  age = getattr(model, 'frameAge', 0)
  if age is None or not 0 <= age <= 2:
    return dict(out, status='Invalid')
  if (probs is None or stds is None or len(probs) != 4 or len(stds) != 4
      or probs[1] < 0.7 or probs[2] < 0.7
      or not 0 <= stds[1] <= 0.3 or not 0 <= stds[2] <= 0.3):
    return dict(out, status='Invalid')
  if lateral_state in LANE_CHANGE_STATES:
    return dict(out, status='Maneuvering')
  lines = list(getattr(model, 'laneLines', []))
  if len(lines) != 4:
    return dict(out, status='Invalid')
  edges = list(getattr(model, 'roadEdges', []))
  edge_stds = _floats(getattr(model, 'roadEdgeStds', []))
  if len(edges) != 2:
    edges = None

  def ego_width_at(x):
    left, right = _at(lines[1], x), _at(lines[2], x)
    if left is None or right is None or not (left < 0 < right):
      return None
    width = right - left
    return (left, right) if MIN_EGO_LANE_M <= width <= MAX_EGO_LANE_M else None

  left_ok = probs[0] >= 0.7 and 0 <= stds[0] <= 0.3
  right_ok = probs[3] >= 0.7 and 0 <= stds[3] <= 0.3

  def neighbor(inner, index, ok):
    if not ok:
      return None
    outer = _at(lines[index], 5.0)
    if outer is None:
      return None
    gap = abs(outer - inner)
    return gap if MIN_OUTER_LANE_M <= gap <= MAX_OUTER_LANE_M else None

  near = ego_width_at(5.0)
  far = ego_width_at(15.0)
  pair = near or far
  if pair is None:
    return out
  width = pair[1] - pair[0]
  out.update(status='WidthOnly', widthM=width,
             leftSpaceM=neighbor(pair[0], 0, left_ok) if near else None,
             rightSpaceM=neighbor(pair[1], 3, right_ok) if near else None)
  if lateral_state not in ('off', None) or edges is None:
    return out

  def full_section(x):
    near_pair = ego_width_at(x)
    if near_pair is None:
      return None
    section = near_pair[1] - near_pair[0]

    def space(index):
      if edge_stds is None or len(edge_stds) <= index or not 0 <= edge_stds[index] <= 0.3:
        return None
      edge = _at(edges[index], x)
      if edge is None:
        return None
      distance = near_pair[0] - edge if index == 0 else edge - near_pair[1]
      return distance if distance >= 0 else None

    def bands(distance):
      if distance is None:
        return None
      ratio = distance / section
      rounded = int(round(ratio))
      return rounded if 0 <= rounded <= 5 and abs(ratio - rounded) <= 0.2 else None

    def outer_valid(index, boundary):
      if probs[index] < 0.7 or not 0 <= stds[index] <= 0.3:
        return False
      curve = _at(lines[index], x)
      if curve is None:
        return False
      gap = boundary - curve if index == 0 else curve - boundary
      return abs(gap - section) <= section * 0.2

    left_bands = bands(space(0))
    right_bands = bands(space(1))
    left = left_bands if left_bands == 0 or (left_bands is not None and outer_valid(0, near_pair[0])) else None
    right = right_bands if right_bands == 0 or (right_bands is not None and outer_valid(3, near_pair[1])) else None
    return dict(section=section, left=left, right=right,
                index=(left + 1) if left is not None and right is not None else None)

  near_section, far_section = full_section(5.0), full_section(15.0)
  chosen = near_section or far_section
  if chosen is None:
    return out
  if near_section is not None and far_section is not None:
    agrees = abs(near_section['section'] - far_section['section']) <= 0.4
    left = near_section['left'] if agrees and near_section['left'] == far_section['left'] else None
    right = near_section['right'] if agrees and near_section['right'] == far_section['right'] else None
    count = left + right + 1 if left is not None and right is not None else None
    return dict(out, status='Stabilizing', widthM=near_section['section'],
                leftWidthBands=left, rightWidthBands=right,
                provisionalIndex=(left + 1) if left is not None and right is not None else None,
                laneCount=count)
  return dict(out, status='Stabilizing', widthM=chosen['section'],
              leftWidthBands=None, rightWidthBands=None, provisionalIndex=None, laneCount=None)
