"""CPdazi-v2 interoperability contract, before adapter implementation.
No source-time refresh from heartbeat, no replay/reconnect mixing, native BSM independent.
"""

import pytest
from navassist.cpnav import CPStore


def update(store, name, value, stamp=1_000_000, seq=1):
  return store.accept(
    {
      "type": "item_update",
      "protocol_version": 2,
      "session_id": store.session,
      "kind": "json",
      "name": name,
      "manifest_revision": 1,
      "stream_handle": store.handles[name],
      "schema_version": 1,
      "sequence": seq,
      "source_timestamp_ms": stamp,
      "sent_at_ms": stamp,
      "present": value is not None,
      "value": value,
    },
    now_ms=stamp,
  )


def ready():
  s = CPStore(clock_ms=lambda: 1_000_000, clock_ns=lambda: 1_000_000_000_000)
  update(s, "vehicle", {"lat": 23.0, "lon": 113.0, "speed_kph": 54.0, "virtual_gps": False})
  update(s, "navigation_status", {"mode": "guiding", "guidance_active": True, "route_present": True})
  update(s, "route", {"remain_distance_m": 10000, "remain_time_sec": 900, "total_distance_m": 12000})
  update(s, "guidance_current", {"turn_type": 13, "distance_m": 300, "road_name": "road"})
  update(s, "lane_current", {"count": 3, "lanes": [{"index": i, "is_recommended": i == 2} for i in range(3)]})
  return s


def test_cp_navigation_normalizes_real_v2_streams():
  s = ready()
  n = s.normalized(1_000_000_000_000)
  assert n["valid"] and n["source"] == "cpdazi"
  assert n["maneuver"] == "turn_right" and n["distanceM"] == 300
  assert n["lanes"][-1]["recommended"] and n["laneTotalCount"] == 3


def test_heartbeat_does_not_renew_source_time_and_absent_clears():
  s = ready()
  assert not s.normalized(1_003_000_000_000)["valid"]
  with pytest.raises(ValueError):
    update(s, "vehicle", {"lat": 23.0, "lon": 113.0}, seq=1)
  update(s, "guidance_current", None, seq=2)
  assert not s.normalized(1_000_000_000_000)["valid"]


def test_unbound_or_wrong_stream_session_rejected():
  s = ready()
  with pytest.raises(ValueError):
    s.accept({"type": "item_update", "protocol_version": 2, "session_id": "other"}, now_ms=1_000_000)
  s.restart()
  assert not s.normalized(1_000_000_000_000)["valid"]


def test_cp_and_original_use_same_bounded_preparation():
  from types import SimpleNamespace as N
  from navassist.runtime import NavigationRuntime
  from navassist.settings import NavSettings
  from navassist.tests.test_migration_contract import model

  s = ready()
  r = NavigationRuntime(NavSettings())
  for tick in range(20):
    now = 1_000_000_000_000 + tick * 50_000_000
    out = r.tick(
      s,
      model(frame=tick + 1),
      now,
      N(vEgo=15.0, rightBlinker=True, rightBlindspot=True),
      N(latActive=True),
      now,
      vehicle_fresh=True,
    )
  assert out["intent"]["signalRequested"]
  assert not out["intent"]["spLaneChangeReady"]
