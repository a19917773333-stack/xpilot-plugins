"""Source-colored lead triangles on the mici road view.

Ported from a19917773333-stack/slgame@6b5dc07f892d24111dbcd67bbf7a890183ba02b7:
- ModelRenderer._draw_lead_source_arrow: gold triangle for a radar lead.
- White lead indicator for a vision lead.

Adapted to xpilot's public RoadOverlay API instead of the old renderer's
private camera transform.

Failure cases:
- The display switch must hide both colors immediately.
- Missing, invalid, stale, previous-trip, out-of-range, or non-finite leads
  must not draw stale triangles.
- A projection failure must skip that lead without affecting the other lead.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
import time

import numpy as np
import pyray as rl

from openpilot.common.params import Params
from openpilot.selfdrive.ui.ui_state import ui_state
from openpilot.tesla.plugin_params import ParamsView
from openpilot.tesla.ui.plugin_ui import RoadOverlay

TRIANGLE_PARAM = "ExtTeslaRadarTriangle"
SETTINGS_REFRESH_S = 0.5
MIN_DREL = 0.8
MAX_DREL = 110.0
MAX_LATERAL = 14.0
PROJECTION_HALF_WIDTH_M = 0.2
DEFAULT_ROAD_HEIGHT_M = 1.22

RADAR_COLOR = rl.Color(255, 215, 0, 255)
VISION_COLOR = rl.Color(255, 255, 255, 255)


@dataclass(frozen=True)
class LeadTriangle:
  d_rel: float
  y_rel: float
  radar: bool


class RadarTriangles(RoadOverlay):
  """Draw gold triangles for radar leads and white triangles for vision leads."""

  def __init__(self, params=None, view_state=None, clock=None):
    self._params = params or ParamsView(Params())
    self._view = view_state or ui_state
    self._clock = clock or time.monotonic
    self._settings_at = -math.inf
    self._show = False
    self._camera_offset = 0.0
    self._road_height_offset = DEFAULT_ROAD_HEIGHT_M
    self._leads: list[LeadTriangle] = []

  def update(self, sm) -> None:
    self._refresh_settings()
    self._leads = []
    if not self._show:
      return
    if not sm.valid.get("radarState", False):
      return
    if sm.recv_frame.get("radarState", -1) < self._view.started_frame:
      return

    self._road_height_offset = self._calibration_height(sm)
    radar_state = sm["radarState"]
    leads = []
    for lead in (radar_state.leadOne, radar_state.leadTwo):
      if lead is None or not lead.present:
        continue
      try:
        d_rel, y_rel = float(lead.dRel), float(lead.yRel)
      except (AttributeError, TypeError, ValueError):
        continue
      if not all(map(math.isfinite, (d_rel, y_rel))):
        continue
      if not (MIN_DREL <= d_rel <= MAX_DREL) or abs(y_rel) > MAX_LATERAL:
        continue
      radar = bool(getattr(lead, "radar", False))
      if any(abs(d_rel - other.d_rel) < 3.0 and abs(y_rel - other.y_rel) < 0.5 for other in leads):
        continue
      leads.append(LeadTriangle(d_rel, y_rel, radar))
    self._leads = leads

  def draw(self, road) -> None:
    if not self._show or not self._leads:
      return
    if hasattr(road, "lead_markers"):
      return
    self._draw_projections(road)

  def draw_after_leads(self, road) -> None:
    """Draw after the host lead bars so the source triangle cannot be covered."""
    if not self._show or not self._leads or not hasattr(road, "lead_markers"):
      return

    markers = road.lead_markers()
    if not markers:
      self._draw_projections(road)  # stock longitudinal control has no native lead bars
      return

    for marker in reversed(markers):
      width, height = self._marker_size(marker.d_rel)
      rect = road.rect
      if marker.y + 5.0 + height > rect.y + rect.height - 4.0:
        continue
      x = float(np.clip(marker.x, rect.x + width / 2.0, rect.x + rect.width - width / 2.0))
      self._draw_marker(rl.Vector2(x, float(marker.y)), RADAR_COLOR if marker.radar else VISION_COLOR, float(marker.d_rel))

  def _draw_projections(self, road) -> None:
    for lead in reversed(self._leads):
      marker = self._project_marker(lead, road)
      if marker is None:
        continue
      self._draw_marker(marker, RADAR_COLOR if lead.radar else VISION_COLOR, lead.d_rel)

  def _refresh_settings(self, force: bool = False) -> None:
    now = self._clock()
    if not force and now - self._settings_at < SETTINGS_REFRESH_S:
      return
    self._settings_at = now
    try:
      self._show = bool(self._params.get_bool(TRIANGLE_PARAM))
    except (AttributeError, TypeError, ValueError):
      self._show = False
    try:
      active_bundle = bool(getattr(self._view, "active_bundle", False))
      camera_offset = self._params.get("CameraOffset", return_default=True) if active_bundle else 0.0
      camera_offset = float(camera_offset or 0.0)
      self._camera_offset = camera_offset if math.isfinite(camera_offset) else 0.0
    except (AttributeError, TypeError, ValueError):
      self._camera_offset = 0.0

  def _project_marker(self, lead: LeadTriangle, road) -> rl.Vector2 | None:
    z = self._road_height(road, lead.d_rel)
    point = np.array([[
      lead.d_rel,
      -lead.y_rel + self._camera_offset,
      z + self._road_height_offset,
    ]], dtype=np.float32)
    polygon = road.polygon(point, PROJECTION_HALF_WIDTH_M)
    if polygon.size < 2:
      return None

    x, y = polygon.mean(axis=0)
    rect = road.rect
    if not (rect.x <= x <= rect.x + rect.width and rect.y <= y <= rect.y + rect.height):
      return None
    return rl.Vector2(float(x), float(y))

  @staticmethod
  def _road_height(road, distance: float) -> float:
    fallback = 0.0
    for points in road.lane_points():
      line = np.asarray(points, dtype=np.float32)
      if line.shape[0] < 2:
        continue
      order = np.argsort(line[:, 0])
      x = line[order, 0]
      fallback = float(np.interp(distance, x, line[order, 2]))
      if x[0] <= distance <= x[-1]:
        return float(np.interp(distance, x, line[order, 2]))
    return fallback

  @staticmethod
  def _calibration_height(sm) -> float:
    try:
      height = float(sm["extrinsicsCalibration"].height[0])
      return height if math.isfinite(height) else DEFAULT_ROAD_HEIGHT_M
    except (AttributeError, IndexError, KeyError, TypeError, ValueError):
      return DEFAULT_ROAD_HEIGHT_M

  @staticmethod
  def _marker_size(d_rel: float) -> tuple[float, float]:
    size = float(np.clip((25.0 * 30.0) / (max(d_rel, 0.0) / 3.0 + 30.0), 15.0, 30.0) * 2.35)
    width = float(np.clip(size * 0.62, 20.0, 44.0))
    height = float(np.clip(size * 0.34, 10.0, 22.0))
    return width, height

  @staticmethod
  def _draw_marker(pos: rl.Vector2, color: rl.Color, d_rel: float) -> None:
    width, height = RadarTriangles._marker_size(d_rel)
    tip_y = pos.y + 5.0
    base_y = tip_y + height
    marker = [(pos.x, tip_y), (pos.x + width / 2.0, base_y), (pos.x - width / 2.0, base_y)]
    shadow = [(pos.x, tip_y - 2.0), (pos.x + width / 2.0 + 2.0, base_y + 2.0),
              (pos.x - width / 2.0 - 2.0, base_y + 2.0)]
    # Triangle primitives did not produce pixels in the target pyray build; scanline rectangles do.
    RadarTriangles._fill_triangle(shadow, rl.Color(0, 0, 0, 170))
    RadarTriangles._fill_triangle(marker, color)

  @staticmethod
  def _fill_triangle(points, color: rl.Color) -> None:
    tip_x, tip_y = points[0]
    base_y = points[1][1]
    if base_y <= tip_y:
      return
    for y in range(math.ceil(tip_y), math.floor(base_y) + 1):
      progress = (y - tip_y) / (base_y - tip_y)
      left_x = tip_x + (points[2][0] - tip_x) * progress
      right_x = tip_x + (points[1][0] - tip_x) * progress
      x0, x1 = math.floor(left_x), math.ceil(right_x)
      if x1 <= x0:
        x0, x1 = math.floor(tip_x), math.floor(tip_x) + 1
      rl.draw_rectangle(x0, y, x1 - x0, 1, color)
