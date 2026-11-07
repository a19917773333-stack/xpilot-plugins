"""Radar mode manifest.

Failure cases:
- A fresh install defaults to ARS408 on a car with only the factory radar.
- The settings row does not expose all three explicit modes.
- The radar triangle display cannot be disabled from the same settings page.
"""
import json
from pathlib import Path


MANIFEST = Path(__file__).resolve().parents[1] / "plugin.json"


def test_fresh_install_defaults_to_factory_radar_and_names_three_modes():
  manifest = json.loads(MANIFEST.read_text())
  assert manifest["params"]["XpilotTeslaRadarBackend"]["default"] == "0"
  assert manifest["settings"][0] == {
    "key": "XpilotTeslaRadarBackend",
    "label": "Radar mode",
    "choices": [["Factory radar", 0], ["ARS408 radar", 1], ["Radar off", 2]],
  }


def test_triangle_display_is_an_ext_toggle_on_the_same_settings_page():
  manifest = json.loads(MANIFEST.read_text())
  triangle = {
    "key": "ExtTeslaRadarTriangle",
    "label": "Radar triangle display",
  }
  assert manifest["settings"] == [{
    "key": "XpilotTeslaRadarBackend",
    "label": "Radar mode",
    "choices": [["Factory radar", 0], ["ARS408 radar", 1], ["Radar off", 2]],
  }, triangle]
  assert manifest["params"][triangle["key"]] == {"type": "BOOL", "default": "1"}
