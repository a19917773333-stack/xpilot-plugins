"""The peer against modeld's own mailbox, in one process: a frame modeld publishes is the frame the peer reads,
and a reply the peer writes is the answer modeld adopts.

Failure cases:
- a reply that is not exactly the wire modeld validates (lengths, magic, paired flags, session) is rejected by
  modeld, so the drive stays local;
- a reply that arrives after the deadline, or for a frame modeld has left behind, is never adopted;
- the peer must not answer a slot it could not lock.
"""
import numpy as np
import pytest

from openpilot.tesla.model_source import DEADLINE_NS, HEAD_SHAPES, ModelSource, nanos_since_boot

from ..decode import HEAD_OFFSETS, HEAD_PADDING, decoder
from ..mailbox import HEAD_COUNT, Mailbox

ADMIT = lambda local, remote: True  # noqa: E731


class Meta:
  def __init__(self, frame_id: int, eof: int) -> None:
    self.frame_id, self.timestamp_eof = frame_id, eof


def inputs():
  return {"desire_pulse": np.zeros(8, dtype=np.float32), "traffic_convention": np.zeros(2, dtype=np.float32),
          "action_t": np.array([0.05, 0.06], dtype=np.float32)}


def transforms():
  return {"img": np.eye(3, dtype=np.float32), "big_img": np.eye(3, dtype=np.float32) * 2}


def local_heads():
  return decoder({})(np.ones(HEAD_COUNT, dtype=np.float32) * 0.25)


def publish(source: ModelSource, frame_id: int, eof: int):
  source.send_frame(Meta(frame_id, eof), Meta(frame_id, eof), transforms(), inputs(), np.zeros(8, dtype=np.float32))


def test_reply_is_the_answer_modeld_adopts(tmp_path):
  source = ModelSource(tmp_path, decoder({}), ADMIT)
  try:
    box = Mailbox(source.path)
    try:
      # one reply per camera frame: modeld reads a reply once and clears the envelope, and a second answer for a
      # frame it already took is a replay. It adopts after five warm-up frames
      picked = []
      for frame_id in range(1, 7):
        publish(source, frame_id=frame_id, eof=nanos_since_boot())
        frame = box.frame()
        assert frame is not None and frame.frame == frame_id and frame.session == source.session
        assert frame.desire.shape == (8,) and frame.action_t.shape == (2,)
        assert np.allclose(frame.img, np.eye(3)) and np.allclose(frame.big_img, np.eye(3) * 2)
        assert box.reply(frame.session, 1, frame.frame, frame.eof, np.ones(HEAD_COUNT, dtype=np.float32))
        picked.append(source.pick(local_heads()))
    finally:
      box.close()
    assert [adopted for _, adopted in picked[:-1]] == [False] * 5, picked
    assert picked[-1][1] is True
    assert picked[-1][0]["plan"].shape == HEAD_SHAPES["plan"]
  finally:
    source.close()


def test_stale_reply_is_never_adopted(tmp_path):
  source = ModelSource(tmp_path, decoder({}), ADMIT)
  try:
    eof = nanos_since_boot() - 4 * DEADLINE_NS
    publish(source, frame_id=1, eof=eof)
    box = Mailbox(source.path)
    try:
      frame = box.frame()
      assert box.reply(frame.session, 1, frame.frame, frame.eof, np.ones(HEAD_COUNT, dtype=np.float32))
    finally:
      box.close()
    local = local_heads()
    remote, adopted = source.pick(local)
    assert adopted is False and remote is local
  finally:
    source.close()


def test_foreign_session_and_wrong_length_are_refused(tmp_path):
  source = ModelSource(tmp_path, decoder({}), ADMIT)
  try:
    publish(source, frame_id=1, eof=nanos_since_boot())
    box = Mailbox(source.path)
    try:
      frame = box.frame()
      assert box.reply(frame.session + 1, 1, frame.frame, frame.eof, np.ones(HEAD_COUNT, dtype=np.float32))
      assert not box.reply(frame.session, 1, frame.frame, frame.eof, np.ones(HEAD_COUNT - 1, dtype=np.float32))
      assert not box.reply(frame.session, 1, frame.frame, frame.eof, np.full(HEAD_COUNT, np.nan, dtype=np.float32))
    finally:
      box.close()
    local = local_heads()
    _, adopted = source.pick(local)
    assert adopted is False
  finally:
    source.close()


def test_empty_slot_reads_as_no_frame(tmp_path):
  source = ModelSource(tmp_path, decoder({}), ADMIT)
  try:
    box = Mailbox(source.path)
    try:
      assert box.frame() is None
    finally:
      box.close()
  finally:
    source.close()


def test_head_offsets_cover_the_wire(tmp_path):
  assert HEAD_OFFSETS["plan"].start == 0
  assert max(part.stop for part in HEAD_OFFSETS.values()) == HEAD_PADDING.start
  assert HEAD_PADDING.stop == HEAD_COUNT
  assert sum(part.stop - part.start for part in HEAD_OFFSETS.values()) + HEAD_PADDING.stop - HEAD_PADDING.start == HEAD_COUNT