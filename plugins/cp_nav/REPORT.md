# CP independent candidate validation — 2026-10-28

## Source and compatibility

- Host source: Sniper-Eon/xpilot branch xpilot at
  `964aebf31a2714c0c68790c7f6dbce6977ac0e9c` (exact safety-provider reference seam).
- Plugin source: Sniper-Eon/xpilot-plugins main, committed with this report;
  initial native foundation `7b50eda2c069cf8ed32d9cfc6230b9ed159d4ed9`.
- Upstream developer docs/API checked against remote branch tips:
  onemiless/xpilot:xpilot `680dd2bfef1e5da79da92b69febb18a50d1a5bae`;
  onemiless/xpilot-plugins:main `ef98bc1f1c0bc9db7c6f6e3f6b56ff02ef1fa1bb`.
  That upstream runtime-rule ABI is not present in the older paired host/device.
  This candidate targets the user's existing exact firmware policy; it does not
  silently replace firmware or claim compatibility with the new upstream ABI.
- Native Carrot kernel `jixiexiaoge/carrot@3615bf4`; original CP Android wire
  client `jixiexiaoge/navipilot@91d77de` latest-snapshot, source unchanged.
- No current device version was queried. Previous device state/commits are
  historical evidence, not confirmation of this candidate's device activation.

## Failure contracts

Checks preceded their fixes and failed on the preceding behavior: absent own
entry/master; wrong source owner after switching; old shared CP selector;
out-of-range settings; stale owned lamp falling through to auto; turn-only
crossing; late disable; renewed observation age; invalid distance/heading;
unbound/moving HTTP writes; stale cached P state; native mode label mismatch;
missing planner targets; replayed passing completion; OEM veto release flicker;
source dropout rearming an increase. Synthetic inputs only, no driving captures.

## Local validation

Commands use the existing Python 3.12 project test environment and paired host
on PYTHONPATH; no new runtime dependency is introduced.

- `pytest -q -p no:cacheprovider plugins`: 750 passed, exit 0 on final source.
- Scoped CP/TN checks: 45 passed, exit 0.
- `tools/cp_candidate_check.py`: real archive installation, discovery, actual
  parked-UI switch both directions and master disable; 3 switches passed.
  Only isolated files are written; no running manager/vehicle is activated.
- Host `tools/sp_tesla_e2e/store_e2e.py --repo .`: installed 24 matching-platform
  plugins including cp_nav and navassist, errors empty. TN aarch64 archive is
  correctly excluded on Mac; this is not a TN native solver execution/build.
- `tools/prepare_profile.py` for cpdazi and tesnav: both staged successfully to
  new temporary directories, activated=false, road_validated=false. TN deferred
  by platform. Both profiles retain Chinese and keep actuation in observation.
- `tools/cp_upstream_probe/run.py --independent`: original Kotlin client sends
  right/sharp/exit/model cases through the standalone receiver and native Carrot;
  original compact decoder reads actual BSM/gear/speed fields. Five cases pass.
  Legacy probe also passes its five cases. Only Android logging is shimmed;
  full APK build=false, MNN executed=false, device deployed=false.
- Classifier, independent master contracts, 138 translated metadata fields,
  companion map-view regression, profile contract and reproducible archive/index
  verification pass. Host's existing 15 validation gates were passed for the
  preceding generic safety-reference commit; no host code changed in this step.

## Artifact versions

cp_nav 0.1.0; navassist 1.5.8 (TesNav-only process selection); TN 1.0.1
(host target collection); zh_cn 1.1.8. Archive digests are in index.json and are
verified by tools/build_index.py --check. These are local candidates, not pushed
or activated releases. The host dependency must be published before plugins.

## Limits and remaining work

- Automatic passing/return source is retained, but production SP lacks qualified
  CP side-lead/pass-complete/return-efficiency data. It advertises unavailable and
  cannot request passing merely because BSM is not triggered. Source fixtures
  covering passing decisions do not establish actual passing capability.
- Native CP UDP SPEED/LANECHANGE control commands, full Carrot traffic-light /
  longitudinal planner, curve inputs, voice countdown and global CP controls are
  outside this candidate. Unsupported parameter writes are rejected.
- No C3 image streaming, full phone APK rebuild, phone model inference, firmware
  compilation/flash, device deployment/activation or road test was performed.
- Real parked C3/phone interoperation and driving validation remain separate
  steps; user requested no deployment for this task.

## 0.1.1 onroad receiver repair (2026-10-28)

Historical device evidence at 17:08:35 records cp_navd dying with
MultiplePublishersError on pluginMsg after card begins OEM publication. At
17:08:39 selfdrived reports process_not_running for cp_navd. The user switched
back to TesNav after the failure; its later master switch state is a consequence,
not the root cause. The phone's reported inability to connect is consistent with
this C3 receiver failure; actual phone handshake remains unverified.

Paired host minimum fc9afa643497a334f7d69df637042bcaca03777b selectively backports
the upstream broker, source authentication, bounded transport and manager restart.
CP 0.1.1 and navassist 1.5.9 no longer construct their own pluginMsg publishers.
An import gate rejects hosts without the broker. No safety or mandatory process
check is removed, and no firmware/schema migration is included.

The new CP card regression failed on the old publisher construction before the
repair, and passes after it. Local full plugin suite: 751 passed before merging
the concurrent upstream-in-user-fork chime commit. Retained that commit and the
host's concurrent soundd changes; updated three existing chime fixtures to test
actual laneChangeStarting with cereal enum values and a modelV2 input, retaining
the producer/host/GPIO dispatch coverage. The scoped eight sound checks pass.
Host and plugin metadata/archive/profile gates passed; both profiles require the
broker host and remain unactivated. Device files/settings are untouched by this
repair so far. Real parked phone connection and vehicle-start validation remain
pending. Private raw logs are outside the repositories.
