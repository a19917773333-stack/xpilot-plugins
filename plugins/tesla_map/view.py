"""ASCII diagnostic text; stale broker messages never leave old values on screen."""


def lines(snapshot):
  if not snapshot or not snapshot.get('fresh'):
    return ('MAP unavailable', 'VEH 0x238 - no fresh data', '', '')
  limit, branch = snapshot['limit'], snapshot['branch']
  raw = snapshot['raw']
  value = str(limit['value']) if limit['value'] is not None else 'UNLIMITED' if limit['unlimited'] else '--'
  distance = '--' if branch['distanceM'] is None else 'NOW' if branch['distanceM'] == 0 else str(branch['distanceM'])+' m'
  comparison = snapshot.get('comparison', {})
  fused = comparison.get('fusedMps')
  unit = 1/3.6 if limit['unit'] == 'KPH' else .44704
  sp = '--' if fused is None else f'{fused/unit:.0f}'
  return (f'MAP <= {value} {limit["unit"]} C{limit["code"]}',
          f'FORK {branch["side"].upper()} {distance}',
          f'SP {sp} {comparison.get("state", "NONE")}',
          f'T{limit["type"]} D{limit["dependency"]} MATCH {raw.get("gpsRoadMatch", 0)} AGE {snapshot["ageMs"]:.0f}ms')
