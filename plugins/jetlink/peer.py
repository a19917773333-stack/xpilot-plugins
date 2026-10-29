"""jetlink_peer: the phone on the other end of the mailbox.

modeld publishes one frame per camera frame; this process warps that camera frame on the comma's GPU, sends it
over the link jetlinkd holds, and writes the phone's raw output back. Nothing here is on the car's critical path:
no published frame, no link or no reply in time is a local frame.
"""
import time

import numpy as np

from .mailbox import HEAD_COUNT, Mailbox

MAILBOX_PARAM = "XpilotJetlinkMailbox"
SPEC_PARAM = "XpilotJetlinkSpec"
STATUS_PARAM = "XpilotJetlinkStatus"
CONNECT_TIMEOUT = 30.0
FRAME_TIMEOUT = 0.05


def address(buf) -> int:
  """The address of a camera buffer's pixels, as the warp reads them."""
  addr = getattr(buf, "addr", None)
  return int(addr) if addr is not None else int(np.frombuffer(buf, dtype=np.uint8).ctypes.data)


def wait_mailbox(params, timeout: float = CONNECT_TIMEOUT):
  import os
  from pathlib import Path
  deadline = time.monotonic() + timeout
  while time.monotonic() < deadline:
    path = params.get(MAILBOX_PARAM)
    if path and Path(path).exists():
      return Mailbox(os.fspath(path))
    time.sleep(0.1)
  return None


def open_client(log):
  """The link jetlinkd lends: the gadget on the cable, or whatever transport the owner set up."""
  from jetlink.openpilot.link import Link
  return Link(log, name="xpilot_peer").open(deadline=time.monotonic() + CONNECT_TIMEOUT)


def prepare_engine(client, value, log) -> None:
  """Make sure the phone has this model built; only a spec jetlink wrote says which one."""
  import json
  try:
    spec = json.loads(value) if isinstance(value, str) else (value or {})
    if spec.get("sha256") and spec.get("onnx_path"):
      client.ensure_engine(spec["sha256"], int(spec["nbytes"]), spec["onnx_path"])
  except Exception:
    log.warning("jetlink: could not prepare the phone's engine; the link decides")


def main() -> None:
  import time as _time

  from openpilot.common.params import Params
  from openpilot.tesla.plugin_params import ParamsView
  from openpilot.common.swaglog import cloudlog
  from msgq.visionipc import VisionIpcClient, VisionStreamType
  from jetlink.openpilot.warp import Warp, Warps

  from .seam import adapter

  params = Params()
  params = ParamsView(Params())
  box = wait_mailbox(params)
  if box is None:
    cloudlog.warning("jetlink: modeld published no mailbox, the phone stays unused")
    return
  parts = adapter()
  warps = Warps(parts)
  geometry = warps.geometry()
  if not warps.built():
    cloudlog.warning("jetlink: no warp for %s, the phone stays unused", geometry)
    return
  warp = Warp(warps.load(*geometry), parts.model_face().frame_size(*geometry[2:]))

  main_stream = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_ROAD, True)
  extra_stream = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_WIDE_ROAD, False)
  for client in (main_stream, extra_stream):
    if not client.connect(True):
      cloudlog.warning("jetlink: camerad not up, the phone stays unused")
      return

  link = open_client(cloudlog)
  prepare_engine(link, params.get(SPEC_PARAM), cloudlog)
  epoch = 0
  served = 0
  last_note = 0.0
  while True:
    frame = box.frame()
    if frame is None:
      _time.sleep(0.002)
      continue
    try:
      main_buf = main_stream.recv()
      extra_buf = extra_stream.recv()
      warp.start(address(main_buf.data), address(extra_buf.data), frame.img, frame.big_img)
      warp.wait()
      packed = np.concatenate([frame.desire, frame.traffic_convention, frame.action_t]).astype(np.float32)
      raw = link.infer(warp.output, packed, frame.frame, deadline=FRAME_TIMEOUT)
      if raw.shape[0] < HEAD_COUNT:
        raise ValueError(f"the phone returned {raw.shape[0]} floats, the host reads {HEAD_COUNT}")
      if box.reply(frame.session, epoch, frame.frame, frame.eof, raw[:HEAD_COUNT]):
        served += 1
      now = _time.monotonic()
      if now - last_note >= 5.0:
        last_note = now
        params.put(STATUS_PARAM, f"served {served} frames", block=False)
    except Exception as error:
      epoch += 1
      cloudlog.warning("jetlink: phone frame failed (%s); the local model drives", error)
      time.sleep(0.5)


if __name__ == "__main__":
  main()
