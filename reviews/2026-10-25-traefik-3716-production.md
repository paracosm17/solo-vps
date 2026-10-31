# Traefik 3.7.16 production patch — bounded V5

On 2026-10-25 the authorized maintained VPS completed the exact reviewed Traefik 3.7.14 to 3.7.16 transition using source `4859230`. This differs from tested `4aa1780` only in qualification metadata/evidence; the proxy policy fingerprint and execution code are identical. Coolify remained 4.5.0 and Sentinel 1.1.2. [Controlled qualification](2026-10-25-traefik-3716-runtime.md) and [firmware/reboot work](2026-10-25-host-maintenance.md) preceded production proxy mutation.

## Preconditions and result

- Fresh verified encrypted off-host control-plane/proxy inputs, healthy exact 3.7.14 origin, completed host verification/audit and no active deployment. No pending lifecycle transaction was cleared or bypassed.
- Staged proxy preflight ok=24 changed=1 failed=0. Normal upgrade ok=24 changed=1 failed=0. Normal rerun ok=24 changed=0 failed=0. Production was not deliberately interrupted or rolled back.
- Full verification ok=163 changed=0 failed=0; audit ok=96 changed=0 failed=0. Running target is the exact official 3.7.16 digest from the manifest; the native helper verified its binary version, image identity, network attachments and TCP-only 80/443 publications.
- Twenty pre-existing non-proxy containers retained IDs, images, mounts and networks. All 120 stored ENV values and source credential bytes matched the private on-server baseline. Proxy/logrotate were recreated as their own stack.
- Native YAML comparison found only the intended image change. ACME storage remained byte-identical to the checkpoint. No application was deployed. Native Coolify 4.5 startup added its internal error-pages helper: no host ports, not privileged, only the error-pages directory mounted read-only. It is a proxy helper, not a second compute node or a new application resource.
- All nine inspected origin HTTPS codes matched baseline: seven 200 (including Coolify), a pre-existing development-route 404 and a pre-existing development-route 503. Both production bots additionally returned healthy PostgreSQL/Redis checks.
- TLS WebSocket returned 101; HTTP/1.1 and HTTP/2 CONNECT probes returned 501. Sentinel was in_sync. Recent inspected proxy/Coolify logs contained no fatal, bind-conflict or Redis DNS failure patterns.
- The native Coolify package-discovery action refreshed APT indexes and reported total_updates=0, reboot_required=false. Its actual result/time were saved to the same cached settings fields used by the native job without enabling automatic patching, installing packages or sending notifications. Coolify automatic security updates remain off; Solo VPS retains host update ownership.

## Recovery inputs

The full retained proxy checkpoint includes native configuration, proxy archive and previous-image archive. Transaction member SHA256 values passed before encryption. It was encrypted on the VPS using only the workstation identity's public recipient, transferred as ciphertext and authenticated/decrypted/manifest-verified in a stream off-host. No plaintext recovery archive was written on the workstation; its private age identity stayed there and was never copied to the VPS. Private plaintext checkpoint files remain on the VPS by design. Prior source/images/checkpoints were retained; no retention/prune operation ran.

This is bounded existing-production V5 evidence, not fresh installation/V4, offline image-only recovery, full VPS reconstruction or arbitrary concurrent-configuration rollback. Control-plane exports and proxy checkpoints exclude application data; the supported native rollback still requires registry access and does not unpack certificate/configuration archives.
