"""jetlink_modeld: openpilot's own modeld with the mailbox peer attached.

The local model runs every frame and stays the one that drives; the peer's answers are adopted only when they
arrive inside openpilot/tesla/model_source.py's deadline and pass decode.admit, so a link that is down or late is
a local frame, never a stall.
"""
import json
from pathlib import Path
from tempfile import gettempdir

from openpilot.tesla.model_source import ModelSource

from .decode import decoder
from .decode import admit as admit_heads

SPEC_PARAM = "XpilotJetlinkSpec"
MAILBOX_PARAM = "XpilotJetlinkMailbox"


def slices_from_spec(value) -> dict[str, slice]:
  """{'plan': [0, 495], ...} from the spec jetlink writes, or {} for the head-ordered default."""
  try:
    spec = json.loads(value) if isinstance(value, str) else (value or {})
    return {name: slice(int(bounds[0]), int(bounds[1])) for name, bounds in spec["output_slices"].items()}
  except Exception:
    return {}


def main() -> None:
  from openpilot.common.params import Params
  from openpilot.tesla.plugin_params import ParamsView
  from openpilot.selfdrive.modeld.modeld import run_with_model_source
  params = ParamsView(Params())
  source = ModelSource(gettempdir(), decoder(slices_from_spec(params.get(SPEC_PARAM))), admit_heads)
  params.put(MAILBOX_PARAM, str(source.path), block=True)
  try:
    run_with_model_source(source)
  finally:
    if Path(params.get(MAILBOX_PARAM) or "/nonexistent") == Path(source.path):
      params.remove(MAILBOX_PARAM)
    source.close()


if __name__ == "__main__":
  main()
