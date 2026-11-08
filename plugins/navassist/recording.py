"""Bounded private navigation recordings; no pairing or device keys are recorded."""
from dataclasses import dataclass
import gzip
import json
import math
import os
from pathlib import Path
import re
import time
import uuid

MAX_LOG_BYTES=128*1024*1024
MAX_FILES=180
MAX_FILE_SECONDS=60
LOG_PATTERN=re.compile(r'^navdiag-(\d{13})-(\d{13})-([0-9a-f]{8})\.jsonl\.gz$')
PARTIAL_PATTERN=re.compile(r'^navdiag-\d{13}-[0-9a-f]{8}\.partial$')

def log_root():
  return Path('/data/media/0/xpilot-navdiagnostics')

def finite_values(value):
  if isinstance(value, float):
    return value if math.isfinite(value) else None
  if isinstance(value, dict):
    return {k: finite_values(v) for k, v in value.items()}
  if isinstance(value, (tuple, list)):
    return [finite_values(v) for v in value]
  return value


@dataclass(frozen=True)
class NavigationLogFile:
  path: Path
  start_ms: int
  end_ms: int
  size: int
  modified_ns: int


def scan_logs(root: Path | None = None) -> tuple[NavigationLogFile, ...]:
  root = root if root is not None else log_root()
  if not root.is_dir() or root.is_symlink():
    return ()
  result = []
  for path in root.iterdir():
    match = LOG_PATTERN.fullmatch(path.name)
    if not match or path.is_symlink() or not path.is_file():
      continue
    try:
      stat = path.stat()
      result.append(NavigationLogFile(path, int(match[1]), int(match[2]), stat.st_size, stat.st_mtime_ns))
    except OSError:
      continue
  return tuple(sorted(result, key=lambda item: (item.start_ms, item.path.name)))



class Recorder:
  def __init__(self, root: Path | None = None, *, max_bytes: int = MAX_LOG_BYTES, max_files: int = MAX_FILES,
               max_seconds: int = MAX_FILE_SECONDS):
    self.root = root if root is not None else log_root()
    self.max_bytes, self.max_files, self.max_seconds = max_bytes, max_files, max_seconds
    self.stream = None
    self.partial: Path | None = None
    self.start_ms = 0
    self.token = ''
    self.raw_bytes = 0
    self.metadata: dict | None = None
    self._prune()

  def write(self, record: dict, *, wall_ms: int | None = None) -> None:
    now = time.time_ns() // 1_000_000 if wall_ms is None else wall_ms
    if self.stream is not None and (now - self.start_ms >= self.max_seconds * 1000 or self.raw_bytes >= 8 * 1024 * 1024):
      self.close(wall_ms=now)
    if self.stream is None:
      self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
      self.root.chmod(0o700)
      self.start_ms, self.token = now, uuid.uuid4().hex[:8]
      self.partial = self.root / f'navdiag-{now:013d}-{self.token}.partial'
      self.stream = gzip.open(self.partial, 'xb', compresslevel=1)
      self.partial.chmod(0o600)
      self.raw_bytes = 0
      if self.metadata is not None:
        header = (json.dumps(finite_values(self.metadata), ensure_ascii=False, allow_nan=False) + '\n').encode()
        self.stream.write(header)
        self.raw_bytes += len(header)
    data = (json.dumps(finite_values(record), ensure_ascii=False, separators=(',', ':'), allow_nan=False) + '\n').encode()
    if len(data) > 64 * 1024:
      raise ValueError('导航样本超过 64 KiB')
    self.stream.write(data)
    self.raw_bytes += len(data)

  def close(self, *, wall_ms: int | None = None) -> None:
    if self.stream is None or self.partial is None:
      return
    now = time.time_ns() // 1_000_000 if wall_ms is None else wall_ms
    self.stream.close()
    self.stream = None
    final = self.root / f'navdiag-{self.start_ms:013d}-{max(now, self.start_ms):013d}-{self.token}.jsonl.gz'
    os.replace(self.partial, final)
    self.partial = None
    self._prune()

  def _prune(self) -> None:
    files = list(scan_logs(self.root))
    if self.root.is_dir() and not self.root.is_symlink():
      for path in self.root.iterdir():
        if PARTIAL_PATTERN.fullmatch(path.name) and not path.is_symlink() and path.is_file() and path != self.partial:
          stat = path.stat()
          files.append(NavigationLogFile(path, int(path.name.split('-')[1]), 0, stat.st_size, stat.st_mtime_ns))
    files.sort(key=lambda item: (item.start_ms, item.path.name))
    size = sum(item.size for item in files)
    # Reserve space for the current <=8 MiB raw block plus one bounded record.
    budget = self.max_bytes - min(9 * 1024 * 1024, self.max_bytes // 8)
    while files and (len(files) > self.max_files or size > budget):
      old = files.pop(0)
      try:
        old.path.unlink()
        size -= old.size
      except OSError:
        pass

