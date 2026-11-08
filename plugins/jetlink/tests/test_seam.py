"""The adapter against jetlink's own conformance check, so a member that drifts fails here and not on the road."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from .. import seam

HERE = Path(__file__).resolve().parents[2]  # the plugins directory pytest put on sys.path, which holds this package


def test_params_dir_exposes_plugin_and_host_values(monkeypatch, tmp_path):
  """Jetlink's file reader sees plugin settings and host state through one directory."""
  host = tmp_path / "host"
  plugin = tmp_path / "plugins"
  owner = tmp_path / "owner"
  host.mkdir()
  plugin.mkdir()
  (host / "IsOffroad").write_text("0")
  (plugin / "XpilotJetlinkMode").write_text("1")
  monkeypatch.setattr(seam, "OWNER_PARAMS_DIR", owner)
  monkeypatch.setattr(seam, "_host_params_dir", lambda: host)
  monkeypatch.setattr(seam, "_plugin_params_dir", lambda: plugin)

  try:
    assert seam.params_dir() == owner
  except OSError as error:
    pytest.skip(f"cannot create symlinks: {error}")
  assert (owner / "IsOffroad").read_text() == "0"
  assert (owner / "XpilotJetlinkMode").read_text() == "1"

  replacement = plugin / ".replacement"
  replacement.write_text("2")
  replacement.replace(plugin / "XpilotJetlinkMode")
  assert (owner / "XpilotJetlinkMode").read_text() == "2"


def test_owner_pythonpath_includes_persistent_runtime(monkeypatch, tmp_path):
  """Provisioning starts from BASEDIR but must still import the saved jetlink runtime."""
  runtime = tmp_path / "runtime"
  runtime.mkdir()
  basedir = tmp_path / "openpilot"
  monkeypatch.setattr(seam, "JETLINK_RUNTIME_DIR", runtime)
  existing = ["/existing/one", "/existing/two"]
  monkeypatch.setenv("PYTHONPATH", os.pathsep.join(existing))

  paths = seam.owner_pythonpath(basedir).split(os.pathsep)
  assert paths == [str(seam.BOOTSTRAP_DIR), str(basedir), str(runtime), *existing]


def test_worker_bootstrap_exposes_store_plugin_namespace(monkeypatch, tmp_path):
  """The provisioning interpreter can import an installed adapter through xpilot_ext."""
  monkeypatch.setattr(seam, "JETLINK_RUNTIME_DIR", tmp_path / "missing-runtime")
  monkeypatch.setenv("PYTHONPATH", "")
  env = {**os.environ, "PYTHONPATH": seam.owner_pythonpath(tmp_path / "openpilot")}

  result = subprocess.run([sys.executable, "-c", "import xpilot_ext.jetlink; print(xpilot_ext.jetlink.__file__)"],
                          capture_output=True, text=True, env=env)
  assert result.returncode == 0, result.stderr
  assert result.stdout.strip().endswith(str(Path("jetlink") / "__init__.py"))


def test_lfs_config_stays_out_of_the_host_checkout(monkeypatch, tmp_path):
  """Jetlink gets an isolated config whose first endpoint is the reachable mirror."""
  config = tmp_path / "lfs"
  monkeypatch.setattr(seam, "LFS_CONFIG_DIR", config)

  assert seam.lfs_config_dir() == config
  assert (config / ".lfsconfig").read_text() == f"[lfs]\n\turl = {seam.LFS_MIRROR}\n\tlocksverify = false\n"


def test_legacy_python_string_params_decode_to_objects():
  """1.0.8 stored dicts with str(), so upgrades must still use the saved pointer."""
  value = repr({"a" * 40: {"oid": "b" * 64, "size": 766354845}})
  assert seam.decode_param("XpilotJetlinkPointers", value) == {"a" * 40: {"oid": "b" * 64, "size": 766354845}}
  assert seam.decode_param("XpilotJetlinkStatus", "served 10 frames") == "served 10 frames"


def test_legacy_strings_are_migrated_before_json_reads(monkeypatch, tmp_path):
  pointer = {"a" * 40: {"oid": "b" * 64, "size": 766354845}}
  (tmp_path / "XpilotJetlinkPointers").write_text(str(pointer))
  (tmp_path / "XpilotJetlinkProgress").write_text(str({"stage": "failed", "frac": 1.0}))
  monkeypatch.setattr(seam, "_plugin_params_dir", lambda: tmp_path)

  seam.migrate_json_params()
  assert json.loads((tmp_path / "XpilotJetlinkPointers").read_text()) == pointer
  assert json.loads((tmp_path / "XpilotJetlinkProgress").read_text()) == {"stage": "failed", "frac": 1.0}


def real_jetlink_adapter():
  """jetlink's package and an Adapter built from it, or None.

  From plugins/ this package is imported as `jetlink`, so jetlink's own package only resolves once this one is off
  sys.path and out of sys.modules; the Adapter is built inside that window, because it imports jetlink when it is
  made. Everything is put back afterwards, so later tests still see this plugin.
  """
  saved_path = list(sys.path)
  saved_modules = {name: module for name, module in sys.modules.items() if name == "jetlink" or name.startswith("jetlink.")}
  sys.path[:] = [path for path in saved_path if Path(path or ".").resolve() != HERE]
  for name in saved_modules:
    sys.modules.pop(name)
  try:
    import jetlink.openpilot
    return sys.modules["jetlink.openpilot"], seam.Adapter()
  except ImportError:
    return None
  finally:
    sys.path[:] = saved_path
    for name in [name for name in sys.modules if name == "jetlink" or name.startswith("jetlink.")]:
      sys.modules.pop(name)
    sys.modules.update(saved_modules)


def test_adapter_conforms_to_jetlink_api():
  found = real_jetlink_adapter()
  if found is None:
    pytest.skip("jetlink (the phone package) is not installed here")
  interface, adapter = found
  assert interface.API == seam.API, "the adapter is written to another jetlink API"
  problems = interface.conformance(adapter, interface.Openpilot)
  assert problems == [], problems
