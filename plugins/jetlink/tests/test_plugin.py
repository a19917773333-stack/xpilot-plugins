"""Manifest, claims, process gating and readiness: what the host needs to run this plugin."""
import importlib
import json
from pathlib import Path
import sys
import types

from .. import plugin as manifest
from .. import ready as readiness

ROOT = Path(__file__).resolve().parents[1]


def fake_python_process(monkeypatch):
  """Keep process-list tests independent of the compiled msgq module."""
  from types import SimpleNamespace

  module = types.ModuleType("openpilot.system.manager.process")
  module.PythonProcess = lambda name, path, should_run: SimpleNamespace(name=name, module=path, should_run=should_run)
  monkeypatch.setitem(sys.modules, "openpilot.system.manager.process", module)


def spec() -> dict:
  return json.loads((ROOT / "plugin.json").read_text())


def test_manifest_declares_the_role_and_every_process_it_runs():
  manifest_json = spec()
  assert manifest_json["id"] == ROOT.name and manifest_json["api"] == 1
  assert {"role:perception.model"} <= set(manifest_json["claims"])
  assert {f"process:{name}" for name, _ in manifest.PROCESSES} <= set(manifest_json["claims"])
  assert manifest_json["entry"] == "plugin:Jetlink"


def test_every_param_the_code_writes_is_declared():
  params = set(spec()["params"])
  declared = {value for value in vars(manifest).values() if isinstance(value, str) and value.startswith("XpilotJetlink")}
  assert declared
  assert declared <= params, declared - params


def test_object_params_round_trip_as_json():
  """Pointers, progress and the spec are dicts; STRING storage silently turns them into unusable text."""
  params = spec()["params"]
  assert {key: params[key]["type"] for key in ("XpilotJetlinkPointers", "XpilotJetlinkProgress", "XpilotJetlinkSpec")} == {
    "XpilotJetlinkPointers": "JSON", "XpilotJetlinkProgress": "JSON", "XpilotJetlinkSpec": "JSON",
  }


def test_processes_are_one_python_process_each(monkeypatch):
  fake_python_process(monkeypatch)
  processes = manifest.Jetlink.processes()
  assert [process.name for process in processes] == [name for name, _ in manifest.PROCESSES]
  assert all(process.module.startswith("jetlink.") for process in processes)


def test_prepare_install_checks_the_device_warp(monkeypatch):
  """The store probe must reject a missing or unreadable local warp before activation."""
  from .. import seam

  packages = {}
  for name in ("jetlink", "jetlink.openpilot", "jetlink.openpilot.warp"):
    module = types.ModuleType(name)
    module.__path__ = []
    packages[name] = module
    monkeypatch.setitem(sys.modules, name, module)

  class Warps:
    cached = True
    error = None

    def __init__(self, parts):
      assert parts == "adapter"

    def geometry(self):
      return (1928, 1208, 512, 256)

    def is_cached(self, *geometry):
      assert geometry == (1928, 1208, 512, 256)
      return self.cached

    def load(self, *geometry):
      assert geometry == (1928, 1208, 512, 256)
      if self.error is not None:
        raise self.error
      return {}

  packages["jetlink.openpilot.warp"].Warps = Warps
  monkeypatch.setattr(manifest, "available", lambda: True)
  monkeypatch.setattr(seam, "adapter", lambda: "adapter")

  assert manifest.Jetlink.prepare_install() is True
  Warps.cached = False
  assert manifest.Jetlink.prepare_install() is False
  Warps.cached = True
  Warps.error = RuntimeError("wrong GPU")
  assert manifest.Jetlink.prepare_install() is False


def test_off_or_uninstalled_runs_nothing():
  class Params:
    def __init__(self, value):
      self.value = value

    def get(self, _key):
      return self.value

  assert manifest.mode(Params(0)) == "off"
  assert manifest.mode(Params(9)) == "off"
  assert manifest.mode(Params(None)) == "off"
  assert manifest.mode(Params(1)) == "usb"
  assert manifest.mode(Params(2)) == "ios"
  assert not manifest._onroad(False, Params(1), None)
  assert manifest._onroad(True, Params(0), None) is False


def test_available_requires_the_v090_runtime(monkeypatch, tmp_path):
  """A runtime of another version must not be used by an adapter written for v0.9.0."""
  runtime = tmp_path / "runtime"
  package = runtime / "jetlink"
  package.mkdir(parents=True)
  (package / "__init__.py").write_text('__version__ = "0.9.0"')
  monkeypatch.setattr(manifest, "JETLINK_RUNTIME_DIR", runtime)
  monkeypatch.setattr(sys, "path", [path for path in sys.path if path != str(runtime)])
  # pytest imports this plugin package as `jetlink`; drop that cached package
  # before the runtime check so the path under test can supply it.

  class NoCheckoutLink:
    def find_spec(self, name, path=None, target=None):
      if name == "jetlink" and str(runtime) not in sys.path:
        raise ModuleNotFoundError("checkout link is gone", name=name)
      return None
  monkeypatch.delitem(sys.modules, "jetlink", raising=False)
  monkeypatch.setattr(sys, "meta_path", [NoCheckoutLink(), *sys.meta_path])
  assert manifest.available()
  assert sys.path[0] == str(runtime)
  monkeypatch.setattr(importlib, "import_module", lambda name: types.SimpleNamespace(__version__="0.8.13"))
  assert manifest.available() is False


