"""Private LAN UDP ingress owned by the active source:navigation plugin.

The socket is limited to RFC1918 IPv4, 100 packets per second and 20 packets
per peer per second. Only the last admitted peer can receive an acknowledgement.
"""
import ipaddress
import json
import socket
import time


NETWORKS = tuple(ipaddress.ip_network(value) for value in
                 ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16'))
PORT = 4213
MAX_BYTES = 8192


def private_peer(host):
  try:
    address = ipaddress.ip_address(host)
    return address.version == 4 and any(address in network for network in NETWORKS)
  except ValueError:
    return False


def authorized(provider):
  from openpilot.common.params import Params
  from openpilot.tesla.plugins import active
  return any(plugin.NAME == provider and 'source:navigation' in plugin.CLAIMS for plugin in active(Params()))


class NavigationIngress:
  def __init__(self, provider, *, authorize=None, transport=None):
    self.authorize = authorize or (lambda: authorized(provider))
    self.sock, self.peer = transport, None
    self.window, self.total, self.counts = int(time.monotonic()), 0, {}
    self._check()
    if self.sock is None:
      self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
      try:
        self.sock.settimeout(.05)
        self.sock.bind(('0.0.0.0', PORT))
      except BaseException:
        self.close()
        raise

  def _check(self):
    if not self.authorize():
      self.close()
      raise PermissionError('Navigation provider is not the enabled source owner')

  def receive(self):
    self._check()
    self.peer = None
    try:
      body, address = self.sock.recvfrom(MAX_BYTES + 1)
    except socket.timeout:
      return None
    now = time.monotonic()
    if int(now) != self.window:
      self.window, self.total, self.counts = int(now), 0, {}
    self.total += 1
    if self.total > 100 or not private_peer(address[0]) or not 0 < len(body) <= MAX_BYTES:
      return None
    count = self.counts.get(address[0], 0) + 1
    self.counts[address[0]] = count
    if count > 20:
      return None
    self.peer = (address, now)
    return body, address[0]

  def ack(self, value):
    self._check()
    if self.peer is None or time.monotonic() - self.peer[1] > .5:
      raise PermissionError('No current navigation peer')
    if (set(value) != {'messageType', 'schemaVersion', 'sessionId', 'sequence'}
        or value['messageType'] != 'navassist_udp_ack' or value['schemaVersion'] != 3
        or not isinstance(value['sessionId'], str) or not 1 <= len(value['sessionId']) <= 64
        or type(value['sequence']) is not int or not 1 <= value['sequence'] < 2**63):
      raise ValueError('Invalid navigation acknowledgement')
    body = json.dumps(value, separators=(',', ':')).encode()
    self.sock.sendto(body, self.peer[0])
    self.peer = None

  def close(self):
    if self.sock is not None:
      self.sock.close()
    self.peer = None

  def __enter__(self):
    return self

  def __exit__(self, *_args):
    self.close()
