"""Explicit single-camera worker. Disabled plugin means no process or camera client."""
import secrets
import threading
import time
from pathlib import Path

from openpilot.common.params import Params
from openpilot.tesla import plugins
from .bridge import FrameStore, BridgeServer, capture


def main():
  params = plugins.view(Params())
  token = params.get('ExtPhoneVisionToken')
  if not isinstance(token, str) or len(token) < 32:
    legacy = Path('/data/phone-vision/connection-code')
    token = legacy.read_text().strip() if legacy.is_file() else secrets.token_hex(32)
    if not 32 <= len(token) <= 128:
      raise ValueError('Invalid connection code')
    params.put('ExtPhoneVisionToken', token)
  width = params.get('ExtPhoneVisionWidth', return_default=True)
  width = width if type(width) is int and width in (320, 640) else 640
  roi = Path('/data/phone-vision/roi.json')
  if not roi.is_file():
    roi = Path(__file__).with_name('roi.example.json')
  store = FrameStore(Path('/dev/shm/phone_side_vehicles.json'))

  def watchdog():
    while True:
      store.expire()
      time.sleep(.2)

  def worker():
    while True:
      # Do not map camera buffers before a phone explicitly asks for a frame.
      if not store.frame_requested.wait(.5):
        continue
      try:
        capture(store, roi, 4, width, 75, 'wide')
      except Exception:
        store.new_stream()
        time.sleep(1)

  threading.Thread(target=watchdog, daemon=True).start()
  threading.Thread(target=worker, daemon=True).start()
  with BridgeServer(('0.0.0.0', 8767), token, store) as server:
    server.serve_forever()
