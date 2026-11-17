import json
from pathlib import Path

from ..pulse import PULSE_TTL_NS, MaintenancePulse


def test_pulse_fires_once_and_clears():
  now = [10]
  pulse = MaintenancePulse(clock=lambda: now[0])

  assert not pulse.take(now[0])
  pulse.request()
  assert pulse.take(now[0])
  assert not pulse.take(now[0])

  now[0] += PULSE_TTL_NS + 1
  pulse.request()
  now[0] += PULSE_TTL_NS + 1
  assert not pulse.take(now[0])
  pulse.request()
  assert pulse.take(now[0])


def test_manifest_allows_only_the_fixed_one_shot_can2_frame():
  manifest = json.loads((Path(__file__).parents[1] / "plugin.json").read_text())
  rule = manifest["rules"][0]

  assert manifest["claims"] == ["can.tx:0x339:1"]
  assert (rule["tx_address"], rule["tx_bus"], rule["tx_length"], rule["max_count"]) == (0x339, 1, 8, 1)
  assert rule["constant_mask"] == [0, 0, 0, 0, 255, 255, 255, 255]
  assert rule["constant_value"] == [0, 0, 0, 0, 0, 128, 0, 0]
