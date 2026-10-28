"""The peer's half of openpilot/tesla/model_source.py's mailbox.

modeld publishes one META record per frame (session, frame ids, timestamps, the warp transforms and the packed
inputs); the peer answers in the reply slot with ENVELOPE + BGM1 and the raw model output. Each side takes a
nonblocking byte-range lock over its own slot, so neither ever reads a half-written record.
"""
import fcntl
import mmap
import os
from pathlib import Path
from typing import NamedTuple

import numpy as np

from openpilot.tesla.model_source import ENVELOPE, META, OFFSET, REPLY, SIZE, nanos_since_boot

# what modeld's ModelSource._candidate accepts: the whole slot, the BGM1 body inside it, and the float count
WIRE_LENGTH = 8320
REPLY_LENGTH = 8280
HEAD_COUNT = 2066
MAGIC = b"XMS1"
BGM = b"BGM1"


class Frame(NamedTuple):
  session: int
  frame: int
  eof: int
  img: np.ndarray
  big_img: np.ndarray
  desire: np.ndarray
  traffic_convention: np.ndarray
  action_t: np.ndarray


class Mailbox:
  """One open model-source file: read the published frame, write the phone's reply."""

  def __init__(self, path):
    self.path = Path(path)
    self.fd = os.open(self.path, os.O_RDWR)
    self.buffer = mmap.mmap(self.fd, SIZE)

  def close(self) -> None:
    self.buffer.close()
    os.close(self.fd)

  def _locked(self, offset: int, size: int):
    try:
      fcntl.lockf(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB, size, offset)
    except OSError:
      return None
    return True

  def _unlock(self, offset: int, size: int) -> None:
    fcntl.lockf(self.fd, fcntl.LOCK_UN, size, offset)

  def frame(self) -> Frame | None:
    """The newest frame modeld published, or None when the meta slot is busy or empty."""
    if not self._locked(0, OFFSET):
      return None
    try:
      data = self.buffer[0:OFFSET]
    finally:
      self._unlock(0, OFFSET)
    if not data[:4] == MAGIC:
      return None
    magic, version, session, frame, _extra, eof, _extra_eof, *values = META.unpack_from(data)
    if (magic, version) != (MAGIC, 1):
      return None
    floats = np.asarray(values, dtype=np.float32)
    return Frame(session, frame, eof, floats[0:9].reshape(3, 3), floats[9:18].reshape(3, 3),
                 floats[18:26], floats[26:28], floats[28:30])

  def reply(self, session: int, epoch: int, frame: int, eof: int, raw: np.ndarray) -> bool:
    """Publish one answer, the way modeld's _candidate reads it: envelope, BGM1 header, then the raw floats."""
    if raw.shape != (HEAD_COUNT,) or not np.isfinite(raw).all():
      return False
    if not self._locked(OFFSET, SIZE - OFFSET):
      return False
    try:
      arrival = nanos_since_boot()
      body = REPLY.pack(BGM, 2, 0x11, 0, frame, REPLY_LENGTH, eof) + raw.astype(np.float32).tobytes()
      envelope = ENVELOPE.pack(session, epoch, arrival, 3, WIRE_LENGTH)
      self.buffer[OFFSET:OFFSET + len(envelope)] = envelope
      self.buffer[OFFSET + len(envelope):OFFSET + len(envelope) + len(body)] = body
      return True
    finally:
      self._unlock(OFFSET, SIZE - OFFSET)