# Coolify 4.4.3 maintained production patch — bounded V5

The owner authorized Coolify 4.4.2 → 4.4.3 after disposable qualification. Operational source `f133f48` shares the tested implementation; its additional changes promote qualification and update documentation. Ubuntu/Docker, Traefik 3.7.14 and business applications were outside mutation scope.

## Recovery and execution

Fresh database/source/SSH and proxy/configuration recovery inputs were created root-private. PostgreSQL archive listing passed. The bundle was encrypted on the workstation; streamed decryption SHA256 matched the original. A second encrypted Windows copy matched the encrypted checksum. The age private identity stayed off the VPS. Previous source and older business-data backups were retained.

The automatically generated upgrade checkpoint was also checksum-validated, exported encrypted off-host and verified through streamed decryption; an encrypted Windows copy was retained.

- Preflight: `ok=41 changed=0 failed=0`.
- Upgrade: `ok=138 changed=10 failed=0`, with a new automatic control-plane checkpoint.
- Full verification: `ok=163 changed=0 failed=0`.
- Security audit: `ok=96 changed=0 failed=0`.
- Upgrade rerun: `ok=87 changed=0 failed=0`.

## Result

All 14 business containers and the proxy retained IDs, image IDs, mounts and start times. Native proxy configuration, local-server UUID/address/user/private-key relation and destinations were unchanged. Six credential fields and both SSH key files matched the fresh backup/baseline.

Six origin HTTPS `/healthz` routes returned 200. Reverb TLS WebSocket handshake returned 101; native SSH backend succeeded; Sentinel was `in_sync`. Native analytics reported six successful requests and no 5xx for the inspected interval. Platform/proxy/Sentinel Docker logs for the post-upgrade ten-minute window contained no ERROR/FATAL/CRITICAL levels or bind conflicts. This does not reconstruct the earlier unsaved UI notification.

The default server display name was initialized without altering connection/resource identities. Existing custom names remain operator-owned. No production reboot, OS/Docker upgrade, proxy restart, application redeployment, pruning or application-data restore was performed.

## Limits

This is bounded production-use evidence, not a reliability guarantee, fresh-user replay or full application-data recovery test. Control-plane checkpoints exclude application data. Actual isolated checkpoint restoration was exercised on the test server, not by overwriting production. Final immutable source identity/publication checks are separate gates.

## Published source handoff

The annotated `v0.2.2` tag resolves to `37fc10aa57298eb7b6daa2c0f3ae9a8ea913e855`. Exact-main CI/Pages, release dry-run with pinned QA and independent history scan passed; GitHub Release is published. Both test and production controllers now use this exact tag. Their final full verification each completed `ok=163 changed=0 failed=0`.
