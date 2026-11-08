"""Failure cases before implementation: the old manifest required a missing host
navigation_ingress hook and the worker imported a host module that was absent.
"""
from pathlib import Path

from openpilot.tesla import manifest as mf

ROOT = Path(__file__).resolve().parents[1]


class FakeSocket:
  def __init__(self, packet):
    self.packet = packet
    self.sent = []
    self.closed = False

  def recvfrom(self, _limit):
    return self.packet

  def sendto(self, body, peer):
    self.sent.append((body, peer))

  def close(self):
    self.closed = True


def test_manifest_uses_plugin_local_ingress():
  manifest = mf.parse(ROOT / 'plugin.json')
  ok, reason = mf.compatible(manifest, mf.HOST_CAPS)
  assert ok, reason
  assert 'navigation_ingress' not in manifest.requires['hooks']
  assert 'source:navigation' in manifest.claims
  assert 'process:tesnavd' in manifest.claims


def test_private_ingress_accepts_and_acknowledges_one_peer():
  from tesnav.ingress import NavigationIngress

  sock = FakeSocket((b'{}', ('192.168.1.25', 4213)))
  ingress = NavigationIngress('tesnav', authorize=lambda: True, transport=sock)
  assert ingress.receive() == (b'{}', '192.168.1.25')
  ingress.ack({'messageType': 'navassist_udp_ack', 'schemaVersion': 3,
               'sessionId': 'fixture', 'sequence': 1})
  assert len(sock.sent) == 1
  ingress.close()
  assert sock.closed
