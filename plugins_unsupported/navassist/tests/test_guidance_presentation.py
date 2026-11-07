"""Display-only source linkage must not become control permission."""
import copy

from navassist.display import guidance_visible, guidance_only


def test_localization_loss_keeps_fresh_guidance_without_mutating_control_state():
  nav = dict(valid=False, linked=True, stale=False, routeActive=True,
             mode='realtime', maneuver='turn_right', reason='localLocalization')
  original = copy.deepcopy(nav)
  assert guidance_visible(nav)
  assert guidance_only(nav)
  assert nav == original
  assert not nav['valid']


def test_phone_localization_loss_is_display_only_too():
  nav = dict(valid=False, linked=True, stale=False, routeActive=True,
             mode='realtime', maneuver='turn_left', reason='phoneLocalization')
  assert guidance_visible(nav)
  assert guidance_only(nav)


def test_expired_unlinked_inactive_or_unknown_guidance_cannot_display():
  nav = dict(valid=False, linked=True, stale=False, routeActive=True,
             mode='realtime', maneuver='turn_right', reason='localLocalization')
  for change in ({'stale': True}, {'linked': False}, {'routeActive': False},
                 {'mode': 'idle'}, {'maneuver': 'unknown'}, {'maneuver': 'none'}):
    assert not guidance_visible(dict(nav, **change))
    assert not guidance_only(dict(nav, **change))
  assert not guidance_visible({})


def test_control_valid_state_keeps_existing_display_without_warning():
  assert guidance_visible(dict(valid=True))
  assert not guidance_only(dict(valid=True))
