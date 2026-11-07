"""Read-only CP API contract before implementation; no runtime write authority."""

import json
import threading
import urllib.error
import urllib.request
from navassist.cpstatus import StatusServer
from navassist.cpmeta import Metadata


def test_heartbeat_truthful_and_commands_rejected():
  s = StatusServer(("127.0.0.1", 0), Metadata())
  t = threading.Thread(target=s.serve_forever, daemon=True)
  t.start()
  base = "http://%s:%d" % s.server_address
  try:
    with urllib.request.urlopen(base + "/api/heartbeat_status") as r:
      d = json.load(r)
    assert d["ok"] and not d["hb"]["vehicle_fresh"]
    assert d["capabilities"]["automatic_overtaking"] is False
    assert d["capabilities"]["images"] is False
    req = urllib.request.Request(base + "/api/param_set", data=b'{"name":"Anything","value":"1"}')
    try:
      urllib.request.urlopen(req)
      assert False
    except urllib.error.HTTPError as e:
      assert e.code == 403
  finally:
    s.shutdown()
    s.server_close()
    t.join(2)
