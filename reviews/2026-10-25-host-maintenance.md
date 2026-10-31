# Firmware and planned reboot — controlled V3 and bounded V5

On 2026-10-25 the owner authorized firmware maintenance, planned reboots and a separately qualified proxy update. The test VPS was handled first; production followed only after its test checks passed. This is operational evidence, not a new automatic host-upgrade feature.

## Before changes

Both hosts were healthy, with no active deployments or pending lifecycle transaction. Fresh encrypted off-host Coolify/proxy backups passed authenticated decryption/manifest verification. Administrator SSH, socket activation, Docker autostart, GRUB syntax, installed kernel/initramfs and sufficient disk space were checked. The owner had previously confirmed provider console/rescue access. Private baselines stayed on each VPS; no credentials or their hashes were exported.

The held linux-firmware update required eighteen newly split dependency packages. Simulated targeted installation showed one upgrade, eighteen additions and zero removals. Production had already received a broad package upgrade through Coolify, including Docker 29.9.2 and Compose 5.6.1; the earlier transient Redis DNS failure was consistent with that daemon restart and had cleared before this work.

## Operations and result

- On each host, installed only the reviewed firmware transaction with --no-remove, noninteractive existing-config preservation and needrestart list-only mode. No autoremove or unrelated full-upgrade. Previous kernels were retained.
- Package configuration and initramfs generation succeeded; GRUB syntax remained valid. Missing optional zstd on production caused the initramfs tool to use gzip, not a failed build.
- Pre-maintenance verify and audit passed on each: ok=163/96, changed=0, failed=0. After firmware, each host was deliberately rebooted once and SSH/platform health returned with a new boot ID.
- Test continued using installed kernel 6.8.0-147-generic. Production moved from running 6.8.0-35-generic to installed 6.8.0-147-generic.
- Across reboot, all six test and twenty-two production containers retained IDs, images, mounts and network attachments. Stored ENV/source credential bytes and HTTPS codes matched the private baseline. Source/identity comparison remained server-side.
- Post-reboot full verify and audit passed on both: ok=163/96, changed=0, failed=0. Production dpkg audit was clean, no failed system units were listed, no package updates remained in the inspected APT indexes, and reboot-required was absent.
- Existing Solo VPS unattended-upgrades policy and daily timers remain the security-update owner, with automatic reboot disabled. Coolify automatic host security updates remained off; no second update controller was enabled. No optional Solo VPS backup/monitoring services were present, so no additional optional-profile recovery claim is made.

Production HTTPS baseline included seven 200 routes (including Coolify), a pre-existing development-route 404 and a pre-existing development-route 503. They remained unchanged. The two production bots' own health endpoints confirmed PostgreSQL and Redis healthy.

The subsequent [Traefik qualification](2026-10-25-traefik-3716-runtime.md) and production proxy result are separate operations. This evidence is not a clean-install V4, full application-data restore or guarantee that every future kernel/package combination will reboot successfully.
