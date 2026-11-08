import json
import socket
import threading

from navassist.protocol import NavAssistStore
from navassist.server import ClientRateLimiter
from navassist.tests.test_legacy_protocol import SOURCE_WALL_MS, encode, payload
from navassist.udp import MAX_UDP_SNAPSHOT_BYTES, NavAssistUDPServer, UDP_ACK_TYPE


def run_server(*, max_requests: int = 20):
  store = NavAssistStore(wall_clock_ms=lambda: SOURCE_WALL_MS)
  server = NavAssistUDPServer(
    ("127.0.0.1", 0), store,
    rate_limiter=ClientRateLimiter(max_requests=max_requests),
  )
  thread = threading.Thread(target=server.serve_forever, daemon=True)
  thread.start()
  return store, server, thread


def stop_server(server: NavAssistUDPServer, thread: threading.Thread) -> None:
  server.shutdown()
  thread.join(timeout=1)
  server.server_close()
  assert not thread.is_alive()


def send(port: int, body: bytes) -> dict | None:
  with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as client:
    client.settimeout(0.25)
    client.sendto(body, ("127.0.0.1", port))
    try:
      response, _ = client.recvfrom(1024)
    except TimeoutError:
      return None
  return json.loads(response)


def test_udp_accepts_canonical_v3_snapshot_without_credentials():
  store, server, thread = run_server()
  try:
    response = send(server.server_address[1], encode(payload()))
    assert response == {
      "messageType": UDP_ACK_TYPE,
      "schemaVersion": 3,
      "sessionId": "session-a",
      "sequence": 1,
    }
    assert store.current().snapshot.session_id == "session-a"
    assert server.diagnostics()['accepted'] == 1
    assert server.diagnostics()['received'] == 1
  finally:
    stop_server(server, thread)


def test_udp_silently_drops_replay_malformed_oversize_and_rate_limited_data():
  _, server, thread = run_server(max_requests=2)
  try:
    body = encode(payload())
    assert send(server.server_address[1], body) is not None
    assert send(server.server_address[1], body) is None
    assert send(server.server_address[1], b'{"echo_cmd":"id"}') is None
    assert send(server.server_address[1], b"x" * (MAX_UDP_SNAPSHOT_BYTES + 1)) is None
    stats = server.diagnostics()
    assert stats['received'] == 4 and stats['accepted'] == 1
    assert stats['rejected']['replay'] == 1
    assert stats['rejected']['invalidLength'] == 1
    assert 'session-a' not in json.dumps(stats)
  finally:
    stop_server(server, thread)


def test_lane_position_query_is_opt_in_and_bound_to_latest_navigation(monkeypatch):
  _, server, thread = run_server()
  try:
    query = {"messageType": "lane_position_request", "sessionId": "session-a", "sequence": 1}
    port=server.server_address[1]
    assert send(port,json.dumps(query).encode()) is None
    legacy=send(port,encode(payload()))
    assert 'lanePosition' not in legacy
    feedback=send(port,json.dumps(query).encode())
    assert feedback['lanePosition']['valid'] is False
    assert feedback['lanePosition']['laneIndex'] is None
    assert feedback['sessionId']=='session-a' and feedback['sequence']==1
    from navassist import udp as udp_receiver
    monkeypatch.setattr(udp_receiver, 'lane_position_feedback',
                        lambda snapshot: feedback['lanePosition'] | {'valid':True,'laneIndex':2,'laneCount':4})
    numbered=send(port,json.dumps(query).encode())
    assert numbered['lanePosition']['laneIndex']==2
    assert numbered['lanePosition']['laneCount']==4
    assert send(port,json.dumps(query | {'sessionId':'old'}).encode()) is None
    assert send(port,json.dumps(query | {'sequence':True}).encode()) is None
    assert send(port,json.dumps(query | {'sequence':2}).encode()) is None
  finally:
    stop_server(server,thread)


def test_model_lane_feedback_requires_explicit_query_opt_in(monkeypatch):
  from navassist import udp as receiver
  _,server,thread=run_server()
  try:
    port=server.server_address[1];send(port,encode(payload()))
    query=dict(messageType='lane_position_request',sessionId='session-a',sequence=1)
    monkeypatch.setattr(receiver,'lane_model_feedback',lambda snapshot:dict(valid=True,laneNumber=2,laneCount=3))
    assert 'laneEstimate' not in send(port,json.dumps(query).encode())
    response=send(port,json.dumps(dict(query,laneEstimateVersion=1)).encode())
    assert response['laneEstimate']['laneNumber']==2 and 'lanePosition' in response
    assert send(port,json.dumps(dict(query,laneEstimateVersion=True)).encode()) is None
  finally:stop_server(server,thread)
