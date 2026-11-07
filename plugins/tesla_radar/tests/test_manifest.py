"""Radar mode manifest.

Failure cases:
- A fresh install defaults to ARS408 on a car with only the factory radar.
- The settings row does not expose all three explicit modes.
"""
import json
from pathlib import Path


MANIFEST = Path(__file__).resolve().parents[1] / "plugin.json"


def test_fresh_install_defaults_to_factory_radar_and_names_three_modes():
  manifest = json.loads(MANIFEST.read_text())
  assert manifest["params"]["XpilotTeslaRadarBackend"]["default"] == "0"
  assert manifest["settings"] == [{
    "key": "XpilotTeslaRadarBackend",
    "label": "Radar mode",
    "choices": [["Factory radar", 0], ["ARS408 radar", 1], ["Radar off", 2]],
  }]
