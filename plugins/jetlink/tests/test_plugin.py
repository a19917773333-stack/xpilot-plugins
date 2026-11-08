"""Manifest, claims and process gating: what the host needs to run this plugin at all."""
import json
from pathlib import Path
import sys
import types

import pytest

from .. import plugin as manifest

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


def test_available_uses_persistent_runtime_without_checkout_link(monkeypatch, tmp_path):
  """A reboot removing /data/openpilot/jetlink must not hide the saved runtime package."""
  runtime = tmp_path / "runtime"
  package = runtime / "jetlink"
  package.mkdir(parents=True)
  (package / "__init__.py").write_text("")
  monkeypatch.setattr(manifest, "JETLINK_RUNTIME_DIR", runtime)
  monkeypatch.setattr(sys, "path", [path for path in sys.path if path != str(runtime)])

  class NoCheckoutLink:
    def find_spec(self, name, path=None, target=None):
      if name == "jetlink" and str(runtime) not in sys.path:
        raise ModuleNotFoundError("checkout link is gone", name=name)
      return None

  monkeypatch.setattr(sys, "meta_path", [NoCheckoutLink(), *sys.meta_path])
  assert manifest.available()
  assert sys.path[0] == str(runtime)


def test_link_owner_stays_up_offroad_but_inference_processes_do_not(monkeypatch):
  """The USB owner provisions while parked; modeld and the peer wait for a drive."""
  monkeypatch.setattr(manifest, "available", lambda: True)
  fake_python_process(monkeypatch)

  class Params:
    def get(self, _key):
      return 1

  processes = {proc.name: proc for proc in manifest.Jetlink.processes()}
  params = Params()
  assert processes["jetlinkd"].should_run(False, params, None)
  assert not processes["jetlink_modeld"].should_run(False, params, None)
  assert not processes["jetlink_peer"].should_run(False, params, None)
  assert all(proc.should_run(True, params, None) for proc in processes.values())
