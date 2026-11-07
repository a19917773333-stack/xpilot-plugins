# tn_long: TN longitudinal (TN-NoDEC)

Replaces SP's longitudinal plan, including lead following, with the TN-NoDEC planner: the legacy cruise-obstacle MPC
plus the TN acceleration controller (pace, lead plan, accel personality). Ported from xpilot dev-sp
(`openpilot/tesla/long/{legacy_mpc,tn_no_dec,tuning.py,registry.py}` at c1b8a76873^) with relative imports and
`Ext*` params.

- Hook: `long_planner` (`role:long.planner`). The host clips aTarget to ACCEL_MIN/MAX, keeps SP's MPC for FCW and
  falls back to SP's plan on bad output; brake disengage, stock AEB and panda limits are unchanged.
- Not included: TN's controlsd stopping policy (`longcontrol_policy.py`): there is no plugin hook for longitudinal
  control yet, so stops use SP's LongControl.
- Settings: Accel Personality on/off and profile (Eco/Normal/Sport). `ExtTnLongTuning` holds the runtime tuning
  config (absent: TN defaults); there is no tuning UI yet.

## Prebuilt binaries

The acados solvers are compiled code, so this plugin ships binaries for one platform. To build them, on the device
running the target openpilot version:

    cd /data/openpilot && PYTHONPATH=/data/openpilot python3 <checkout>/plugins/tn_long/build_native.py
    cd <checkout> && python3 tools/build_index.py

`build_native.py` writes `legacy_mpc/c_generated_code*/*.so` and stamps `plugin.json` with the platform
(`machine`, Python ABI). Devices only offer and load it on a matching platform. Rebuild after openpilot changes its
Python, numpy or acados versions. Until it is built, `build_index.py` leaves it out of `index.json`.

The reviewed C3-built solver libraries are committed in `legacy_mpc/c_generated_code*` so a clean checkout can
reproduce the release archive. A device rebuild replaces those files in place.

Status: host import check only. The solver build and the planner have not run on a device in this form.
