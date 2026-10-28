"""Raw phone output -> the heads openpilot's modeld reads, and the test the mailbox applies before adopting one.

Two layouts are possible. A phone whose model publishes output_slices returns that layout, and xpilot's Parser
turns the raw heads into the plan/lane/lead dicts. Without a spec the peer returns the parsed heads themselves,
flattened in HEAD_SHAPES order (openpilot/tesla/model_source.py) and padded to the wire, so they are only
reshaped here: running a parsed plan through the Parser again would read its standard deviations as means.
"""
import numpy as np

from openpilot.selfdrive.modeld.parse_model_outputs import Parser
from openpilot.tesla.model_source import HEAD_SHAPES

from .mailbox import HEAD_COUNT

OFFSETS = {}
_at = 0
for _name, _shape in HEAD_SHAPES.items():
  OFFSETS[_name] = slice(_at, _at + int(np.prod(_shape)))
  _at += int(np.prod(_shape))
assert _at <= HEAD_COUNT, (_at, HEAD_COUNT)
HEAD_OFFSETS = dict(OFFSETS)
HEAD_PADDING = slice(_at, HEAD_COUNT)


def decoder(output_slices: dict[str, slice]):
  """decode(raw) -> heads, for the slices the phone's model publishes (the head order and padding by default)."""
  if not output_slices:
    def decode_heads(raw: np.ndarray) -> dict:
      return {name: raw[np.newaxis, at].reshape(HEAD_SHAPES[name]) for name, at in HEAD_OFFSETS.items()}

    return decode_heads

  parser = Parser(ignore_missing=True)
  slices = dict(output_slices)

  def decode(raw: np.ndarray) -> dict:
    return parser.parse_outputs({name: raw[np.newaxis, at] for name, at in slices.items()})

  return decode


def admit(local: dict, remote: dict, *, lateral_m: float = 3.0) -> bool:
  """Adopt a phone frame only when it is the same drive: a plan within a lane width of the local one.

  Timing, shape, finiteness and session are modeld's own checks; this is the policy xpilot keeps for itself, and
  it is deliberately loose: two runs of one model differ by centimetres, a foreign model by metres.
  """
  plan = remote.get("plan")
  if plan is None:
    return False
  local_plan = local.get("plan")
  if local_plan is not None:
    lateral = np.abs(plan[0, :, 1] - local_plan[0, :, 1])
    if not np.isfinite(lateral).all() or float(lateral.max()) > lateral_m:
      return False
  return True