# Traefik 3.7.16 qualification

Reviewed patch origin is the v0.2.5 integration's Traefik 3.7.14. Coolify stays 4.5.0 and Sentinel 1.1.2; their [existing qualification](2026-10-24-coolify-450-runtime.md) is unchanged. Controlled existing-host proxy qualification passed at V3 using candidate `4aa1780` on the disposable Ubuntu 24.04 VPS.

Official Docker index: sha256:c8a121e4bb1347e8fd52657fab12f2cb70b68f8a018895e2068f92c9e519b9c2. Linux amd64 manifest: sha256:abb2b9c1b132b5b0be40d09c85bf8d3dab2a59fa0eb3aa955ab8be5efbb73de6. Classic Docker config identity: sha256:3733df53e74cd0df7d1b839168e30d2bd7f5e77dd6214ef3d8056ee1f21392b7. Registry metadata and an evaluation-host pull were inspected independently of the mutable tag before pinning.

## Compatibility review

Reviewed official 3.7.15/3.7.16 release notes, security advisories and the versioned migration guide. CONNECT requests are now rejected with 501 before routing, including HTTP/2; they are not recorded in access logs. The Kubernetes Gateway API and Kubernetes secret-reference changes do not apply to this Docker-provider topology. No Kubernetes, forward-proxy or authentication capability is newly qualified here.

Only the preceding v0.2.5 integration's exact 3.7.14 index/config identities are accepted as origins. Older integrations/images must first reach that baseline; source and image versions alone do not establish content identity. The reviewed 3.7.16 target is pinned by official digest and supports inspection under both Docker image-store identity formats.

## Controlled runtime

- Fresh encrypted off-host Coolify/proxy recovery inputs passed authenticated decryption and manifest checks before maintenance. Test firmware/reboot completed and full verify/audit passed before proxy mutation.
- Staged native preflight: ok=24 changed=1 failed=0. This stages private helpers; it is not a zero-write probe.
- Evaluation stopped after native Save with a protected checkpoint/pending transaction: ok=22 changed=0 failed=1 (expected). The failed command's changed counter does not imply that no state was written.
- Same-source forward resume passed, then explicit digest-pinned rollback, re-upgrade and no-op. Each resume/rollback/re-upgrade reported ok=24 changed=1 failed=0; no-op ok=24 changed=0 failed=0. HTTPS health passed after each completed stage.
- Full verify: ok=163 changed=0 failed=0. Audit: ok=96 changed=0 failed=0.
- All four non-proxy containers retained IDs, images, networks and mounts; stored ENV and source credential bytes matched the on-server baseline. Proxy/logrotate recreation was scoped to their own stack.
- Native YAML comparison confirmed only the proxy image field changed. The ACME storage file remained byte-identical to the checkpoint. TLS WebSocket returned 101; explicit HTTP/1.1 and HTTP/2 CONNECT probes returned 501.
- Native Coolify 4.5 startup created its internal error-pages helper. It belongs to the proxy stack, publishes no host port and mounts only the error-pages directory read-only. This was not a business-resource deployment.
- The complete final checkpoint includes native YAML, proxy archive and previous-image archive, all checked against transaction hashes. It was encrypted on the VPS with the public recipient, transferred encrypted only and authenticated/manifest-verified off-host without writing a plaintext recovery archive. Prior image/checkpoints were retained.

No production interruption/rollback was performed as part of this controlled exercise. This is V3 existing-host Linux amd64 evidence, not a clean-install V4 or full VPS recovery claim. Rollback preserves current mounted certificate data; it does not restore that archive or arbitrary concurrent configuration changes.
