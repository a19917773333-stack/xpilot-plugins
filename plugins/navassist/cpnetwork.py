"""CP profile's only ingress: no TesNav listener and no source fallback."""

import socket
import threading
import json
from .cpserver import CPServer
from .cpstatus import StatusServer
from .cpmeta import Metadata


class CPTransports:
  def __init__(self, store, params, is_offroad):
    self.metadata = Metadata()
    self.servers = []
    self.threads = []
    self.stop = threading.Event()
    self.pairing = None
    try:
      self.servers.append(CPServer(("0.0.0.0", 7714), store))
      self.servers.append(StatusServer(("0.0.0.0", 7000), self.metadata))
      for server in self.servers:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        self.threads.append(t)
    except Exception:
      self.close()
      raise
    self.discovery = threading.Thread(target=self.advertise, daemon=True)
    self.discovery.start()

  def advertise(self):
    # UDP discovery contains no location, license, identity or control permission.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
      sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
      data = json.dumps(
        {
          "version": "X-Pilot CP compatibility",
          "port": 7706,
          "navigation_port": 7714,
          "status_port": 7000,
          "automatic_overtaking": False,
          "images": False,
        }
      ).encode()
      while not self.stop.wait(2):
        try:
          sock.sendto(data, ("255.255.255.255", 7705))
        except OSError:
          pass

  def close(self):
    self.stop.set()
    for i, server in enumerate(self.servers):
      if i < len(self.threads):
        server.shutdown()
      server.server_close()
    for t in self.threads:
      t.join(2)
    if hasattr(self, "discovery"):
      self.discovery.join(2)
