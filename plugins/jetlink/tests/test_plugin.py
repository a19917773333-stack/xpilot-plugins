"""Manifest, claims and process gating: what the host needs to run this plugin at all."""
import json
from pathlib import Path

import pytest

from .. import plugin as manifest

ROOT = Path(__file__).resolve().parents[1]


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


def test_processes_are_one_python_process_each():
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