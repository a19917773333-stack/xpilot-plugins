"""The peer takes camera geometry from VisionIPC and model geometry from the adapter."""
from types import SimpleNamespace

import pytest

from ..peer import camera_frame_size, frame_geometry


def test_frame_geometry_keeps_camera_and_model_sizes_separate():
  main = SimpleNamespace(width=1928, height=1208)
  extra = SimpleNamespace(width=1928, height=1208)

  assert frame_geometry(main, extra, (1928, 1208, 512, 256)) == (1928, 1208, 512, 256)


def test_frame_geometry_rejects_disagreeing_road_streams():
  main = SimpleNamespace(width=1928, height=1208)
  extra = SimpleNamespace(width=1344, height=760)

  with pytest.raises(RuntimeError, match="road streams disagree"):
    frame_geometry(main, extra, (1928, 1208, 512, 256))

def test_warp_buffer_size_uses_the_camera_not_the_model_input():
  class Face:
    @staticmethod
    def frame_size(width, height):
      return width, height

  assert camera_frame_size(Face(), (1928, 1208, 512, 256)) == (1928, 1208)
