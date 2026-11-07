"""CP7000 native BSM telemetry plus bounded, parked CP navigation settings."""

import base64
import hashlib
import json
import time
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlsplit, parse_qs
from .settings import NATIVE_KEYS, BOUNDS, param_key, read
from .cpserver import CPServer, send
from .cpmeta import SERVICES

CAPABILITIES = {
  "navigation_v2": True,
  "native_bsm": True,
  "phone_lane_model_observations": True,
  "images": False,
  "automatic_overtaking": False,
  "stereo": False,
  "side_radar_tracks": False,
  "remote_params": True,
  "remote_params_scope": "qualified_parked_cp_navigation_only",
  "model_download": False,
  "compact_services_available": ["carState", "modelV2"],
  "compact_reserved_fields": [
    "softHoldActive",
    "carrotCruise",
    "gearStep",
    "useLaneLineSpeed",
    "leftLaneLine",
    "rightLaneLine",
    "ureaGauge",
    "tpms",
  ],
}


class CPStatusServer(CPServer):
  def __init__(self,address,ingress,params,is_parked):
    from .cpmeta import Metadata
    self.metadata=Metadata();self.ingress=ingress;self.params=params;self.is_parked=is_parked
    super().__init__(address,None,handler=StatusHandler)

  def bound(self,peer):
    with self.ingress.lock:
      return bool(self.ingress.owner and self.ingress.owner[0]==peer and self.ingress.applied
                  and read(self.params).enabled)


SUPPORTED={k:v for k,v in NATIVE_KEYS.items() if v not in
           ('curve_mode','curve_min_kph','curve_factor_pct','countdown_mode')}



class StatusHandler(BaseHTTPRequestHandler):
  protocol_version = "HTTP/1.1"
  rbufsize = 0

  def log_message(self, *args):
    pass

  def reply(self, status, body):
    data = json.dumps(body).encode()
    self.send_response(status)
    self.send_header("Content-Type", "application/json")
    self.send_header("Content-Length", str(len(data)))
    self.send_header("Cache-Control", "no-store")
    self.end_headers()
    self.wfile.write(data)

  def do_POST(self):
    self.close_connection=True
    if urlsplit(self.path).path!='/api/param_set':
      self.reply(404,{'ok':False,'error':'unsupported'});return
    if (self.headers.get('Origin') or not self.server.bound(self.client_address[0])
        or not self.server.is_parked()):
      self.reply(403,{'ok':False,'error':'parked_bound_CP_required'});return
    try:
      self.connection.settimeout(2)
      length=int(self.headers.get('Content-Length','0'))
      if not 0<length<=4096 or self.headers.get('Transfer-Encoding'):
        raise ValueError('length')
      if self.headers.get('Content-Type','').split(';')[0]!='application/json':
        raise ValueError('content_type')
      d=json.loads(self.rfile.read(length),parse_constant=lambda v: (_ for _ in ()).throw(ValueError('finite')))
      if not isinstance(d,dict):raise ValueError('object')
    except (ValueError,OSError):
      self.reply(400,{'ok':False,'error':'invalid_request'});return
    name=d.get('name');value=d.get('value');field=SUPPORTED.get(name) if isinstance(name,str) else None
    if (field is None or type(value) is not int or not BOUNDS[field][0]<=value<=BOUNDS[field][1]):
      self.reply(422,{'ok':False,'error':'unsupported_or_out_of_bounds'});return
    # Recheck after receiving the body: a peer can stall while the vehicle moves.
    with self.server.ingress.lock:
      if not self.server.bound(self.client_address[0]) or not self.server.is_parked():
        self.reply(403,{'ok':False,'error':'state_changed'});return
      self.server.params.put(param_key(field),str(value))
    self.reply(200,{'ok':True,'name':name,'value':value})

  def do_GET(self):
    path = urlsplit(self.path).path
    if path == "/ws/compact_state" and self.headers.get("Upgrade", "").lower() == "websocket":
      self.telemetry()
      return
    if path == "/api/heartbeat_status":
      self.reply(
        200,
        {"ok": True, "hb": {"vehicle_fresh": self.server.metadata.read() is not None}, "capabilities": CAPABILITIES},
      )
    elif path == "/api/params_bulk":
      if not self.server.bound(self.client_address[0]):
        self.reply(403,{'ok':False,'error':'bound_CP_required'});return
      names=parse_qs(urlsplit(self.path).query).get('names',[''])[0].split(',')
      if len(names)>64 or any(len(n)>80 for n in names):
        self.reply(400,{'ok':False,'error':'too_many_names'});return
      settings=read(self.server.params)
      self.reply(200,{'ok':True,'values':{n:getattr(settings,SUPPORTED[n]) for n in names if n in SUPPORTED},
                      'unsupported':[n for n in names if n not in SUPPORTED]})
    else:
      self.reply(404, {"ok": False, "error": "unsupported"})

  def telemetry(self):
    key = self.headers.get("Sec-WebSocket-Key", "")
    try:
      if (
        len(base64.b64decode(key, validate=True)) != 16
        or self.headers.get("Sec-WebSocket-Version") != "13"
        or "upgrade" not in self.headers.get("Connection", "").lower()
      ):
        raise ValueError("bad_upgrade")
    except ValueError:
      self.reply(400, {"ok": False})
      return
    digest = base64.b64encode(hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode()).digest()).decode()
    self.send_response(101)
    self.send_header("Upgrade", "websocket")
    self.send_header("Connection", "Upgrade")
    self.send_header("Sec-WebSocket-Accept", digest)
    self.end_headers()
    self.close_connection = True
    self.connection.settimeout(2)
    last = 0
    ping = time.monotonic()
    try:
      send(self.connection, {"mode": "carrot-state-v1", "services": SERVICES, "capabilities": CAPABILITIES})
      while self.connection in self.server.connections:
        row = self.server.metadata.read()
        if row and row[0] != last:
          last = row[0]
          send(self.connection, row[1], 2)
        if time.monotonic() - ping > 2:
          send(self.connection, b"", 9)
          ping = time.monotonic()
        # Drain and validate client ping/pong/close without blocking metadata delivery.
        import select

        if select.select([self.connection], [], [], 0.2)[0]:
          from .cpserver import receive

          op, payload = receive(self.rfile)
          if op == 8:
            break
          if op == 9:
            send(self.connection, payload, 10)
          elif op != 10:
            break
    except (OSError, EOFError, ValueError):
      pass
