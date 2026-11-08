"""jetlink_peer: the phone on the other end of the mailbox.

modeld publishes one frame per camera frame; this process warps that camera frame on the comma's GPU, sends it
over the link jetlinkd holds, and writes the phone's raw output back. Nothing here is on the car's critical path:
no published frame, no link or no reply in time is a local frame.

While parked, the same process also keeps the protocol session open: it says hello, asks the phone to keep its
already-built engine ready, and keeps the USB lease idle. That is what turns Android's USB "attached"
state into Jetlink's "connected" state without starting cameras or inference early.
"""
import time

import numpy as np

from .mailbox import HEAD_COUNT, Mailbox

MAILBOX_PARAM = "XpilotJetlinkMailbox"
SPEC_PARAM = "XpilotJetlinkSpec"
STATUS_PARAM = "XpilotJetlinkStatus"
CONNECT_TIMEOUT = 30.0
HELLO_TIMEOUT = 10.0
MAILBOX_POLL = 0.2
FRAME_TIMEOUT = 0.05
ENGINE_RETRY = 10.0
WARMUP_TIMEOUT = 120.0


def address(buf) -> int:
  """The address of a camera buffer's pixels, as the warp reads them."""
  addr = getattr(buf, "addr", None)
  return int(addr) if addr is not None else int(np.frombuffer(buf, dtype=np.uint8).ctypes.data)


def mailbox(params):
  """The modeld mailbox, if a drive has published one."""
  import os
  from pathlib import Path
  path = params.get(MAILBOX_PARAM)
  if not path or not Path(path).exists():
    return None
  try:
    return Mailbox(os.fspath(path))
  except OSError:
    # modeld may retire the file between exists() and open().
    return None


def wait_for_mailbox(params, *, timeout: float | None = None,
                     poll_interval: float = MAILBOX_POLL, client=None):
  """Hold the open USB lease until modeld starts publishing frames."""
  import time as _time
  deadline = None if timeout is None else _time.monotonic() + timeout
  while True:
    if client is not None and client.dead:
      raise ConnectionError("the phone disconnected while waiting for modeld")
    box = mailbox(params)
    if box is not None:
      return box
    if deadline is not None and _time.monotonic() >= deadline:
      return None
    _time.sleep(poll_interval)


def open_client(log):
  """Open the link jetlinkd lends and keep both the lease and the client."""
  from jetlink.openpilot.link import Link
  link = Link(log, name="xpilot_peer")
  client = link.open(deadline=time.monotonic() + CONNECT_TIMEOUT)
  return link, client


def models_for(op):
  from jetlink.openpilot.models import Models
  return Models(op)


def introduce(link, client, log, op) -> dict:
  """Start the session with our pick and pass the phone's answer to the owner."""
  models = models_for(op)
  asked = models.hello_pick()
  hello = models.heard(client.hello(timeout=HELLO_TIMEOUT, pick=asked), asked)
  link.note_server(hello)
  models.adopt()
  log.warning("jetlink: phone %s connected (engine %s)",
              hello.get("device") or "peer", hello.get("engine_state") or "unknown")
  return hello


def infer_frame(client, warped, packed, frame_id, *, warmed):
  """Use a bounded warmup for the first reply, then the mailbox's frame deadline.

  Loading an engine can take tens of seconds. Abandoning that first reply at the
  mailbox's 50 ms deadline closes the USB lease and makes the host re-enumerate,
  which can turn a working USB 3 session into USB 2. Once the phone has answered,
  keep every later frame behind the same short deadline used by the local model.
  """
  if not warmed:
    return client.infer(warped, packed, frame_id, deadline=WARMUP_TIMEOUT)
  # Reap replies that arrived after the previous frame's hold. The send must
  # never wait on a busy USB queue: try_send can skip this frame without
  # treating the host as dead, while a short blocking send deadline can make
  # FunctionFS abort the whole transport and force a re-enumeration.
  client.drain()
  seq = client.infer_begin(warped, packed, frame_id, skip_if_busy=True)
  if seq is None:
    return None
  return client.infer_end(seq, hold=FRAME_TIMEOUT)


def prepare_engine(client, value, log):
  """Load the model named by the ready spec; the phone may already hold its engine.

  False is a malformed spec, while None means the phone does not have the
  named engine and the ready record is stale. The caller then releases the
  loan so jetlinkd can provision it.
  """
  import json
  try:
    spec = json.loads(value) if isinstance(value, str) else (value or {})
    sha256, nbytes = spec.get("sha256"), spec.get("nbytes")
    if spec.get("ready") is not True or not sha256 or not nbytes:
      raise ValueError("the spec is not a ready model with sha256/nbytes")
    # A ready spec does not carry a comma-local ONNX path. Pass None so the phone
    # reuses its built engine instead of the peer skipping preparation entirely.
    client.ensure_engine(str(sha256), int(nbytes), spec.get("onnx_path"))
    return True
  except Exception as error:
    log.warning("jetlink: could not prepare the phone's engine: %s", error)
    return None if type(error).__name__ == "EngineMissing" else False


def clear_ready(params) -> None:
  """Mark a stale ready spec false so the owner can provision before the peer retries."""
  value = params.get(SPEC_PARAM)
  if isinstance(value, dict) and value.get("ready"):
    params.put(SPEC_PARAM, {**value, "ready": False}, block=False)


