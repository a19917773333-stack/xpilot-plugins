from types import SimpleNamespace

from .. import ui as radar_ui
from .test_ui import FakeRoad, FakeSubMasterState, Harness, lead, radar_state


def test_modern_host_without_native_lead_bars_falls_back_to_road_projection():
  class EmptyModernRoad(FakeRoad):
    def lead_markers(self):
      return []

  h = Harness()
  road = EmptyModernRoad()
  h.overlay.update(FakeSubMasterState(radar_state(lead(20.0, 0.0, True))))

  h.overlay.draw_after_leads(road)

  assert road.polygon_calls == 1
  assert len(h.markers) == 1
  assert h.markers[0][1] == radar_ui.RADAR_COLOR


def test_invalid_modern_state_does_not_draw_stale_markers():
  class ModernRoad(FakeRoad):
    def lead_markers(self):
      return [SimpleNamespace(x=350.0, y=220.0, d_rel=20.0, radar=True)]

  h = Harness()
  road = ModernRoad()
  h.overlay.update(FakeSubMasterState(radar_state(lead(20.0, 0.0, True))))
  h.overlay.update(FakeSubMasterState(radar_state(lead(20.0, 0.0, True)), valid=False))

  h.overlay.draw_after_leads(road)

  assert not h.markers and road.polygon_calls == 0
