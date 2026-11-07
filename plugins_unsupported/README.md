# Unsupported plugin source

This directory keeps source snapshots that cannot be installed or run on the
current xpilot host. They are intentionally outside `plugins/`, so the store,
plugin tests, and runtime-rule checks do not publish or load them.

Imported from `sniper-eon/xpilot-plugins@1ae409345549cb7d28fcae53d8ae2a6c652fcbba`.

- `cp_nav`: requires `template_clone.v2` and rule ABI 2; the current host supports rule ABI 1.
- `navassist`: requires rule ABI 2, `buzzer_policy`, and the matching host lane policy module.
- `tesnav`: requires the `navigation_ingress` host hook, which is not present.
- `zh_cn`: requires the `ui_translation` host hook, which is not present.

Do not copy these into `plugins/` or add them to `index.json` until the target
host provides the required contracts and the packages have been rebuilt and
validated against that host.
