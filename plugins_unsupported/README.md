# Unsupported plugin source

This directory keeps source snapshots that cannot be installed or run on the
current xpilot host. It now contains only sources that still require unavailable
host contracts.

`cp_nav` 0.2.5, `navassist` 2.4.6 and `tesnav` 0.1.2 were adapted to the current
API 1 / runtime-rule ABI 1 host and moved to `plugins/`. Their packages are
published through `dist/` and `index.json` like other store plugins.

Imported from `sniper-eon/xpilot-plugins@1ae409345549cb7d28fcae53d8ae2a6c652fcbba`.

- `zh_cn`: requires the `ui_translation` host hook, which is not present.

Do not copy it into `plugins/` or add it to `index.json` until the target host
provides the required contract and the package has been rebuilt and validated.
