"""Failure cases before implementation: ABI-2 rules, a host-only lane dataclass
import, and the removed buzzer_policy hook keep the package undiscoverable.
"""
from pathlib import Path

from openpilot.tesla import manifest as mf

ROOT = Path(__file__).resolve().parents[1]


def test_manifest_matches_current_host_capabilities():
  manifest = mf.parse(ROOT / 'plugin.json')
  ok, reason = mf.compatible(manifest, mf.HOST_CAPS)
  assert ok, reason
  assert manifest.requires['rule_abi'] == 1
  assert 'buzzer_policy' not in manifest.requires['hooks']
  assert all(rule['type'] == 'template_clone.v1' and 'engagement' not in rule for rule in manifest.rules)


def test_entry_does_not_publish_removed_host_interfaces():
  from navassist.plugin import NavAssist
  from navassist.policy import LaneChangeLimits

  assert not hasattr(NavAssist, 'buzzer_policy')
  assert LaneChangeLimits().allow_start is True
