"""Source-compatible single-camera API; actual work is split into bounded modules."""
from .limits import MAX_AGE_NS
from .frames import FrameStore, read_observation
from .transport import BridgeServer, Handler
from .camera import camera_frames, camera_service_name, camera_stream_type, output_frame_size, capture
