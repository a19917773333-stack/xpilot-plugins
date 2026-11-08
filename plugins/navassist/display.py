"""Fresh, named-producer state only; an expired message clears the display."""

KINDS = {'nav': 'nav.state', 'intent': 'lanes.intent', 'oem': 'oem.lanes', 'topology': 'lanes.topology'}


def guidance_visible(nav):
  """Fresh route text is useful even when localization forbids vehicle assistance."""
  return bool(nav.get('valid') or (nav.get('linked') and not nav.get('stale', True)
    and nav.get('routeActive') and nav.get('mode') == 'realtime'
    and nav.get('maneuver') not in (None, '', 'none', 'unknown')))


def guidance_only(nav):
  return guidance_visible(nav) and not nav.get('valid', False)


def read_state(messages):
  result = {}
  for field, kind in KINDS.items():
    value = messages.fresh(kind).get('navassist')
    result[field] = value if isinstance(value, dict) else {}
  return result


def signal_status(intent):
  """A lamp is preparation, never evidence that SP has accepted a lane change."""
  if not intent.get('signalRequested'):
    return ''
  if intent.get('targetLaneIndex', -1) < 0:
    return 'WAIT LANE CONFIRMATION' if intent.get('signalPurpose') == 'lanePreparation' else 'TURN SIGNAL ONLY'
  reason = str(intent.get('reason', '')).lower()
  if 'blindspot' in reason:
    return 'WAIT BLINDSPOT'
  if 'crossing' in reason:
    return 'WAIT LANE BOUNDARY'
  if 'observ' in reason or 'stabiliz' in reason:
    return 'WAIT LANE CONFIRMATION'
  if intent.get('spLaneChangeReady'):
    return 'READY - SP CHECKS'
  return 'WAIT SIGNAL CONFIRMATION'
