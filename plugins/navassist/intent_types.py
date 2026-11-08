from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class LaneIntentDirection(IntEnum):
  none = 0
  left = 1
  right = 2


class ObservedLaneChangeState(IntEnum):
  off = 0
  pre = 1
  starting = 2
  finishing = 3


_LANE_CHANGE_STATE_NAMES = {
  0: "off",
  1: "preLaneChange",
  2: "laneChangeStarting",
  3: "laneChangeFinishing",
}
_LANE_CHANGE_DIRECTION_NAMES = {0: "none", 1: "left", 2: "right"}


def _enum_name(value, names, default):
  raw = getattr(value, "raw", value)
  try:
    mapped = names.get(int(raw))
  except (TypeError, ValueError):
    mapped = None
  if mapped is not None:
    return mapped
  name = getattr(value, "name", None)
  text = str(name if isinstance(name, str) else raw).split(".")[-1]
  normalized = "".join(char for char in text.lower() if char.isalnum())
  for candidate in names.values():
    if normalized == candidate.lower():
      return candidate
  return default


def lane_change_state_name(value) -> str:
  return _enum_name(value, _LANE_CHANGE_STATE_NAMES, "off")


def lane_change_direction_name(value) -> str:
  return _enum_name(value, _LANE_CHANGE_DIRECTION_NAMES, "none")


@dataclass(frozen=True)
class NavLanePlan:
  valid: bool
  session_id: str
  route_revision: int
  maneuver_event_id: int
  lane_count: int
  recommended_indices: tuple[int, ...]
  heuristic: bool = False
  edge_direction: LaneIntentDirection = LaneIntentDirection.none
  force_fork: bool = False
  allow_unknown_crossing: bool = False
  ignore_solid_boundary: bool = False
  observation_interrupted: bool = False
  relative_change_limit: int | None = None


@dataclass(frozen=True)
class LaneTopologyInput:
  valid_for_control: bool
  visible_lane_count: int
  ego_lane_index: int
  left_neighbor_exists: bool | None
  right_neighbor_exists: bool | None
  left_crossing_allowed: bool
  right_crossing_allowed: bool


@dataclass(frozen=True)
class LaneVehicleInput:
  lateral_active: bool
  speed_mps: float
  left_blindspot: bool = False
  right_blindspot: bool = False
  left_blinker: bool = False
  right_blinker: bool = False
  brake_pressed: bool = False
  gas_pressed: bool = False
  steering_pressed: bool = False
  lane_change_state: ObservedLaneChangeState = ObservedLaneChangeState.off
  lane_change_direction: LaneIntentDirection = LaneIntentDirection.none


@dataclass(frozen=True)
class NavTurnPlan:
  valid: bool
  session_id: str
  route_revision: int
  maneuver_event_id: int
  maneuver: str
  distance_m: float


@dataclass(frozen=True)
class NavLaneIntent:
  signal_requested: bool = False
  lane_change_ready: bool = False
  direction: LaneIntentDirection = LaneIntentDirection.none
  request_id: int = 0
  target_lane_index: int = -1
  reason: str = "idle"

