"""Paced snapshots with headroom for card diagnostics and broker queue jitter.

No catch-up batches: every deadline is based on the actual send time. Keep the
two control inputs at 20 Hz; navigation display and OEM metadata need less.
"""


class CyclePublisher:
  CHANNELS = (
    ('nav', 'nav.state', 1000, 200_000_000),
    ('topology', 'lanes.topology', 150, 50_000_000),
    ('intent', 'lanes.intent', 200, 50_000_000),
    ('oem', 'oem.lanes', 500, 100_000_000),
  )

  def __init__(self, send):
    self.send = send
    self.next_ns = {}

  def publish(self, result, now_ns):
    for key, kind, ttl, interval in self.CHANNELS:
      if now_ns >= self.next_ns.get(kind, 0):
        self.next_ns[kind] = now_ns+interval
        self.send(kind, result[key], ttl)
