# Coolify 4.4.6 candidate qualification

Candidate: direct 4.4.3 → 4.4.6, embedded Reverb, Sentinel 1.0.2, existing reviewed Traefik 3.7.14.

All release notes for 4.4.4, 4.4.5 and 4.4.6 and the tagged comparison were reviewed. The three installation artifacts retain independently fetched SHA256 identities. There are three forward-only data migrations: IPv6 server/Sentinel URL normalization, duplicate Redis usernames and duplicate Nixpacks Node versions. Duplicate cleanup keeps the newest updated timestamp, then highest ID. Source/current artifact identity does not inherit runtime qualification.

Controlled runtime qualification is pending. This candidate is not yet a published supported release.
