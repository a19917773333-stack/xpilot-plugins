"""Reuse an existing bridge OpenCV install inside this worker only; no installer."""
import importlib
from pathlib import Path
import sys

LEGACY_PATHS = ('/data/phone-vision/pydeps', '/data/wide-capture/pydeps')


def load_opencv(paths=LEGACY_PATHS):
  try:
    return importlib.import_module('cv2')
  except ModuleNotFoundError as exc:
    if exc.name != 'cv2':
      raise
  for directory in paths:
    if Path(directory).is_dir() and directory not in sys.path:
      sys.path.append(directory)
  return importlib.import_module('cv2')
