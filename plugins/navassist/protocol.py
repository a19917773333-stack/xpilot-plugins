"""Stable protocol facade; parsing and state live in separate bounded modules."""
from .wire import SCHEMA_VERSION, LANE_ACTION_BITS, MAX_BODY_BYTES, NavAssistProtocolError, parse_snapshot
from .store import NavAssistStore
