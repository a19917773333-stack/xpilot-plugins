"""Frame-bound lane estimates must use server capture time, not phone claims."""
import pytest
from phone_vision.frames import FrameStore


def test_lane_is_frame_bound_and_optional(tmp_path):
  now=1_000_000_000;s=FrameStore(tmp_path/'obs.json',lambda:now)
  s.publish(dict(capture_mono_ns=now,frame_id=7,jpeg_b64='fixture'))
  p=s.issue();lane=dict(version=1,model='vlaneDay.mnn',leftClass=2,rightClass=2,laneNumber=2,laneCount=3,
                        scope='visibleCorridor',control_eligible=False)
  r=s.accept(dict(request_id=p['request_id'],frame_id=7,left=None,right=None,lane_cp=lane))
  assert r['lane_cp']==lane and r['updated_mono_ns']==now
  with pytest.raises(ValueError):s.accept(dict(request_id=p['request_id'],frame_id=7,lane_cp=lane))
  p=s.issue();lane['control_eligible']=True
  with pytest.raises(ValueError):s.accept(dict(request_id=p['request_id'],frame_id=7,lane_cp=lane))
