# Disposable clean Ubuntu target proof

This is the maintainer/integration harness for the controlled clean-target half of CRIT-004. It is deliberately **provider-neutral**: Solo VPS does not create, resize, bill for, snapshot, or destroy cloud servers. The operator first creates one fresh Ubuntu 24.04 VPS in a provider account, then the harness proves the critical host path and emits sanitized evidence.

**Scheduling note:** this harness is source-ready, but the current release plan intentionally does not rent a VPS just for this proof. Run it during the batched external validation window after recovery source work and user-surface simplification are ready; the same short-lived compute can then be reimaged/reused for restore, upgrade and final V4 replay scenarios. See [`alpha-release-plan.md`](alpha-release-plan.md).

The target is **one-shot**. Do not point this command at an existing production/staging host and do not reuse a target that already contains Docker, Coolify, an active UFW policy, the managed admin, or Solo VPS host state.

## What the proof covers

The harness performs this controlled sequence from a separate Linux controller:

```text
explicit disposable marker + provider recovery acknowledgement
→ verify provider-console Ed25519 host-key fingerprint
→ clean Ubuntu 24.04 / noble preflight
→ refuse the current controller and configured production target
→ controller QA check
→ bootstrap identity doctor
→ first bootstrap
→ managed-admin verify
→ exact ephemeral human-key admin login
→ proof-gated SSH hardening
→ verify-ssh
→ exact human-key admin reconnect
→ direct root SSH denial
→ security audit
→ second bootstrap
→ require changed=0 / failed=0
→ final verify + audit
→ sanitized evidence JSON
```

Coolify is not part of this core proof. Backup restore, observability credentials, application delivery and release-candidate Coolify replay remain separate integration layers. The purpose here is to make the critical host/bootstrap/SSH/idempotency path reproducible before adding a larger disposable platform test.

## Safety boundary

The harness has several independent refusal gates:

- exact destructive-test confirmation;
- exact provider-console/recovery acknowledgement before SSH hardening;
- a target marker at `/root/.solo-vps-disposable-clean-target` owned `root:root` with mode `0600`;
- the marker value must equal the run-specific target id supplied to the harness;
- target OS must be Ubuntu `24.04` / `noble`;
- Docker, the Solo VPS SSH drop-in, Coolify ownership marker, managed admin and active UFW state must be absent;
- the target must not resolve to the current controller;
- if the normal external Solo VPS config exists, the target must not match its configured production host/IP;
- SSH uses a temporary `known_hosts` file with `StrictHostKeyChecking=yes` and requires the Ed25519 fingerprint copied from the provider console.

The proof does not disable SSH host-key checking and does not silently adopt an unknown server.

## Inputs that remain private

The bootstrap private key is read from an explicit controller path. The harness generates two additional temporary Ed25519 identities: one automation identity for Ansible after bootstrap and one exact human-login test identity. Their private halves live only in a temporary controller directory and are deleted when the process exits.

The generated evidence intentionally retains none of the following:

- target IP/hostname;
- disposable marker value;
- SSH host-key fingerprint;
- bootstrap or generated private-key paths/contents;
- generated public-key payloads;
- raw Ansible/SSH command logs.

On a failed command, a bounded sanitized tail is printed to the maintainer terminal for diagnosis. The harness leaves the disposable VPS intact on failure so provider-console recovery and targeted inspection remain possible.

## Prepare a fresh target

Create a fresh Ubuntu 24.04 LTS VPS with provider console/rescue access. The standard proof uses SSH port 22. Configure a temporary provider/bootstrap SSH public key during provisioning and keep its private half on the controller.

From the **provider console**, obtain the target Ed25519 host-key fingerprint:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

Record only the `SHA256:...` value.

Choose a non-secret run id on the controller, for example:

```bash
DISPOSABLE_TARGET_ID="clean-$(date -u +%Y%m%d%H%M%S)-$(python3 -c 'import secrets; print(secrets.token_hex(4))')"
printf '%s\n' "$DISPOSABLE_TARGET_ID"
```

Create the marker on the **disposable target** through the provider console:

```bash
install -m 0600 -o root -g root /dev/null /root/.solo-vps-disposable-clean-target
printf '%s\n' '<DISPOSABLE_TARGET_ID>' > /root/.solo-vps-disposable-clean-target
```

Do not create this marker on a maintained VPS.

## Run the source checks first

From the Linux controller that contains the Solo VPS source and its pinned QA toolchain:

```bash
make validate-disposable-clean-target
make test-disposable-clean-target
make qa-check
```

These commands do not contact or change a server.

## Run the controlled proof

The destructive proof target is intentionally absent from normal `make help`. Supply every target-specific value explicitly:

```bash
make prove-disposable-clean-target \
  DISPOSABLE_TARGET_HOST='<fresh-vps-host-or-ip>' \
  DISPOSABLE_TARGET_BOOTSTRAP_USER='root' \
  DISPOSABLE_TARGET_BOOTSTRAP_IDENTITY_FILE="$HOME/.ssh/solo-vps-disposable-provider" \
  DISPOSABLE_TARGET_HOST_KEY_SHA256='SHA256:<provider-console-fingerprint>' \
  DISPOSABLE_TARGET_ID='<DISPOSABLE_TARGET_ID>' \
  DISPOSABLE_TARGET_CONFIRM=I_HAVE_REVIEWED_THE_DISPOSABLE_CLEAN_TARGET \
  DISPOSABLE_TARGET_PROVIDER_RECOVERY_CONFIRM=I_HAVE_VERIFIED_DISPOSABLE_PROVIDER_RECOVERY
```

Use the provider's actual initial account instead of `root` when necessary; it must have passwordless non-interactive sudo. The proof still attempts a direct `root` SSH connection after hardening and requires it to fail.

A successful run ends with:

```text
PASS CRIT-004 disposable clean-target core proof
  target_address_retained: false
  generated_private_keys_retained: false
  raw_command_logs_retained: false
  second_bootstrap_changed: 0
  second_bootstrap_failed: 0
  sanitized_evidence: .../clean-target-evidence.json
```

The JSON is the public-safe evidence artifact. Review it before sharing it.

## Evidence location

By default the harness writes outside the source checkout:

```text
~/.local/share/solo-vps/evidence/disposable-clean-target/<target-id>/clean-target-evidence.json
```

An explicit `DISPOSABLE_TARGET_EVIDENCE_DIR` override may be used for a private CI artifact directory. The harness refuses an evidence path inside the Solo VPS source checkout.

The evidence records first/second bootstrap recaps, hardening/reconnect/root-denial/audit outcomes, source fingerprint and scope boundaries. It does not store raw logs.

## Failure handling

If the proof fails after mutation:

1. do not rerun the whole proof immediately;
2. keep the disposable VPS alive;
3. use provider console/rescue and the sanitized failure tail to identify the failed checkpoint;
4. preserve the target only long enough for diagnosis;
5. destroy it and start from another fresh Ubuntu 24.04 target for the next clean evidence run.

The clean-state gate intentionally rejects an already-mutated target. A second run on the same server is not clean-host evidence.

## Disposal

Solo VPS deliberately **does not create or destroy** provider resources. After a successful evidence review, **destroy the VPS** in the provider control plane and delete/revoke any temporary bootstrap key that existed only for this test.

Do not leave the disposable host running merely because the proof passed; it is not a maintained Solo VPS environment.
