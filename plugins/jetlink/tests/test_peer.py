"""The peer takes camera geometry from VisionIPC and model geometry from the adapter."""
from types import SimpleNamespace

import pytest

from ..peer import camera_frame_size, frame_geometry, prepare_engine


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


def test_prepare_engine_accepts_a_ready_spec_without_an_onnx_path():
  """Provisioning writes the model identity; the comma-local ONNX path is optional."""

  class Client:
    calls = []

    def ensure_engine(self, *args):
      self.calls.append(args)

  class Log:
    warnings = []

    def warning(self, *args):
      self.warnings.append(args)

  client = Client()
  spec = {"sha256": "a" * 64, "nbytes": 766354845, "ready": True}

  assert prepare_engine(client, spec, Log()) is True
  assert client.calls == [("a" * 64, 766354845, None)]


def test_prepare_engine_reports_an_unusable_spec():
  class Client:
    def ensure_engine(self, *args):
      raise AssertionError("must not request an unnamed model")

  class Log:
    warnings = []

    def warning(self, *args):
      self.warnings.append(args)

  log = Log()
  assert prepare_engine(Client(), {"ready": True}, log) is False
  assert "sha256/nbytes" in str(log.warnings[0][1])
