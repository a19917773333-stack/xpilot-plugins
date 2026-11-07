"""CPdazi8 v2 JSON catalog, interoperable field names; no image subscription."""

JSON_STREAMS = (
  "vehicle",
  "guidance_current",
  "guidance_next",
  "lane_current",
  "lane_ahead",
  "speed",
  "traffic_signal",
  "crossroad",
  "route",
  "navigation_status",
  "app_status",
  "camera_state",
  "composition_state",
)
IMAGE_STREAMS = (
  "tbt_current_compact",
  "tbt_current_full",
  "tbt_next",
  "traffic_signal",
  "lane_top",
  "lane_bottom",
  "safety_primary",
  "safety_secondary",
  "safety_section",
  "crossroad_minimized",
  "crossroad_expanded",
  "center_tbt_icon",
  "center_tbt_text",
  "center_tbt_fee",
)
CATALOG = (
  tuple(("json", n) for n in JSON_STREAMS) + tuple(("image", n) for n in IMAGE_STREAMS) + (("render", "map_main"),)
)
TURN_TYPES = {
  12: "turn_left",
  13: "turn_right",
  14: "u_turn_left",
  16: "sharp_left",
  17: "keep_left",
  19: "sharp_right",
  51: "straight",
  6: "merge_right",
  7: "merge_left",
  101: "exit_right",
  102: "exit_left",
  1000: "slight_left",
  1001: "slight_right",
  201: "destination",
  **{i: "roundabout" for i in (131, 132, 133, 134, 139, 140, 141, 142)},
}


def manifest(session):
  return {
    "type": "subscription_manifest",
    "protocol_version": 2,
    "session_id": session,
    "revision": 1,
    "streams": [
      {
        "kind": kind,
        "name": name,
        "schema_version": 1,
        "stream_handle": i + 1,
        "enabled": kind == "json",
        "params": (
          {"delivery_mode": "on_change_with_heartbeat", "interval_ms": 500, "stale_timeout_ms": 1500}
          if kind == "json"
          else {}
        ),
      }
      for i, (kind, name) in enumerate(CATALOG)
    ],
  }
