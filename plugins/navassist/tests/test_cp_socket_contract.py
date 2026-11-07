"""Wire contract specified before server: real masked frames, peer/session binding, expiry."""

import base64
import json
import os
import socket
import struct
import threading
from contextlib import contextmanager
from navassist.cpnav import CPStore
from navassist.cpserver import CPServer


@contextmanager
def server():
  s = CPServer(("127.0.0.1", 0), CPStore())
  t = threading.Thread(target=s.serve_forever, daemon=True)
  t.start()
  try:
    yield s
  finally:
    s.shutdown()
    s.server_close()
    t.join(2)


def connect(s, path):
  c = socket.create_connection(s.server_address, timeout=2)
  f = c.makefile("rb")
  key = base64.b64encode(os.urandom(16)).decode()
  c.sendall(
    (
      f"GET {path} HTTP/1.1\r\nHost: localhost\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
    ).encode()
  )
  assert b"101" in f.readline()
  while f.readline() != b"\r\n":
    pass
  return c, f


def send(c, obj):
  b = json.dumps(obj).encode()
  mask = os.urandom(4)
  h = bytes([0x81, 0x80 | len(b)]) if len(b) < 126 else bytes([0x81, 0xFE]) + struct.pack("!H", len(b))
  c.sendall(h + mask + bytes(v ^ mask[i % 4] for i, v in enumerate(b)))


def receive(f):
  h = f.read(2)
  n = h[1] & 127
  if n == 126:
    n = struct.unpack("!H", f.read(2))[0]
  return json.loads(f.read(n))


def test_real_control_and_bound_stream():
  with server() as s:
    c, f = connect(s, "/api/navi/ws/v2/control/amap_auto_1.0")
    send(c, {"type": "requirements_query", "protocol_version": 2})
    m = receive(f)
    assert m["type"] == "subscription_manifest"
    assert len(m["streams"]) == 28
    assert not any(x["enabled"] for x in m["streams"] if x["kind"] != "json")
    send(c, {"type": "manifest_applied", "protocol_version": 2, "session_id": m["session_id"], "revision": 1})
    d, g = connect(s, f"/api/navi/ws/v2/json/{m['session_id']}/vehicle")
    import time

    stamp = time.time_ns() // 1_000_000
    send(
      d,
      {
        "type": "item_update",
        "protocol_version": 2,
        "session_id": m["session_id"],
        "kind": "json",
        "name": "vehicle",
        "manifest_revision": 1,
        "stream_handle": 1,
        "schema_version": 1,
        "sequence": 1,
        "source_timestamp_ms": stamp,
        "sent_at_ms": stamp,
        "present": True,
        "value": {"lat": 23.0, "lon": 113.0, "virtual_gps": False},
      },
    )
    assert receive(g)["accepted"] is True
    send(d, {"type": "item_update"})
    assert receive(g)["type"] == "protocol_error"
    d.close()
    c.close()


def test_unmasked_frame_is_rejected():
  with server() as s:
    c, f = connect(s, "/api/navi/ws/v2/control/amap_auto_1.0")
    c.sendall(b"\x81\x02{}")
    assert receive(f)["type"] == "protocol_error"
    c.close()
