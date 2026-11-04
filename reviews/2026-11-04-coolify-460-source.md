# Coolify 4.6.0 — source preparation and production-first gate

- Date: 2026-11-04.
- Upstream release: https://github.com/coollabsio/coolify/releases/tag/v4.6.0 (published 2026-11-02).
- Proposed transition: Coolify 4.5.3 → 4.6.0, official `docker.io/coollabsio/coolify` image.
- Origin: last reported 4.5.3 production verification, `reviews/2026-10-31-coolify-453-production.md`. **Current live version is not independently observed in this source review.**
- Keep Sentinel 1.1.3 (same reviewed x86_64 image identity as origin) and Traefik 3.7.16.
- Keep Docker Engine 29.x, loopback-only 8000/6001/6002, ingress guard, checkpoint, transaction and explicit forward resume.

## Source artifact evidence

The official upstream `v4.5.3` and `v4.6.0` tags were read directly through the GitHub connector. Independently computed SHA-256 for all three raw files; every hash matches the previous production manifest and remains unchanged at 4.6.0:

| File | Raw SHA-256 |
| --- | --- |
| `docker-compose.yml` | `2532ee9258e10ad4e86cb3c2b46c29fe9329f5a0dace0f7da410744feec279bd` |
| `docker-compose.prod.yml` | `f8b104aadfca48d0033fdee6cb87fea13c68bc5c67c63ba18b1934e9f901ff5d` |
| `.env.production` | `7895e54f7c9d40063e76afec9b35839048d91e5c3b5107d64ea49ef6987c304a` |

The official `v4.6.0/upstream.json` continues to pin Sentinel `1.1.3` and Traefik `3.7.16`. The x86_64 Sentinel identity is carried forward from the 4.5.3 production-qualified manifest, **not newly pulled on a validation host**.

The 4.6.0 release notes require:
- API/MCP deletion now requires `delete` or `root`; existing ordinary `read`/`write`/`deploy` tokens should remain least-privileged. New resource scopes may restrict even a syntactically valid token.
- Upstream version identification now comes from the image, not `COOLIFY_VERSION` in `.env`. Solo VPS removes that obsolete line for first install, supported upgrade, and forward resume; existing secrets and image-tag pin are not replaced.
- An unchanged Compose file is not proof of unchanged migrations or API/server behavior. Keep the exact-instance database and `APP_KEY` for recovery.

## Validation and promotion gates

Source/contract/unit qualification: **V2**. GitHub Actions Repository CI `fast-source` succeeded for candidate commit `3e763392ada99e1cbb9e57a2a8d117ebd876061d` (run [41745001036](https://github.com/paracosm17/solo-vps/actions/runs/41745001036)); Documentation `build` succeeded (run [41745000936](https://github.com/paracosm17/solo-vps/actions/runs/41745000936)). Checks included 153 YAML files, the platform lifecycle/upgrade regression tests, Ansible syntax checks and static lint (`0 failure(s), 0 warning(s)` in 183 processed files). The first commit's CI failure exposed a 4.5.3-only historical artifact checker; a follow-up made that checker use the current release manifest and its regression tests passed. These are **not V3 or V5**. No disposable server is used at the owner's request; no target server, live migration, API token or backup has been accessed.

Before production mutation: verify the current marker/image is exactly 4.5.3, external encrypted Coolify control-plane backup and application-data backup are current, decryption/restore boundary is understood, SSH/provider recovery works, Sentinel is In Sync, and `make coolify-upgrade-preflight` passes. Use the explicit project-owned `make coolify-upgrade`, not the Coolify UI update button. Pause deployments.

After production mutation: record the actual 4.6.0 image, health/realtime/terminal endpoints, Sentinel and proxy, private ports, full `make verify-coolify`, `make verify`, `make audit`, application HTTPS/CI/API checks, migration warnings, backup checkpoint and available recovery. Update the manifest qualification fingerprint/evidence *only after observed results*. Check v0.2.7 release prerequisites and request release approval separately; do not publish a tag from this source review.
