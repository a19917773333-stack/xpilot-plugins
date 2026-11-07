from __future__ import annotations
import time,json,math,threading,secrets,hashlib,base64
from pathlib import Path
from .limits import MAX_AGE_NS

def camera_service_name(camera_name, available):
  names = ('wideRoadCameraState',) if camera_name == 'wide' else ('narrowRoadCameraState', 'roadCameraState')
  return next((name for name in names if name in available), None)


def camera_stream_type(camera_name, stream_types):
  names = ('VISION_STREAM_WIDE_ROAD',) if camera_name == 'wide' else ('VISION_STREAM_NARROW_ROAD', 'VISION_STREAM_ROAD')
  for name in names:
    if hasattr(stream_types, name):
      return getattr(stream_types, name)
  raise ValueError('unsupported_camera_stream')


def camera_frames(make_client, clock=time.monotonic, sleep=time.sleep, requested=None):
  """Recreate IPC mappings after camerad restarts or stops producing frames."""
  client = None
  last_frame = clock()
  while True:
    if requested is not None and not requested():
      last_frame = clock()
      sleep(.05)
      continue
    if client is None:
      client = make_client()
      if not client.connect(False):
        client = None
        sleep(.5)
        continue
      last_frame = clock()
    try:
      buf = client.recv(timeout_ms=100)
    except (RuntimeError, ConnectionError):
      client = None
      sleep(.5)
      continue
    if buf is None:
      if clock() - last_frame >= 2:
        client = None
      sleep(.02)
      continue
    last_frame = clock()
    yield client, buf


def output_frame_size(width, height, max_width=640):
  if type(width) is not int or type(height) is not int or width <= 0 or height <= 0:
    raise ValueError('invalid camera dimensions')
  if max_width not in (0, 320, 640, 960, 1280, 1928):
    raise ValueError('unsupported frame width')
  # No camera reconfiguration or upscaling; change only the transport image.
  scale = min(1., (max_width or 1928)/width, 1208/height)
  return max(1, round(width*scale)), max(1, round(height*scale))


