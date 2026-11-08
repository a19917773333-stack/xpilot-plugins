"""The peer takes camera geometry from VisionIPC and model geometry from the adapter."""
from types import SimpleNamespace

import pytest

from .. import peer as peer_module
from ..peer import camera_frame_size, clear_ready, frame_geometry, introduce, prepare_engine, wait_for_mailbox
from ..peer import FRAME_TIMEOUT, WARMUP_TIMEOUT, infer_frame


def test_first_phone_frame_warms_up_then_uses_nonblocking_normal_sends():
  """The first model reply may be slow; a busy later send must not reset USB."""

  class Client:
    def __init__(self):
      self.calls = []

    def infer(self, warped, packed, frame_id, *, deadline):
      self.calls.append(("warmup", deadline))
      return [0.0]

    def drain(self):
      self.calls.append(("drain", None))
      return 0

    def infer_begin(self, warped, packed, frame_id, *, skip_if_busy=False):
      self.calls.append(("send", skip_if_busy))
      return 1

    def infer_end(self, seq, *, hold):
      self.calls.append(("hold", hold))
      return None

  client = Client()
  infer_frame(client, None, None, 1, warmed=False)
  assert infer_frame(client, None, None, 2, warmed=True) is None

  assert client.calls == [("warmup", WARMUP_TIMEOUT), ("drain", None), ("send", True),
                        ("hold", FRAME_TIMEOUT)]
  assert 3.0 < WARMUP_TIMEOUT <= 180.0
  assert FRAME_TIMEOUT < 0.1


def test_busy_phone_queue_skips_the_frame_without_touching_the_link():
  """USB backpressure drops one phone frame, never the whole transport."""

  class Client:
    def __init__(self):
      self.ended = False

    def drain(self):
      return 0

    def infer_begin(self, warped, packed, frame_id, *, skip_if_busy=False):
      assert skip_if_busy is True
      return None

    def infer_end(self, seq, *, hold):
      self.ended = True
      raise AssertionError("no reply can exist for a frame that was not sent")

  client = Client()
  assert infer_frame(client, None, None, 1, warmed=True) is None
  assert client.ended is False


def test_introduce_hands_the_phone_hello_to_the_owner(monkeypatch):
  """The hello carries the host's pick, and the answer reaches the owner unchanged."""

  asked = {"ref": "a" * 40, "sha256": "b" * 64, "nbytes": 123, "at": 1.0}
  answer = {"device": "phone", "sleep_after": 0, "engine_state": "ready", "pick": None}

  class Models:
    adopted = False

    def __init__(self, op):
      assert op == "adapter"

    @staticmethod
    def hello_pick():
      return asked

    @staticmethod
    def heard(hello, pick):
      assert hello == answer
      assert pick == asked
      return {**hello, "heard": True}

    def adopt(self):
      type(self).adopted = True

  class Client:
    @staticmethod
    def hello(timeout, pick):
      assert timeout > 0
      assert pick == asked
      return answer

  class Link:
    def __init__(self):
      self.hello = None

    def note_server(self, hello):
      self.hello = hello

  class Log:
    @staticmethod
    def warning(*args):
      pass

  monkeypatch.setattr(peer_module, "models_for", lambda op: Models(op))
  link = Link()
  hello = introduce(link, Client(), Log(), "adapter")
  assert link.hello == hello == {**answer, "heard": True}
  assert Models.adopted


def test_wait_for_mailbox_holds_the_idle_lease_until_modeld_starts(tmp_path):
  """The phone does not answer parked pings; the open USB lease is the keepalive."""
  from ..mailbox import SIZE

  class Params:
    reads = 0

    def get(self, key):
      self.reads += 1
      if self.reads == 3:
        (tmp_path / "mailbox").write_bytes(bytes(SIZE))
      return str(tmp_path / "mailbox")

  params = Params()
  box = wait_for_mailbox(params, poll_interval=0.001)
  assert box is not None
  box.close()
  assert params.reads == 3


def test_wait_for_mailbox_stops_when_the_phone_disconnects():
  """A dead client must not leave a parked peer holding a stale USB lease forever."""
  class Params:
    @staticmethod
    def get(key):
      return None

  client = SimpleNamespace(dead=True)
  with pytest.raises(ConnectionError, match="phone disconnected"):
    wait_for_mailbox(Params(), poll_interval=0.001, client=client)


def test_missing_phone_engine_invalidates_a_stale_ready_spec():
  """A wiped phone must release the loan so provisioning can run again."""
  class EngineMissing(Exception):
    pass

  class Client:
    @staticmethod
    def ensure_engine(*args):
      raise EngineMissing("not on the phone")

  class Log:
    @staticmethod
    def warning(*args):
      pass

  class Params:
    def __init__(self):
      self.value = {"ready": True, "sha256": "a" * 64, "nbytes": 123}

    def get(self, key):
      return self.value

    def put(self, key, value, block=False):
      assert block is False
      self.value = value

  params = Params()
  assert prepare_engine(Client(), params.value, Log()) is None
  clear_ready(params)
  assert params.value["ready"] is False


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
