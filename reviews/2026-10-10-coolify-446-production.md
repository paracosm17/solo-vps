# Coolify 4.4.6 bounded production upgrade — V5

On 2026-10-10 the owner-authorized maintained Ubuntu 24.04 VPS completed Coolify 4.4.3 → 4.4.6 with operational source `ef4139b`. Traefik 3.7.14 and Sentinel 1.0.2 were retained. A disposable-host interruption/resume, isolated restore and exact upstream migration-fixture qualification preceded production.

## Recovery inputs

A fresh control-plane dump/archive was validated before mutation, accompanied by native proxy/operator configuration and a private container/environment baseline. The encrypted off-host copy was decrypted as a stream and its SHA256 matched the server archive (`0039f36e58cca7322ca4a837356e63b0c709a0cd55957f27ad461a255660c97d`). The automatic upgrade checkpoint's manifest hashes also passed; its encrypted off-host bundle matched `367c6b55faee0bc650954400a5e290a1ae028f230e34d5b2d6940a1cc66ded56`. Previous source and existing application-data backups were retained.

## Result

- No active deployments or affected IPv6/duplicate-variable groups before mutation. Baseline preservation was rechecked immediately before the transition.
- Preflight `ok=41 changed=0 failed=0`; upgrade `ok=138 changed=9 failed=0`.
- Full verification `ok=163 changed=0 failed=0`; audit `ok=96 changed=0 failed=0`.
- All 14 business containers and native proxy/logrotate retained IDs, image IDs, mounts and start times. Built-in server and destinations stayed unchanged.
- Every native environment-variable row matched its baseline hash. Six credential fields and two actual SSH key files stayed unchanged; no deleted duplicate rows were expected or observed.
- Six origin HTTPS `/healthz` routes returned 200. Embedded Reverb TLS WebSocket returned 101; native SSH succeeded; Sentinel was `in_sync`. After the collector interval, all six generated requests appeared as 2xx and no 5xx.
- Normalized fresh Coolify/proxy/Sentinel logs had zero ERROR/FATAL/CRITICAL and zero bind conflicts.

Normal upgrade rerun passed with `ok=87 changed=0 failed=0`. Published v0.2.3 resolves to `7373ae6487fac3370f3f38fcd1111aa9280f56de`; both installed checkouts match the annotated tag. Exact-commit `verify-coolify` passed on both with `ok=56 changed=0 failed=0`. Exact-main CI/Pages, pinned-QA release dry-run and independent history scanning passed. No OS/Docker update, reboot, application deploy or proxy replacement was performed. These results are bounded production evidence, not a reliability guarantee or fresh V4 install. Forward-only data migrations cannot be reversed by a source/image downgrade; control-plane recovery inputs exclude application data.
