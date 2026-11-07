"""CP native classifications are visible-corridor observations, never clearance."""


def validate(value):
  if value is None:
    return None
  if not isinstance(value, dict):
    raise ValueError('invalid_lane_observation')
  expected = ('version','leftClass','rightClass','laneNumber','laneCount')
  if any(type(value.get(k)) is not int for k in expected):
    raise ValueError('invalid_lane_numbers')
  left, right = value['leftClass'], value['rightClass']
  if (value['version'] != 1 or not 1 <= left <= 3 or not 1 <= right <= 3
      or value['laneNumber'] != left or value['laneCount'] != left+right-1
      or value.get('model') not in ('vlaneDay.mnn','vlaneNight.mnn')
      or value.get('scope') != 'visibleCorridor' or value.get('control_eligible') is not False):
    raise ValueError('invalid_lane_contract')
  return {k:value[k] for k in (*expected,'model','scope','control_eligible')}
