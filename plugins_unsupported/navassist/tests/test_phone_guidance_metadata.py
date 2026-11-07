"""Failures first: optional metadata already emitted by the phone rejects the
entire otherwise valid navigation snapshot. Accept only bounded documented
fields; do not derive lane number or control permissions from metadata. Reject
diagnostics must retain a field name without logging private packet values.
"""
import json,re
from pathlib import Path
from dataclasses import asdict
import pytest
from navassist.wire import parse_snapshot,NavAssistProtocolError,GUIDANCE_KEYS
from .test_navassist import snapshot_body
from .test_legacy_udp_receiver import run_server,stop_server,send

META=dict(parallelRoadStatus='main',elevatedRoadStatus='side',routeNoticeType='congestion',
          routeNoticeDistanceM=250,routeNoticeObservedAtMs=1,turnSignalHold=True,turnSignalCountdownS=30)


def body(**metadata):
  data=json.loads(snapshot_body())
  data['guidance'].update(metadata)
  return json.dumps(data).encode()


def test_current_phone_guidance_fields_are_recognized_by_receiver():
  root=Path(__file__).resolve().parents[3]
  source=(root/'companion/tesnav/app/src/main/kotlin/com/garan/tesnav/export/NavAssistV2Protocol.kt').read_text()
  fields=re.search(r'data class NavAssistV2Guidance\((.*?)\n\)',source,re.S)[1]
  assert set(re.findall(r'val (\w+):',fields))<=GUIDANCE_KEYS
  schema=json.loads((root/'plugins/navassist/nav-assist-v3.schema.json').read_text())
  assert set(META)<=set(schema['$defs']['guidance']['properties'])


@pytest.mark.parametrize('field',META)
def test_documented_phone_metadata_does_not_discard_navigation(field):
  original=parse_snapshot(body())
  with_metadata=parse_snapshot(body(**{field:META[field]}))
  for key in ('maneuver','maneuver_distance_m','lanes','latitude','longitude','route_active','route_matched'):
    assert getattr(with_metadata,key)==getattr(original,key)


def test_metadata_remains_data_and_does_not_override_freshness_or_route_facts():
  snap=parse_snapshot(body(**META))
  assert snap.parallel_road_status=='main' and snap.turn_signal_hold
  assert snap.maneuver=='turn_left' and snap.maneuver_distance_m==120
  assert snap.lane_total_count==3


@pytest.mark.parametrize('bad',[dict(parallelRoadStatus='mars'),dict(elevatedRoadStatus=1),
 dict(routeNoticeType='run_command'),dict(routeNoticeDistanceM=-5),dict(routeNoticeObservedAtMs=-1),
 dict(turnSignalHold='true'),dict(turnSignalCountdownS=3601),dict(extraUndocumentedField=True)])
def test_bad_metadata_is_still_rejected(bad):
  with pytest.raises(NavAssistProtocolError):parse_snapshot(body(**bad))


def test_reject_field_diagnostics_do_not_echo_packet_values():
  store,server,thread=run_server()
  try:
    assert send(server.server_address[1],body(maneuver='PRIVATE_VALUE_NOT_FOR_LOGS')) is None
    d=server.diagnostics()
    assert d['last_reject_field']=='maneuver' and d['last_reject_reason']=='malformed'
    assert 'PRIVATE_VALUE' not in json.dumps(d)
  finally:stop_server(server,thread)
