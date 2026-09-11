---
name: insecure-defaults
description: >
  Catch insecure defaults — open permissions, debug in prod, weak crypto, trust-boundary gaps.
---

# Insecure defaults

## Hunt for

| Area | Bad default |
|------|-------------|
| Auth | Missing checks on new routes; `*` CORS in prod |
| Secrets | Keys in repo, logs, or client bundles |
| Files | World-writable paths; path traversal |
| DB | String concat SQL; overly broad grants |
| Config | `DEBUG=true`, `verify=False`, permissive CSP |
| Dependencies | Known CVEs in added packages |

## When adding features

- **Deny by default** — explicit allow lists
- **Least privilege** — scopes, roles, env separation
- **Fail closed** — errors reject, not bypass

## Report format

One line: **risk** → **where** → **fix**. No lecture.

---

*Adapted from [Trail of Bits skills](https://github.com/trailofbits/skills), licensed [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/). Condensed and rewritten for Hypercharge; this file is shared under the same licence.*
