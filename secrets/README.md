# Encrypted infrastructure and recovery secrets

This directory is reserved for **SOPS-encrypted infrastructure/recovery secret sources**. Normal application runtime secrets belong in Coolify; CI-only secrets belong in GitHub.

Repository rules:

- encrypted secret files use `*.enc.yaml` and contain SOPS metadata;
- plaintext secret files under `secrets/` are not valid project state;
- tracked recipient files are examples/placeholders only;
- generated SOPS policy/recipient state lives outside the Git checkout;
- an age private identity must never be stored in Git;
- SSH private keys are not stored here;
- losing every protected copy of the age private identity makes encrypted files unrecoverable.

Current runtime integrations use external ciphertext such as `backup.enc.yaml` and `observability.enc.yaml`; the VPS receives only the specific root-only runtime credentials required by those features.

See [`../docs/secrets-sops-age.md`](../docs/secrets-sops-age.md).
