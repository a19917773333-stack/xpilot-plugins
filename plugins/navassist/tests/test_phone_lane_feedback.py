"""The HUD model observation must reach phone feedback, with its original age;
legacy absolute-lane feedback and legacy ACK shapes must remain unchanged."""
import json
from types import SimpleNamespace as N
from navassist.feedback import lane_model_feedback


def test_single_frame_estimate_feedback_is_route_bound_and_expires(tmp_path):
  path=tmp_path/'estimate.json';now=1_000_000_000
  data=dict(version=1,valid=True,laneNumber=2,laneCount=3,captureMonoNs=now,
    source='cpPhoneVision',scope='visibleCorridor',controlEligible=False,
    navSessionId='s',routeRevision=2)
  path.write_text(json.dumps(data));snap=N(session_id='s',route_revision=2)
  out=lane_model_feedback(snap,path=path,now_ns=now)
  assert out['valid'] and out['laneNumber']==2 and out['laneCount']==3
  assert not lane_model_feedback(snap,path=path,now_ns=now+800_000_001)['valid']
  assert not lane_model_feedback(N(session_id='new',route_revision=2),path=path,now_ns=now)['valid']
  assert not lane_model_feedback(N(session_id='s',route_revision=3),path=path,now_ns=now)['valid']


def test_model_replaces_original_position_channel_and_does_not_fall_back_when_stale(tmp_path):
  from navassist.feedback import lane_position_feedback
  model=tmp_path/'model';geometry=tmp_path/'geometry';now=1_000_000_000
  model.write_text(json.dumps(dict(enabled=True,version=1,valid=True,laneNumber=2,laneCount=3,
    captureMonoNs=now,source='cpPhoneVision',scope='visibleCorridor',controlEligible=False,
    navSessionId='s',routeRevision=2)))
  snapshot=N(session_id='s',route_revision=2)
  out=lane_position_feedback(snapshot,path=geometry,model_path=model,now_ns=now)
  assert out['valid'] and out['laneIndex']==2 and out['source']=='cpPhoneVision'
  assert out['absoluteConfirmed'] is False and out['validForMs']==800
  assert not lane_position_feedback(snapshot,path=geometry,model_path=model,now_ns=now+800_000_001)['valid']
  assert not lane_position_feedback(N(session_id='s',route_revision=3),path=geometry,model_path=model,now_ns=now)['valid']


def test_missing_line_codes_do_not_turn_into_dashed_and_expiry_clears_codes():
  from navassist.vehicle_lines import observe
  missing=observe(N(),1_000_000_000,1_000_000_000,enabled=True,vehicle_fresh=True)
  assert missing['left']['type']=='unknown' and missing['left']['code'] is None
  assert not missing['supported']
  found=observe(N(leftLaneLine=10,rightLaneLine=21),1_000_000_000,1_000_000_000,enabled=True,vehicle_fresh=True)
  assert found['left']['type']=='dashed' and found['left']['color']=='white'
  assert found['right']['type']=='solid' and found['right']['color']=='yellow'
  assert observe(N(leftLaneLine=10),1,1_000_000_000,enabled=True,vehicle_fresh=True)['left']['code'] is None
  assert observe(N(leftLaneLine=10),1,1,enabled=False,vehicle_fresh=True)['left']['code'] is None
