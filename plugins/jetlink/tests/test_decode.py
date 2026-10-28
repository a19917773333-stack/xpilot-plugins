"""Decoding the phone's raw output into the heads modeld reads, and the admission test applied to it."""
import numpy as np

from openpilot.tesla.model_source import HEAD_SHAPES

from ..decode import HEAD_OFFSETS, HEAD_PADDING, admit, decoder

SCALE = 0.25


def raw(value: float = SCALE) -> np.ndarray:
  return np.ones(HEAD_PADDING.stop, dtype=np.float32) * value


def test_head_ordered_decode_matches_every_head():
  heads = decoder({})(raw())
  assert set(HEAD_SHAPES) <= set(heads)
  for name, shape in HEAD_SHAPES.items():
    assert heads[name].shape == shape, name
  assert np.isfinite(heads["plan"]).all()


def test_every_head_reads_its_own_slice():
  flat = raw(0.0)
  for name, at in HEAD_OFFSETS.items():
    flat[at] = 1.0
  heads = decoder({})(flat)
  for name in HEAD_SHAPES:
    assert float(np.squeeze(heads[name]).flat[0]) == 1.0, name


def test_admit_keeps_a_matching_plan_and_drops_a_foreign_one():
  local = decoder({})(raw())
  near = {key: value.copy() for key, value in local.items()}
  assert admit(local, near)
  far = {key: value.copy() for key, value in local.items()}
  far["plan"][0, :, 1] += 5.0
  assert not admit(local, far)


def test_admit_drops_a_frame_without_a_plan():
  assert not admit(decoder({})(raw()), {"lane_lines": np.zeros(HEAD_SHAPES["lane_lines"], dtype=np.float32)})