def frame_geometry(main_stream, extra_stream, configured):
  """Use the live camera size; the adapter supplies only the model input size."""
  dimensions = (main_stream.width, main_stream.height, extra_stream.width, extra_stream.height)
  if any(value is None for value in dimensions):
    raise RuntimeError("camerad did not publish frame dimensions")
  cam_w, cam_h, extra_w, extra_h = (int(value) for value in dimensions)
  if (cam_w, cam_h) != (extra_w, extra_h):
    raise RuntimeError(f"road streams disagree: {cam_w}x{cam_h} and {extra_w}x{extra_h}")
  model_w, model_h = configured[2:]
  return cam_w, cam_h, int(model_w), int(model_h)


def camera_frame_size(model_face, geometry):
  """The warp copies camera NV12 bytes, never the smaller model input."""
  return model_face.frame_size(geometry[0], geometry[1])


def main() -> None:
  import time as _time

  from openpilot.common.params import Params
  from openpilot.tesla.plugin_params import ParamsView
  from openpilot.common.swaglog import cloudlog
  from msgq.visionipc import VisionIpcClient
  from openpilot.cereal.visionipc import VisionStreamType

  from .seam import adapter

  params = ParamsView(Params())
  parts = adapter()
  link = None
  try:
    link, client = open_client(cloudlog)
    introduce(link, client, cloudlog, parts)
    params.put(STATUS_PARAM, "phone connected", block=False)

    prepared = prepare_engine(client, params.get(SPEC_PARAM), cloudlog)
    if prepared is None:
      clear_ready(params)
    if not prepared:
      params.put(STATUS_PARAM, "waiting for phone engine", block=False)
      _time.sleep(ENGINE_RETRY)
      return
    params.put(STATUS_PARAM, "phone engine ready", block=False)

    # Offroad this holds the USB lease idle. Onroad modeld publishes the mailbox and
    # the same session starts carrying frames.
    box = wait_for_mailbox(params, client=client)

    from jetlink.openpilot.warp import Warp, Warps
    warps = Warps(parts)

    # the stream enum moved out of msgq and ROAD was renamed NARROW_ROAD on newer trees
    road_stream = getattr(VisionStreamType, "VISION_STREAM_ROAD", None)
    if road_stream is None:
      road_stream = VisionStreamType.VISION_STREAM_NARROW_ROAD
    main_stream = VisionIpcClient("camerad", road_stream, True)
    extra_stream = VisionIpcClient("camerad", VisionStreamType.VISION_STREAM_WIDE_ROAD, False)
    for stream in (main_stream, extra_stream):
      if not stream.connect(True):
        cloudlog.warning("jetlink: camerad not up, the phone stays unused")
        return

    try:
      geometry = frame_geometry(main_stream, extra_stream, warps.geometry())
      if not warps.is_cached(*geometry):
        params.put(STATUS_PARAM, "no local warp", block=False)
        cloudlog.warning("jetlink: no warp for %s, the phone stays unused", geometry)
        return
      warp = Warp(warps.load(*geometry), camera_frame_size(parts.model_face(), geometry))
    except Exception:
      params.put(STATUS_PARAM, "warp setup failed", block=False)
      raise

    epoch = 0
    served = 0
    last_note = 0.0
    warmed = False
    while True:
      if not box.alive:
        cloudlog.warning("jetlink: modeld retired the mailbox; reconnecting the phone")
        return
      frame = box.frame()
      if frame is None:
        _time.sleep(0.002)
        continue
      if not warmed:
        params.put(STATUS_PARAM, "warming phone model", block=False)
      try:
        main_buf = main_stream.recv()
        extra_buf = extra_stream.recv()
        if main_buf is None or extra_buf is None:
          cloudlog.warning("jetlink: camerad stopped; reconnecting the phone")
          return
        warp.start(address(main_buf.data), address(extra_buf.data), frame.img, frame.big_img)
        warp.wait()
        packed = np.concatenate([frame.desire, frame.traffic_convention, frame.action_t]).astype(np.float32)
        raw = infer_frame(client, warp.output, packed, frame.frame, warmed=warmed)
        if raw is None:
          epoch += 1
          continue
        if raw.shape[0] < HEAD_COUNT:
          raise ValueError(f"the phone returned {raw.shape[0]} floats, the host reads {HEAD_COUNT}")
        if not warmed:
          warmed = True
          cloudlog.warning("jetlink: phone model warmed up; normal frame deadline is %.0f ms", FRAME_TIMEOUT * 1000)
        if box.reply(frame.session, epoch, frame.frame, frame.eof, raw[:HEAD_COUNT]):
          served += 1
        now = _time.monotonic()
        if now - last_note >= 5.0:
          last_note = now
          params.put(STATUS_PARAM, f"served {served} frames", block=False)
        if client.dead:
          raise RuntimeError("the phone link stopped answering")
      except Exception as error:
        epoch += 1
        cloudlog.warning("jetlink: phone frame failed (%s); the local model drives", error)
        if client.dead:
          return
        _time.sleep(0.5)
  finally:
    if link is not None:
      link.close()


if __name__ == "__main__":
  main()