class Pointer:
  def __init__(self, oid, size):
    self.oid = oid
    self.size = size


class Index:
  def __init__(self, mapping, default=None):
    self.mapping = mapping
    self.default = default
    self.models = [types.SimpleNamespace(ref=ref) for ref in mapping]

  def pointer(self, ref):
    return self.mapping.get(ref)


def test_models_index_uses_the_host_model_manager_cache(monkeypatch, tmp_path):
  module = types.ModuleType("openpilot.common.hardware.hw")
  module.Paths = type("Paths", (), {"model_root": staticmethod(lambda: str(tmp_path))})
  monkeypatch.setitem(sys.modules, module.__name__, module)

  assert readiness._models_index_path() == tmp_path / "jetlink" / "index.json"


def ready_params(ref=None, pointer_oid="a" * 64):
  spec = {"ready": True, "sha256": "a" * 64, "nbytes": 123}
  pointers = {ref: {"oid": pointer_oid, "size": 123}} if ref and pointer_oid else {}
  return {"spec": spec, "active": {"ref": ref} if ref else {}, "pointers": pointers}


def test_peer_ready_uses_the_new_index_and_not_a_matching_legacy_pointer(monkeypatch):
  """Once v0.9.0 has an index, a missing ref cannot be admitted by old pointers."""
  params = ready_params(ref="a" * 40)
  index = Index({"b" * 40: Pointer("a" * 64, 123)}, default="b" * 40)
  monkeypatch.setattr(readiness, "_load_index", lambda: index)

  class Params:
    def get(self, key):
      key = {readiness.SPEC_PARAM: "spec", readiness.BIG_MODEL_PARAM: "active",
             readiness.POINTERS_PARAM: "pointers"}[key]
      return params[key]

  assert readiness.peer_ready(Params()) is False


def test_peer_ready_falls_back_to_pointer_only_before_the_index_exists(monkeypatch):
  params = ready_params(ref="a" * 40)
  monkeypatch.setattr(readiness, "_load_index", lambda: None)

  class Params:
    def get(self, key):
      key = {readiness.SPEC_PARAM: "spec", readiness.BIG_MODEL_PARAM: "active",
             readiness.POINTERS_PARAM: "pointers"}[key]
      return params[key]

  assert readiness.peer_ready(Params()) is True
  params["pointers"]["a" * 40]["oid"] = "b" * 64
  assert readiness.peer_ready(Params()) is False


def test_peer_ready_compares_the_default_model_when_no_ref_is_picked(monkeypatch):
  params = ready_params()
  index = Index({"c" * 40: Pointer("a" * 64, 123)}, default="c" * 40)
  monkeypatch.setattr(readiness, "_load_index", lambda: index)

  class Params:
    def get(self, key):
      key = {readiness.SPEC_PARAM: "spec", readiness.BIG_MODEL_PARAM: "active",
             readiness.POINTERS_PARAM: "pointers"}[key]
      return params[key]

  assert readiness.peer_ready(Params()) is True
  index.mapping["c" * 40] = Pointer("b" * 64, 123)
  assert readiness.peer_ready(Params()) is False


def test_peer_joins_offroad_only_when_a_model_is_ready(monkeypatch):
  """The parked peer completes the phone handshake, but not while it would block provisioning."""
  monkeypatch.setattr(manifest, "available", lambda: True)
  monkeypatch.setattr(readiness, "_load_index", lambda: None)
  fake_python_process(monkeypatch)

  class Params:
    def __init__(self, ready=True, ref="a" * 40, pointer_oid="a" * 64):
      self.ready = ready
      self.ref = ref
      self.pointer_oid = pointer_oid

    def get(self, key):
      if key == manifest.MODE_PARAM:
        return 1
      if key == readiness.SPEC_PARAM:
        return {"ready": self.ready, "sha256": "a" * 64, "nbytes": 123} if self.ready else {}
      if key == readiness.BIG_MODEL_PARAM:
        return {"ref": self.ref}
      if key == readiness.POINTERS_PARAM:
        return {self.ref: {"oid": self.pointer_oid, "size": 123}} if self.pointer_oid else {}
      return None

  processes = {proc.name: proc for proc in manifest.Jetlink.processes()}
  current = Params(ready=True)
  assert processes["jetlinkd"].should_run(False, current, None)
  assert not processes["jetlink_modeld"].should_run(False, current, None)
  assert processes["jetlink_peer"].should_run(False, current, None)

  not_ready = Params(ready=False)
  assert not processes["jetlink_peer"].should_run(False, not_ready, None)

  wrong_model = Params(ref="b" * 40, pointer_oid="b" * 64)
  assert not processes["jetlink_peer"].should_run(False, wrong_model, None)
  assert not processes["jetlink_peer"].should_run(True, wrong_model, None)

  unresolved = Params(pointer_oid=None)
  assert not processes["jetlink_peer"].should_run(False, unresolved, None)

  assert processes["jetlink_modeld"].should_run(True, not_ready, None)
  assert not processes["jetlink_peer"].should_run(True, not_ready, None)