def capture(store, roi_path, hz, max_width=640, jpeg_quality=75, camera_name='wide'):
  from .dependencies import load_opencv
  cv2 = load_opencv()
  import numpy as np
  from msgq.visionipc import VisionIpcClient
  from openpilot.cereal.visionipc import VisionStreamType
  from openpilot.cereal import messaging
  from openpilot.cereal.services import SERVICE_LIST
  from openpilot.common.transformations.camera import DEVICE_CAMERAS, get_view_frame_from_calib_frame, view_frame_from_device_frame
  from openpilot.common.transformations.orientation import rot_from_euler
  cv2.setNumThreads(1)
  roi = json.loads(Path(roi_path).read_text())
  camera_service = camera_service_name(camera_name, SERVICE_LIST)
  if camera_service is None:
    raise ValueError('camera_metadata_service_missing')
  stream = camera_stream_type(camera_name, VisionStreamType)
  sm = messaging.SubMaster(['deviceState', 'carState', 'extrinsicsCalibration', camera_service])
  make_client = lambda: VisionIpcClient('camerad', stream, conflate=True)
  previous_client = None
  last_encoded = float('-inf')
  try:
    device_id = hashlib.sha256(Path('/etc/machine-id').read_bytes().strip()).hexdigest()[:24]
  except OSError:
    device_id = None
  demand = store.frame_requested.is_set if camera_name == 'wide' else None
  for client, buf in camera_frames(make_client, requested=demand):
    if client is not previous_client:
      if camera_name == 'wide':
        store.new_stream()
      previous_client = client
    started = time.monotonic()
    capture_ns = int(client.timestamp_eof)
    if not 0 <= time.monotonic_ns()-capture_ns <= MAX_AGE_NS:
      continue
    if camera_name == 'wide':
      store.camera_seen(capture_ns)
    # Native IPC is conflated: drain cheaply, encode only when a phone asks.
    # Never accumulate a queue; hz is a hard maximum for JPEG work.
    if started-last_encoded < 1/hz:
      continue
    single_requested = camera_name == 'wide' and store.claim_capture(started, hz)
    if not single_requested:
      continue
    last_encoded = started
    sm.update(0)
    # Copy before the next recv: camera buffers belong to vision IPC.
    raw = np.frombuffer(buf.data, dtype=np.uint8)
    w, h, stride = int(buf.width), int(buf.height), int(buf.stride)
    y = raw[:stride*h].reshape(h, stride)[:, :w]
    uv = raw[int(buf.uv_offset):int(buf.uv_offset)+stride*(h//2)].reshape(h//2, stride)[:, :w]
    bgr = cv2.cvtColor(np.vstack((y, uv)), cv2.COLOR_YUV2BGR_NV12)
    width, height = output_frame_size(w, h, max_width)
    if (width, height) != (w, h):
      bgr = cv2.resize(bgr, (width, height), interpolation=cv2.INTER_AREA)
    inv, intrinsics, view_rotation, calibration_id, view_from_calib = None, None, None, None, None
    try:
      camera_fresh = all(sm.seen[s] and sm.alive[s] and sm.valid[s] for s in (camera_service, 'deviceState'))
      if not camera_fresh:
        raise ValueError('camera profile unavailable')
      configs = DEVICE_CAMERAS[(str(sm['deviceState'].deviceType), str(sm[camera_service].sensor))]
      camera = configs.wide_road if camera_name == 'wide' else configs.narrow_road
      if (w, h) != (camera.width, camera.height):
        raise ValueError('source camera geometry changed')
      k = camera.intrinsics.copy().astype(float)
      k[0] *= width/camera.width
      k[1] *= height/camera.height
      intrinsics = k.reshape(-1).tolist()
      # Intrinsic/profile identity is available during parked calibration even
      # when the onroad live ground-pose producer is intentionally not running.
      profile = [camera_name, str(sm['deviceState'].deviceType), str(sm[camera_service].sensor),
                 w, h, width, height, camera.focal_length]
      calibration_id = hashlib.sha256(json.dumps(profile).encode()).hexdigest()[:24]
      cal = sm['extrinsicsCalibration']
      fresh = all(sm.seen[s] and sm.alive[s] and sm.valid[s] for s in ('extrinsicsCalibration', camera_service, 'deviceState'))
      age = time.monotonic_ns()-sm.logMonoTime['extrinsicsCalibration']
      if fresh and 0 <= age <= 2_000_000_000 and str(cal.calStatus) == 'calibrated' and len(cal.height) and .5 <= cal.height[0] <= 3:
        view = get_view_frame_from_calib_frame(*cal.rpyCalib, float(cal.height[0]))
        rotation = (view_frame_from_device_frame @ rot_from_euler(cal.wideFromDeviceEuler) @ view_frame_from_device_frame.T
                    if camera_name == 'wide' else np.eye(3))
        projection = k @ rotation @ view
        inverse = np.linalg.inv(projection[:, [0, 1, 3]])
        if not np.isfinite(inverse).all():
          raise ValueError('invalid ground projection')
        inv = inverse.reshape(-1).tolist()
        intrinsics = k.reshape(-1).tolist()
        view_rotation = rotation.reshape(-1).tolist()
        view_from_calib = (rotation @ view).reshape(-1).tolist()
    except (KeyError, ValueError, np.linalg.LinAlgError):
      pass
    ok, jpg = cv2.imencode('.jpg', bgr, [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality])
    if ok:
      car_fresh = sm.seen['carState'] and sm.alive['carState'] and sm.valid['carState'] and 0 <= time.monotonic_ns()-sm.logMonoTime['carState'] <= 250_000_000
      speed = float(sm['carState'].vEgo) if car_fresh else None
      speed = speed if speed is not None and math.isfinite(speed) else None
      packet = dict(version=1, frame_id=int(client.frame_id), capture_mono_ns=capture_ns,
                         width=width, height=height, jpeg_b64=base64.b64encode(jpg).decode(),
                         ego_speed_mps=speed,
                         ground_inverse=inv, roi=roi, jpeg_bytes=len(jpg),
                         bridge_processing_ms=(time.monotonic()-started)*1000,
                         camera_id=camera_name, calibration_id=calibration_id, device_id=device_id,
                         camera_matrix=intrinsics, view_rotation=view_rotation,
                         view_from_calib=view_from_calib,
                         source_width=w, source_height=h)
      if single_requested:
        store.publish(packet)

