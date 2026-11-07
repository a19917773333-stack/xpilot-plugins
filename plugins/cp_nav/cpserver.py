"""Bounded CPdazi v2 WebSocket ingress. One control lease and one phone peer.

LAN-only protocol compatibility: CP does not implement TesNav signed pairing.
No command, camera, arbitrary Params, model download or shell interface is exposed.
"""

import base64
import hashlib
import json
import socket
import select
import struct
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit
from .cp_catalog import JSON_STREAMS, manifest

MAX_FRAME = 262144


def exact(stream, n):
  parts = []
  while n:
    data = stream.read(n)
    if not data:
      raise EOFError()
    parts.append(data)
    n -= len(data)
  return b"".join(parts)


def receive(stream):
  a, b = exact(stream, 2)
  if a & 0x70 or not a & 0x80 or not b & 0x80:
    raise ValueError("masked_final_frame_required")
  op = a & 15
  n = b & 127
  if n == 126:
    n = struct.unpack("!H", exact(stream, 2))[0]
  elif n == 127:
    n = struct.unpack("!Q", exact(stream, 8))[0]
  if n > MAX_FRAME or (op >= 8 and n > 125):
    raise ValueError("frame_too_large")
  mask = exact(stream, 4)
  raw = exact(stream, n)
  return op, bytes(v ^ mask[i % 4] for i, v in enumerate(raw))


def send(sock, data, opcode=1):
  if isinstance(data, dict):
    data = json.dumps(data, allow_nan=False, separators=(",", ":")).encode()
  n = len(data)
  header = bytes([0x80 | opcode, n]) if n < 126 else bytes([0x80 | opcode, 126]) + struct.pack("!H", n)
  sock.sendall(header + data)


class CPServer(ThreadingHTTPServer):
  daemon_threads = True
  allow_reuse_address = True
  request_queue_size = 24

  def __init__(self, address, store, handler=None):
    self.store = store
    self.lock = threading.RLock()
    self.ready = threading.Condition(self.lock)
    self.owner = None
    self.applied = False
    self.slots = threading.BoundedSemaphore(24)
    self.connections = set()
    super().__init__(address, handler or Handler)

  def process_request(self, request, address):
    if not self.slots.acquire(False):
      self.shutdown_request(request)
      return
    with self.lock:
      self.connections.add(request)
    try:
      super().process_request(request, address)
    except Exception:
      with self.lock:
        self.connections.discard(request)
      self.slots.release()
      raise

  def process_request_thread(self, request, address):
    try:
      super().process_request_thread(request, address)
    finally:
      with self.lock:
        self.connections.discard(request)
      self.slots.release()

  def server_close(self):
    with self.lock:
      for sock in list(self.connections):
        try:
          sock.shutdown(socket.SHUT_RDWR)
        except OSError:
          pass
    super().server_close()


class Handler(BaseHTTPRequestHandler):
  protocol_version = "HTTP/1.1"
  rbufsize = 0

  def log_message(self, *args):
    pass

  def do_GET(self):
    path = urlsplit(self.path).path
    s = self.server
    peer = self.client_address[0]
    control = path == "/api/navi/ws/v2/control/amap_auto_1.0"
    pieces = path.split("/")
    stream = pieces[-1] if len(pieces) == 8 and pieces[:6] == ["", "api", "navi", "ws", "v2", "json"] else None
    with s.lock:
      if control:
        if s.owner is not None:
          self.send_error(409, "control_lease_busy")
          return
        s.owner = (peer, id(self))
        s.applied = False
        s.store.restart()
      else:
        if not (stream in JSON_STREAMS and pieces[-2] == s.store.session and s.owner and s.owner[0] == peer):
          self.send_error(404)
          return
        requested_session = pieces[-2]
        # Android enqueues manifest_applied and opens independent sockets in one
        # callback. A bound socket may arrive before its control frame is read.
        s.ready.wait_for(lambda: s.applied or not s.owner or s.store.session != requested_session, timeout=.75)
        if not (s.applied and s.owner and s.owner[0] == peer and s.store.session == requested_session):
          self.send_error(409, "manifest_not_applied")
          return
      session = s.store.session
    try:
      key = self.headers.get("Sec-WebSocket-Key", "")
      if (
        self.headers.get("Upgrade", "").lower() != "websocket"
        or "upgrade" not in self.headers.get("Connection", "").lower()
        or self.headers.get("Sec-WebSocket-Version") != "13"
        or len(base64.b64decode(key, validate=True)) != 16
      ):
        self.send_error(400)
        return
      digest = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
      self.send_response(101)
      self.send_header("Upgrade", "websocket")
      self.send_header("Connection", "Upgrade")
      self.send_header("Sec-WebSocket-Accept", digest)
      self.end_headers()
      self.connection.settimeout(3)
      missed = 0
      while True:
        if not select.select([self.connection], [], [], 20)[0]:
          missed += 1
          if missed > 2:
            break
          send(self.connection, b"", 9)
          continue
        op, payload = receive(self.rfile)
        missed = 0
        if op == 8:
          send(self.connection, payload, 8)
          break
        if op == 9:
          send(self.connection, payload, 10)
          continue
        if op == 10:
          continue
        if op != 1:
          raise ValueError("json_text_required")
        d = json.loads(payload, parse_constant=lambda x: (_ for _ in ()).throw(ValueError("nonfinite")))
        if not isinstance(d, dict):
          raise ValueError("object_required")
        with s.lock:
          if s.store.session != session:
            raise ValueError("expired_session")
          if control:
            if d.get("protocol_version") != 2:
              raise ValueError("protocol_version")
            if d.get("type") == "requirements_query":
              send(self.connection, manifest(session))
            elif d.get("type") == "manifest_applied" and d.get("session_id") == session and d.get("revision") == 1:
              s.applied = True
              s.ready.notify_all()
            else:
              raise ValueError("control_message")
          else:
            if d.get("name") != stream:
              raise ValueError("stream_mismatch")
            send(self.connection, s.store.accept(d))
    except (ValueError, UnicodeError, KeyError, TypeError) as e:
      try:
        send(self.connection, {"type": "protocol_error", "code": "rejected_message", "message": str(e)[:80]})
      except OSError:
        pass
    except (EOFError, OSError):
      pass
    finally:
      self.close_connection = True
      if control:
        with s.lock:
          if s.owner == (peer, id(self)):
            s.owner = None
            s.applied = False
            s.store.restart()
            s.ready.notify_all()
