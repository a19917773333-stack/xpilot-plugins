"""Bound CPdazi v2 source observations -> the shared navigation coordinator.

Arrival/heartbeat never makes an old source observation fresh. Data is read-only;
there are no passing requests, lane-command, camera or model-control endpoints.
"""

import copy
import math
import threading
import time
import uuid
from .cp_catalog import JSON_STREAMS, TURN_TYPES

ROUTE_SCOPED = frozenset(("guidance_current", "guidance_next", "lane_current", "lane_ahead",
                         "speed", "traffic_signal", "crossroad", "navigation_status"))


def model_observation(lane):
  if lane.get('lane_source') not in ('model', 'map+model'):
    return None
  count, current = lane.get('model_count'), lane.get('model_current_lane')
  if type(count) is not int or type(current) is not int or not 1 <= current <= count <= 16:
    return None
  return dict(count=count, laneNumber=current, source='cpPhoneVision', confirmed=False, mapAssociated=False)


class CPStore:
  def __init__(self, clock_ms=None, clock_ns=None):
    self.wall = clock_ms or (lambda: time.time_ns() // 1_000_000)
    self.mono = clock_ns or time.monotonic_ns
    self.lock = threading.RLock()
    self.restart()

  def restart(self):
    with self.lock:
      self.session = str(uuid.uuid4())
      self.revision = 1
      self.event = 1
      self.handles = {name: i + 1 for i, name in enumerate(JSON_STREAMS)}
      self.rows = {}
      self.sequences = {}
      self.observation_stamps = {}
      self.withdrawn = set()
      self._event_key = None
      self._route_key = None
      self._distance = None
      self.route_cutoff = -1

  def current(self, now_ns=None):
    return self

  def is_stale(self, now_ns=None):
    return not self.normalized(self.mono() if now_ns is None else now_ns)["valid"]

  def accept(self, d, now_ms=None):
    now = self.wall() if now_ms is None else now_ms
    with self.lock:
      if not isinstance(d, dict):
        raise ValueError("invalid_envelope")
      name = d.get("name")
      if not isinstance(name, str):
        raise ValueError("invalid_stream")
      if (
        d.get("type") != "item_update"
        or d.get("protocol_version") != 2
        or d.get("session_id") != self.session
        or d.get("manifest_revision") != 1
        or d.get("kind") != "json"
        or name not in self.handles
        or d.get("stream_handle") != self.handles[name]
        or d.get("schema_version") != 1
      ):
        raise ValueError("unbound_stream")
      seq, stamp, sent = d.get("sequence"), d.get("source_timestamp_ms"), d.get("sent_at_ms")
      if (
        type(seq) is not int
        or not 0 <= seq < 2**63
        or seq <= self.sequences.get(name, -1)
        or type(stamp) is not int
        or type(sent) is not int
        or not -500 <= now - stamp <= 1500
        or not stamp <= sent <= now + 500
      ):
        raise ValueError("stale_or_replay")
      present = d.get("present")
      value = d.get("value")
      if type(present) is not bool or (present and not isinstance(value, dict)):
        raise ValueError("invalid_value")
      # An absent envelope is timed at withdrawal, not at sensor acquisition.
      # Compare observations with observations; a new GPS sample may legitimately
      # predate the administrative withdrawal while advancing the real sensor.
      if present and (name in ROUTE_SCOPED or name == "route") and stamp < self.route_cutoff:
        raise ValueError("previous_route_observation")
      previous = self.observation_stamps.get(name)
      if present and previous is not None and (
        stamp < previous or (name in self.withdrawn and stamp == previous)
      ):
        raise ValueError("source_time_regression")
      if present:
        self.observation_stamps[name] = stamp
        self.withdrawn.discard(name)
      else:
        self.withdrawn.add(name)
      if name == "route" and not present and self.rows.get("route", (None,))[0] is not None:
        self.revision += 1
        self.event += 1
        self.route_cutoff = stamp
        self._route_key = self._event_key = self._distance = None
        for key in ROUTE_SCOPED:
          self.rows.pop(key, None)
      self.sequences[name] = seq
      self.rows[name] = (copy.deepcopy(value) if present else None, stamp, self.mono(), max(0, now - stamp))
      return {"type": "item_ack", "sequence": seq, "name": name, "accepted": True}

  def _value(self, name, now_ns):
    row = self.rows.get(name)
    if row is None:
      return {}
    value, stamp, received, initial_age = row
    return value or {} if 0 <= now_ns - received <= max(0, 1500 - initial_age) * 1_000_000 else {}

  def normalized(self, now_ns):
    from .navstate import empty_state

    with self.lock:
      v, g, n, r = (self._value(k, now_ns) for k in ("vehicle", "guidance_current", "navigation_status", "route"))
      coords = (v.get("lat"), v.get("lon"))
      location = (
        all(type(x) in (int, float) and math.isfinite(x) for x in coords)
        and -90 <= coords[0] <= 90
        and -180 <= coords[1] <= 180
        and v.get("virtual_gps") is False
      )
      turn = g.get("turn_type")
      maneuver = TURN_TYPES.get(turn, "unknown") if type(turn) is int else "unknown"
      distance = g.get("distance_m")
      guide = type(distance) in (int, float) and math.isfinite(distance) and 0 <= distance <= 100000
      active = (
        n.get("mode") == "guiding"
        and n.get("guidance_active") is True
        and n.get("route_present") is True
        and n.get("off_route", False) is False
        and bool(r)
      )
      valid = bool(location and guide and active and maneuver != "unknown")
      route_key = r.get("total_distance_m")
      if valid:
        if self._route_key is not None and route_key is not None and route_key != self._route_key:
          self.revision += 1
          self.event += 1
        self._route_key = route_key
        key = (maneuver, g.get("road_name"))
        if self._event_key is not None and (
          key != self._event_key or (self._distance is not None and distance > self._distance + 50)
        ):
          self.event += 1
        self._event_key, self._distance = key, distance
      lane = self._value("lane_current", now_ns)
      count = lane.get("count", lane.get("lane_count", 0))
      items = lane.get("lanes", lane.get("items", []))
      lanes = []
      if (lane.get("lane_source", "map") in ("map", "map+model")
          and type(count) is int and 1 <= count <= 16 and isinstance(items, list) and len(items) == count):
        for i, item in enumerate(items):
          if not isinstance(item, dict) or type(item.get("index")) is not int or item.get("index") != i:
            lanes = []
            break
          lanes.append(
            {
              "index": i,
              "recommended": item.get("is_recommended", False) is True,
              "allowedActions": [],
              "recommendedActions": [],
            }
          )
      out = empty_state("none" if valid else "cpSourceUnconfirmed")
      out.update(
        valid=valid,
        stale=not valid,
        linked=bool(guide and active),
        source="cpdazi",
        mode="realtime" if active else "idle",
        routeActive=bool(active),
        sessionId=self.session,
        routeRevision=self.revision,
        maneuverEventId=self.event,
        sequence=max(self.sequences.values(), default=0),
        maneuver=maneuver,
        distanceM=distance if guide else 0.0,
        lanes=lanes,
        laneTotalCount=count if lanes else -1,
        laneGuidanceSource="map" if lanes else "none",
        modelLaneEstimate=model_observation(lane),
      )
      nxt = self._value("guidance_next", now_ns)
      nt = nxt.get("turn_type")
      nd = nxt.get("distance_m", 0)
      out.update(
        nextManeuver=TURN_TYPES.get(nt, "none") if type(nt) is int else "none",
        nextDistanceM=nd if type(nd) in (int, float) and math.isfinite(nd) and 0 <= nd <= 100000 else 0,
      )
      return out
