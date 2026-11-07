"""Source-colored lead triangles.

Failure cases:
- The display switch leaves stale triangles after being turned off.
- Missing, invalid, stale, or previous-trip radarState draws triangles.
- Radar and vision leads do not use the old gold and white colors.
- Out-of-range or non-finite leads produce markers.
"""
from types import SimpleNamespace

import numpy as np
import pytest

pytest.importorskip("pyray")
pytest.importorskip("openpilot.selfdrive.ui.ui_state")

from .. import ui as radar_ui


class FakeParams:
  def __init__(self, show=True):
    self.show = show

  def get(self, key, return_default=False):
    assert key == "CameraOffset" and return_default
    return 0.35

  def get_bool(self, key, block=False):
    assert key == radar_ui.TRIANGLE_PARAM
    return self.show


class FakeSubMasterState(dict):
  def __init__(self, radar_state, valid=True, frame=10):
    super().__init__({"radarState": radar_state})
    self.valid = {"radarState": valid}
    self.recv_frame = {"radarState": frame}


class FakeRoad:
  def __init__(self):
    import pyray as rl
    self.rect = rl.Rectangle(100, 100, 600, 360)
    self.polygon_calls = 0
    self.points = []

  def lane_points(self):
    return [np.array([[0.0, 0.0, -1.0], [100.0, 0.0, -1.0]], dtype=np.float32)]

  def polygon(self, points, half_width):
    self.polygon_calls += 1
    self.points.append(points.copy())
    assert half_width > 0
    x = float(points[0, 1]) * 10.0 + 350.0
    return np.array([[x - 5.0, 220.0], [x + 5.0, 220.0]], dtype=np.float32)


def lead(d_rel, y_rel, radar):
  return SimpleNamespace(present=True, dRel=d_rel, yRel=y_rel, radar=radar)


def radar_state(lead_one=None, lead_two=None):
  return SimpleNamespace(
    leadOne=lead_one or SimpleNamespace(present=False),
    leadTwo=lead_two or SimpleNamespace(present=False),
  )


class Harness:
  def __init__(self, show=True):
    self.now = 10.0
    self.params = FakeParams(show)
    self.view = SimpleNamespace(started_frame=5, active_bundle=True)
    self.overlay = radar_ui.RadarTriangles(self.params, self.view, clock=lambda: self.now)
    self.markers = []
    self.overlay._draw_marker = lambda pos, color, d_rel: self.markers.append((pos, color, d_rel))

  def render(self, state, road=None):
    road = road or FakeRoad()
    self.overlay.update(state)
    self.overlay.draw(road)
    return road


def test_switch_off_draws_nothing():
  h = Harness(show=False)
  road = h.render(FakeSubMasterState(radar_state(lead(20.0, 0.0, True))))
  assert not h.markers and road.polygon_calls == 0


@pytest.mark.parametrize("state", [
  FakeSubMasterState(radar_state(lead(20.0, 0.0, True)), valid=False),
  FakeSubMasterState(radar_state(lead(20.0, 0.0, True)), frame=4),
])
def test_invalid_or_previous_trip_state_draws_nothing(state):
  h = Harness()
  road = h.render(state)
  assert not h.markers and road.polygon_calls == 0


def test_radar_lead_is_gold_and_vision_lead_is_white():
  h = Harness()
  road = h.render(FakeSubMasterState(radar_state(lead(20.0, 0.0, True), lead(40.0, 1.0, False))))
  assert road.polygon_calls == 2
  assert len(h.markers) == 2
  colors = [color for _, color, _ in h.markers]
  assert radar_ui.RADAR_COLOR in colors
  assert radar_ui.VISION_COLOR in colors


def test_projection_uses_camera_offset_and_calibrated_path_height():
  h = Harness()
  state = FakeSubMasterState(radar_state(lead(20.0, 1.2, True)))
  state["extrinsicsCalibration"] = SimpleNamespace(height=[1.6])
  road = h.render(state)
  assert road.polygon_calls == 1
  assert np.allclose(road.points[0][0], [20.0, -0.85, 0.6])


def test_out_of_range_nonfinite_and_duplicate_leads_are_skipped():
  h = Harness()
  state = FakeSubMasterState(radar_state(
    lead(0.2, 0.0, True),
    lead(float("nan"), 0.0, False),
  ))
  road = h.render(state)
  assert not h.markers and road.polygon_calls == 0

  h = Harness()
  state = FakeSubMasterState(radar_state(lead(20.0, 0.0, True), lead(20.5, 0.1, True)))
  road = h.render(state)
  assert len(h.markers) == 1 and road.polygon_calls == 1


def test_cached_switch_change_hides_triangles_without_restart():
  h = Harness()
  state = FakeSubMasterState(radar_state(lead(20.0, 0.0, True)))
  h.render(state)
  assert len(h.markers) == 1

  h.params.show = False
  h.now += radar_ui.SETTINGS_REFRESH_S + 0.01
  h.markers.clear()
  h.render(state)
  assert not h.markers


def test_projection_failure_does_not_draw():
  class NoProjection(FakeRoad):
    def polygon(self, points, half_width):
      self.polygon_calls += 1
      return np.empty((0, 2), dtype=np.float32)

  h = Harness()
  road = h.render(FakeSubMasterState(radar_state(lead(20.0, 0.0, True))), NoProjection())
  assert road.polygon_calls == 1
  assert not h.markers
