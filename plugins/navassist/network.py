"""Start the source-compatible transports; pairing is allowed only offroad."""
import threading

from .discovery import NavAssistDiscoveryServer, DISCOVERY_PORT
from .identity import NavAssistDeviceIdentity, NavAssistPairingStore
from .server import NavAssistHTTPServer
from .udp import NavAssistUDPServer

LISTEN_PORT = 7766


class NavigationTransports:
  def __init__(self, store, params, is_offroad):
    self.pairing = NavAssistPairingStore(params)
    identity = NavAssistDeviceIdentity.load_or_create(params=params)
    self.servers = []
    self.threads = []
    try:
      udp = NavAssistUDPServer(('0.0.0.0', 4213), store)
      self.geometry = udp.geometry
      self.servers.append(udp)
      self.servers.append(NavAssistHTTPServer(('0.0.0.0', LISTEN_PORT), store, identity, self.pairing))
      self.servers.append(NavAssistDiscoveryServer(('0.0.0.0', DISCOVERY_PORT), identity, self.pairing,
                                                 is_offroad=is_offroad))
      for server in self.servers:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.threads.append(thread)
    except Exception:
      self.close()
      raise

  def close(self):
    for index, server in enumerate(self.servers):
      if index < len(self.threads):
        server.shutdown()
      server.server_close()
    for thread in self.threads:
      thread.join(timeout=2)
