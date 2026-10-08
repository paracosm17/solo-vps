# Coolify 4.4.2 / Traefik 3.7.14 candidate — 2026-10-08

Candidate under evaluation. No target-version runtime qualification is claimed yet.

The reviewed Coolify 4.4.0 → 4.4.2 pair keeps embedded Reverb. The three
checksummed upstream installation artifacts are unchanged. Source review includes
the new backup-notification and traffic-IP-mode database migrations.

Traefik is a separate explicit native lifecycle. The shared manifest pins its exact
target digest and reviewed x86_64 source identities; host port reconciliation still
does not upgrade the proxy. Runtime/recovery results will be recorded after testing.
