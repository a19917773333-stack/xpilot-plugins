"""Failures first: the original Android client can open JSON sockets before
its control-socket manifest_applied frame is processed. Keep session/peer binding
but permit a bounded handshake reorder; do not accept an unbound or stale lease.
"""
import concurrent.futures
import time
from .test_cp_socket_contract import server,connect,send,receive


def test_bound_stream_waits_briefly_for_manifest_application():
 with server() as s:
  c,f=connect(s,'/api/navi/ws/v2/control/amap_auto_1.0')
  try:
   send(c,{'type':'requirements_query','protocol_version':2});m=receive(f)
   with concurrent.futures.ThreadPoolExecutor() as pool:
    pending=pool.submit(connect,s,f"/api/navi/ws/v2/json/{m['session_id']}/vehicle")
    time.sleep(.05)
    send(c,{'type':'manifest_applied','protocol_version':2,'session_id':m['session_id'],'revision':1})
    d,g=pending.result(timeout=2);d.close();g.close()
  finally:c.close();f.close()
