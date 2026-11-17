"""One-shot latch for a user-pressed maintenance command."""
import threading
import time

PULSE_TTL_NS = 1_000_000_000


class MaintenancePulse:
  def __init__(self, clock=time.monotonic_ns):
    self._clock = clock
    self._lock = threading.Lock()
    self._pending_until_ns = 0

  def request(self) -> None:
    deadline = self._clock() + PULSE_TTL_NS
    with self._lock:
      self._pending_until_ns = deadline

  def take(self, now_ns: int) -> bool:
    with self._lock:
      deadline = self._pending_until_ns
      self._pending_until_ns = 0
    return deadline != 0 and now_ns <= deadline
