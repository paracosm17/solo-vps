# ADR-0002: Keep the SOPS age private key on the operator workstation

Status: Accepted  
Date: 2026-08-11  
Simplified: 2026-08-14

## Context

Solo VPS has one production VPS. The user also naturally has a home/work computer used to administer it. That workstation can be Windows or Linux; it is **not another server** and Solo VPS does not require a second VPS, VM, always-on controller host, Vault, KMS, or other secrets service.

The project uses SOPS + age only for infrastructure/recovery values that should not be committed to Git as plaintext. Application environment variables remain in Coolify.

## Decision

Keep one production age private key on the **operator workstation**. Keep generated public recipient/policy state outside the public product checkout; a private operator repository may intentionally track SOPS ciphertext when a concrete feature needs it.

Recommended model:

```text
Windows or Linux home workstation
  one age private key
  optional backup copy somewhere the operator can recover

persistent workstation state
  public age recipient
  SOPS policy

Git/private operator repository, when intentionally used
  encrypted *.enc.yaml files

one VPS
  no production age private key by default
  only concrete runtime credentials when a service actually needs them

Coolify
  application runtime secrets
```

This does not require a second server. It also does not require a dedicated SSH identity or a separate Ansible controller just for secrets.

## Operational rule

Keep this simple:

1. generate one age key once on the home workstation;
2. record/copy the private key somewhere recoverable if desired;
3. initialize persistent public recipient/policy state outside the product checkout;
4. encrypt infrastructure secret files with SOPS when a real feature needs one;
5. do not copy the production age private key to Git or to the VPS by default.

A future service integration may materialize one concrete runtime credential to the VPS. That implementation belongs to the milestone that actually needs the credential (for example backup storage), not to a generic M13 secret-delivery framework.

## Why

This gives the useful part of SOPS + age without enterprise ceremony:

- a leaked Git repository does not contain plaintext infrastructure credentials;
- losing/reinstalling the VPS does not destroy the only decryption key;
- the user manages one key, not a secret-management platform;
- the one-VPS architecture stays one VPS.

## Consequences

### Positive

- very small operational surface;
- Windows and Linux home workstations are both valid;
- no second server or always-on controller;
- no mandatory external KMS/Vault account;
- private age material remains outside Git.

### Negative

- if the only copy of the age private key is lost, encrypted files cannot be decrypted;
- the user must keep the key somewhere they can recover;
- native SOPS/age installation differs between Windows and Linux.

## Recovery

A backup copy is recommended but does not need a special ceremony. A password manager secure note/file attachment, encrypted external drive, or another operator-controlled backup location is sufficient for the Solo VPS baseline.

Recovery proof for M13 is simply: a copied production key can derive the same public recipient and decrypt a disposable SOPS file. No separate recovery server is required.

## Validation

M13 is complete when:

1. repository policy contains no private age identity or plaintext secret source;
2. pinned SOPS + age crypto has been proven with a disposable roundtrip;
3. the operator has generated one production age identity on a Windows or Linux workstation;
4. the public recipient initializes the persistent workstation SOPS policy/recipient files outside the checkout;
5. a disposable encrypted file can be encrypted/decrypted with that workstation key;
6. the production private age identity is absent from the VPS.

Concrete runtime credential delivery is validated by the milestone that actually introduces that credential.

M14 implements that first concrete path without changing the one-key model: the encrypted backup bundle stays in persistent workstation state, the workstation decrypts it only for an explicit push, and plaintext travels to the managed VPS over SSH stdin. The VPS stores only `/etc/solo-vps/backup/credentials.json` as `root:root 0600`; the production age private key is not copied there. This narrow backup helper is not a generic secret-distribution service.
