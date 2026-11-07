from __future__ import annotations
import time,json,math,threading,secrets,hashlib,base64
from pathlib import Path
from .limits import MAX_AGE_NS
import hmac,gzip
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

class BridgeServer(ThreadingHTTPServer):
  daemon_threads = True
  def __init__(self, address, token, store):
    super().__init__(address, Handler)
    self.token, self.store = token, store


class Handler(BaseHTTPRequestHandler):
  protocol_version = "HTTP/1.1"
  disable_nagle_algorithm = True

  def log_message(self, *_):
    pass

  def setup(self):
    super().setup()
    self.connection.settimeout(3)

  def respond(self, status, data):
    body = json.dumps(data, allow_nan=False).encode()
    # Explicit app opt-in: older clients require a known decoded Content-Length.
    camera_response = status == 200 and self.path == '/v1/frame'
    compressed = (camera_response and len(body) >= 16_384 and
                  self.headers.get('X-Phone-Vision-Encoding') == 'gzip-v1' and
                  'gzip' in [item.strip().lower() for item in self.headers.get('Accept-Encoding', '').split(',')])
    if compressed:
      encoded = gzip.compress(body, compresslevel=1)
      if len(encoded) < len(body):
        body = encoded
      else:
        compressed = False
    self.send_response(status)
    if camera_response:
      self.send_header('Vary', 'Accept-Encoding, X-Phone-Vision-Encoding')
    if compressed:
      self.send_header('Content-Encoding', 'gzip')
    self.send_header('Content-Type', 'application/json')
    self.send_header('Content-Length', str(len(body)))
    self.send_header('Cache-Control', 'no-store')
    if status != 200:
      # Failed/oversized POST bodies may be unread: never parse them as another request.
      self.send_header('Connection', 'close')
      self.close_connection = True
    self.end_headers()
    self.wfile.write(body)

  def authorized(self):
    return hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer '+self.server.token)

  def do_GET(self):
    if not self.authorized():
      return self.respond(401, {'error': 'authentication'})
    if self.path != '/v1/frame':
      return self.respond(404, {'error': 'not_found'})
    try:
      self.respond(200, self.server.store.issue(fresh=True, buffered=True))
    except ValueError as e:
      self.respond(503, {'error': str(e)})

  def do_POST(self):
    if not self.authorized():
      return self.respond(401, {'error': 'authentication'})
    if self.path != '/v1/observation':
      return self.respond(404, {'error': 'not_found'})
    try:
      length = int(self.headers.get('Content-Length', '0'))
      if not 0 < length <= 8192:
        raise ValueError('body_size')
      data = json.loads(self.rfile.read(length))
      if not isinstance(data, dict):
        raise ValueError('body_type')
      self.server.store.accept(data)
      self.respond(200, {'accepted': True, 'control_eligible': False})
    except (ValueError, TypeError) as e:
      self.respond(400, {'error': str(e)})

