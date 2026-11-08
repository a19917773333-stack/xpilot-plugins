"""The tile's label must distinguish a disabled link, live frames and a prepared engine."""
from ..status import tile_state


def test_status_prefers_the_live_peer_message():
  assert tile_state(1, "served 250 frames", {"stage": "ready"}, {"ready": True}) == "served 250 frames"


def test_off_mode_is_named_even_when_an_old_spec_is_ready():
  assert tile_state(0, "", {"stage": "ready"}, {"ready": True}) == "link off"


def test_failed_setup_takes_priority_over_a_stale_ready_spec():
  assert tile_state(1, "", {"stage": "failed", "msg": "see the log"}, {"ready": True}) == "setup failed"


def test_waiting_for_the_phone_does_not_claim_the_engine_is_ready():
  assert tile_state(1, "", {"stage": "waiting"}, {}) == "waiting for phone"


def test_empty_peer_status_uses_the_ready_spec_instead_of_link_off():
  assert tile_state(1, "", {"stage": "ready", "msg": "engine ready"}, {"ready": True}) == "engine ready"
  assert tile_state(1, None, {}, {"ready": True}) == "engine ready"
