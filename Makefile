SHELL := /bin/bash
.DEFAULT_GOAL := help

PYTHON ?= python3

# Keep the Git checkout source-only. Mutable per-installation controller state lives
# under one persistent user-owned data root and survives source replacement/reclone.
SOLO_VPS_DATA_BASE ?= $(if $(XDG_DATA_HOME),$(XDG_DATA_HOME),$(HOME)/.local/share)
SOLO_VPS_DATA_DIR ?= $(SOLO_VPS_DATA_BASE)/solo-vps
SOLO_VPS_DEFAULT_DATA_DIR := $(SOLO_VPS_DATA_BASE)/solo-vps
SOLO_VPS_CONFIG_DIR ?= $(SOLO_VPS_DATA_DIR)/config
SOLO_VPS_TOOLCHAIN_DIR ?= $(SOLO_VPS_DATA_DIR)/toolchain
SOLO_VPS_SOPS_DIR ?= $(SOLO_VPS_DATA_DIR)/sops
SOLO_VPS_SECRET_DIR ?= $(SOLO_VPS_DATA_DIR)/secrets
SOLO_VPS_EVIDENCE_DIR ?= $(SOLO_VPS_DATA_DIR)/evidence
SOLO_VPS_STATE_DIR ?= $(SOLO_VPS_DATA_DIR)/state
QA_VENV ?= $(SOLO_VPS_TOOLCHAIN_DIR)/qa
QA_COLLECTIONS_DIR ?= $(SOLO_VPS_TOOLCHAIN_DIR)/ansible-collections
QA_PYTHON := $(QA_VENV)/bin/python
QA_ANSIBLE_PLAYBOOK := $(QA_VENV)/bin/ansible-playbook
QA_ANSIBLE_GALAXY := $(QA_VENV)/bin/ansible-galaxy
QA_ANSIBLE_DOC := $(QA_VENV)/bin/ansible-doc
QA_ANSIBLE_LINT := $(QA_VENV)/bin/ansible-lint
QA_YAMLLINT := $(QA_VENV)/bin/yamllint
QA_READY_MARKER := $(QA_VENV)/.solo-vps-ready
DOCS_VENV ?= $(SOLO_VPS_TOOLCHAIN_DIR)/docs
DOCS_SITE_DIR ?= $(SOLO_VPS_DATA_DIR)/docs-site
DOCS_MKDOCS := $(DOCS_VENV)/bin/mkdocs
DOCS_REQUIREMENTS := requirements-docs.txt

# The pinned persistent Ansible toolchain is the default controller runtime too.
# Callers may still override these variables explicitly when debugging another controller.
ANSIBLE_PLAYBOOK ?= $(QA_ANSIBLE_PLAYBOOK)
ANSIBLE_GALAXY ?= $(QA_ANSIBLE_GALAXY)
ANSIBLE_DOC ?= $(QA_ANSIBLE_DOC)
ANSIBLE_COLLECTIONS_PATH ?= $(abspath $(QA_COLLECTIONS_DIR))
ANSIBLE_CONFIG := ansible/ansible.cfg
CONFIG ?= $(SOLO_VPS_CONFIG_DIR)/config.yml
INVENTORY ?= $(SOLO_VPS_CONFIG_DIR)/hosts.yml
SOPS_POLICY ?= $(SOLO_VPS_SOPS_DIR)/.sops.yaml
SOPS_RECIPIENT_FILE ?= $(SOLO_VPS_SOPS_DIR)/production.txt
BACKUP_SECRET_FILE ?= $(SOLO_VPS_SECRET_DIR)/backup.enc.yaml
OBSERVABILITY_SECRET_FILE ?= $(SOLO_VPS_SECRET_DIR)/observability.enc.yaml
METRICS_SECRET_FILE ?= $(SOLO_VPS_SECRET_DIR)/metrics.enc.yaml
AGE_KEY_FILE ?= $(HOME)/.config/solo-vps/age-key.txt
EXAMPLE_CONFIG := config/config.example.yml
EXAMPLE_INVENTORY := ansible/inventories/example/hosts.yml
PLAYBOOK_DIR := ansible/playbooks
ANSIBLE_REQUIREMENTS := ansible/requirements.yml
CONFIG_VALIDATOR := scripts/validate_config.py
FIREWALL_CONTRACT_VALIDATOR := scripts/validate_firewall_contract.py
DOCKER_CONTRACT_VALIDATOR := scripts/validate_docker_contract.py
DOCTOR := scripts/doctor.py
PLATFORM_DOCTOR := scripts/doctor_platform.py
VERIFY_CONTRACT_VALIDATOR := scripts/validate_verify_contract.py
AUDIT_CONTRACT_VALIDATOR := scripts/validate_audit_contract.py
OPS_VISIBILITY_VALIDATOR := scripts/validate_ops_visibility_contract.py
OBSERVABILITY_TOOLING_VALIDATOR := scripts/validate_observability_tooling.py
OBSERVABILITY_CREDENTIALS_VALIDATOR := scripts/validate_observability_credentials_contract.py
OBSERVABILITY_LOG_DRAIN_VALIDATOR := scripts/validate_observability_log_drain.py
OBSERVABILITY_RUNTIME_VALIDATOR := scripts/validate_observability_runtime.py
OBSERVABILITY_SECRET_BUNDLE := scripts/observability_secret_bundle.py
OBSERVABILITY_CREDENTIAL_INSTALLER := scripts/install_observability_credentials.py
OBSERVABILITY_ROLE_DIR := ansible/roles/observability
METRICS_CREDENTIALS_VALIDATOR := scripts/validate_metrics_credentials_contract.py
METRICS_RUNTIME_VALIDATOR := scripts/validate_metrics_runtime.py
METRICS_SECRET_BUNDLE := scripts/metrics_secret_bundle.py
METRICS_CREDENTIAL_INSTALLER := scripts/install_metrics_credentials.py
METRICS_ROLE_DIR := ansible/roles/metrics
QA_CONTRACT_VALIDATOR := scripts/validate_qa_contract.py
README_CONTRACT_VALIDATOR := scripts/validate_readme_contract.py
DOCUMENTATION_GOVERNANCE_VALIDATOR := scripts/validate_documentation_governance.py
AI_CODING_VALIDATOR := scripts/validate_ai_coding.py
DOCS_I18N_VALIDATOR := scripts/validate_docs_i18n.py
EXTERNAL_UPTIME_CONTRACT_VALIDATOR := scripts/validate_external_uptime_contract.py
EXTERNAL_UPTIME := scripts/external_uptime.py
ONBOARDING_CONTRACT_VALIDATOR := scripts/validate_onboarding_contract.py
ARCHITECTURE_DOCS_VALIDATOR := scripts/validate_architecture_docs.py
COMMUNITY_POLICY_VALIDATOR := scripts/validate_community_policy.py
UPGRADE_GUIDE_VALIDATOR := scripts/validate_upgrade_guide.py
PLATFORM_LIFECYCLE_CONTRACT_VALIDATOR := scripts/validate_platform_lifecycle_contract.py
PLATFORM_LIFECYCLE := scripts/platform_lifecycle.py
PLATFORM_LIFECYCLE_POLICY := docs/contracts/platform-lifecycle-policy.yml
COOLIFY_UPGRADE_CONFIRM ?=
COOLIFY_UPGRADE_CONFIRM_REQUIRED := I_HAVE_REVIEWED_THE_COOLIFY_UPGRADE_PLAN
COOLIFY_UPGRADE_RESUME_CONFIRM ?=
COOLIFY_UPGRADE_RESUME_CONFIRM_REQUIRED := I_HAVE_REVIEWED_THE_INTERRUPTED_COOLIFY_UPGRADE
COOLIFY_EVALUATION_TARGET_ID ?=
COOLIFY_EVALUATION_DATA_DIR ?=
COOLIFY_EVALUATION_MARKER := $(COOLIFY_EVALUATION_DATA_DIR)/.coolify-4.3.21-disposable-evaluation
COOLIFY_SENTINEL_URL ?=
COOLIFY_EVALUATION_CONFIRM ?=
COOLIFY_EVALUATION_CONFIRM_REQUIRED := I_HAVE_VERIFIED_A_DISPOSABLE_COOLIFY_4_3_21_TARGET
COOLIFY_EVALUATION_INTERRUPT_AFTER_MARKER ?= false
RELEASE_PROCESS_VALIDATOR := scripts/validate_release_process.py
HOSTED_CI_CONTRACT_VALIDATOR := scripts/validate_hosted_ci_contract.py
DISPOSABLE_CLEAN_TARGET_CONTRACT_VALIDATOR := scripts/validate_disposable_clean_target_contract.py
DISPOSABLE_CLEAN_TARGET_PROOF := scripts/prove_disposable_clean_target.py
RELEASE_DRY_RUN := scripts/release_dry_run.py
CONTROLLER_SETUP := scripts/controller_setup.sh
SSH_KEY_SETUP := scripts/ensure_ssh_key.py
LOCAL_INIT := scripts/init_local.py
INVENTORY_CONFIGURE := scripts/configure_inventory.py
STATE_LAYOUT_VALIDATOR := scripts/validate_state_layout.py
ACCESS_PREPARE := scripts/prepare_access.py
ADMIN_HANDOFF := scripts/handoff_admin_workspace.py
HUMAN_ADMIN_KEY_CONFIGURE := scripts/configure_human_admin_key.py
RELEASE_VERSION ?=
DISPOSABLE_TARGET_HOST ?=
DISPOSABLE_TARGET_BOOTSTRAP_USER ?= root
BOOTSTRAP_USER ?=
DISPOSABLE_TARGET_BOOTSTRAP_IDENTITY_FILE ?=
DISPOSABLE_TARGET_HOST_KEY_SHA256 ?=
DISPOSABLE_TARGET_ID ?=
DISPOSABLE_TARGET_ADMIN_USER ?= ops
DISPOSABLE_TARGET_CONFIRM ?=
DISPOSABLE_TARGET_PROVIDER_RECOVERY_CONFIRM ?=
DISPOSABLE_TARGET_EVIDENCE_DIR ?= $(SOLO_VPS_EVIDENCE_DIR)/disposable-clean-target/$(DISPOSABLE_TARGET_ID)
UPTIME_HEALTH_URL ?=
UPTIME_INTERVAL_SECONDS ?= 300
UPTIME_TIMEOUT_SECONDS ?= 10
UPTIME_PROOF_ID ?=
UPTIME_EXERCISE_MODE ?=
UPTIME_NOTIFICATION_CHANNEL ?=
UPTIME_PROVIDER_ARTIFACT_SHA256 ?=
UPTIME_PROVIDER_ARTIFACT_REVIEW_CONFIRM ?=
UPTIME_NOTIFICATION_TEST_RECEIVED_AT ?=
UPTIME_OUTAGE_STARTED_AT ?=
UPTIME_ALERT_RECEIVED_AT ?=
UPTIME_SERVICE_RESTORED_AT ?=
UPTIME_RECOVERY_RECEIVED_AT ?=
UPTIME_EVIDENCE_CONFIRM ?=
UPTIME_EVIDENCE_DIR ?= $(SOLO_VPS_EVIDENCE_DIR)/external-uptime/$(UPTIME_PROOF_ID)
QA_REQUIREMENTS := tools/qa-requirements.txt
QA_YAML_PATHS := ansible config .github/dependabot.yml .github/workflows/repository-ci.yml .github/workflows/docs.yml .sops.yaml.example docs/contracts templates/github-actions/hello-app-ci.yml
COOLIFY_CONTRACT_VALIDATOR := scripts/validate_coolify_contract.py
COOLIFY_DEFAULTS := ansible/roles/coolify/defaults/main.yml
COOLIFY_COMPOSE_OVERRIDE := ansible/roles/coolify/templates/docker-compose.solo-vps.yml.j2
COOLIFY_COMPOSE_OVERRIDE_VALIDATOR := scripts/validate_coolify_compose_override.py
COOLIFY_INSTALL_BACKEND_VALIDATOR := scripts/validate_coolify_install_backend.py
EXAMPLE_APP_DIR := examples/hello-app
EXAMPLE_APP_VALIDATOR := scripts/validate_example_app.py
CI_TEMPLATE := templates/github-actions/hello-app-ci.yml
CI_TEMPLATE_VALIDATOR := scripts/validate_github_actions_template.py
APPLICATION_MIGRATION_CONTRACT_VALIDATOR := scripts/validate_application_migration_contract.py
OPERATOR_SURFACE_VALIDATOR := scripts/validate_operator_surface.py
OPERATOR_LIFECYCLE := scripts/operator_lifecycle.py
COOLIFY_IMAGE_HANDOFF_VALIDATOR := scripts/validate_coolify_image_handoff.py
COOLIFY_DEPLOY_API := scripts/coolify_deploy_api.py
COOLIFY_ROLLBACK_PROOF := scripts/prove_coolify_deploy_rollback.py
CI_DEPLOY_TRANSPORT := scripts/ci_deploy_transport.py
COOLIFY_IMAGE_REF ?=
COOLIFY_RESOURCE_UUID ?=
COOLIFY_API_BASE_URL ?= http://127.0.0.1:8000/api/v1
COOLIFY_API_DEPLOY_CONFIRM ?=
COOLIFY_API_DEPLOY_CONFIRM_REQUIRED := I_HAVE_REVIEWED_THE_LOOPBACK_COOLIFY_API_DEPLOYMENT
COOLIFY_ROLLBACK_PROOF_CONFIRM ?=
COOLIFY_ROLLBACK_PROOF_CONFIRM_REQUIRED := I_HAVE_REVIEWED_THE_FAILED_DEPLOYMENT_ROLLBACK_PROOF
CI_DEPLOY_SERVER_HOST ?=
CI_DEPLOY_PUBLIC_KEY_FILE ?=
CI_DEPLOY_TRANSPORT_CONFIRM ?=
CI_DEPLOY_TRANSPORT_CONFIRM_REQUIRED := I_HAVE_REVIEWED_THE_RESTRICTED_CI_SSH_TRANSPORT
DEPENDABOT_CONFIG := .github/dependabot.yml
DEPENDENCY_HYGIENE_VALIDATOR := scripts/validate_dependency_hygiene.py
SOPS_POLICY_VALIDATOR := scripts/validate_secrets_policy.py
SOPS_POLICY_INIT := scripts/init_sops_policy.py
SECRETS_TOOLCHAIN := scripts/secrets_toolchain.py
SECRETS_TOOLCHAIN_MANIFEST := tools/secrets-toolchain.json
SOPS_ROUNDTRIP := scripts/test_sops_roundtrip.py
WORKSTATION_SECRETS_VALIDATOR := scripts/validate_workstation_secrets_contract.py
PUBLIC_PRODUCT_HYGIENE_VALIDATOR := scripts/validate_public_product_hygiene.py
VPS_SECRETS_BOUNDARY_VERIFIER := scripts/verify_vps_secrets_boundary.py
BACKUP_SECRET_BUNDLE := scripts/backup_secret_bundle.py
BACKUP_CREDENTIAL_INSTALLER := scripts/install_backup_credentials.py
VPS_SECRETS_ADMIN_HOME ?=
BACKUP_VPS_HOST ?=
BACKUP_VPS_USER ?=
BACKUP_REMOTE_PROJECT ?= ~/solo-vps
BACKUP_SSH_IDENTITY_FILE ?=
BACKUP_RETENTION_CONFIRM ?=
BACKUP_RETENTION_CONFIRM_REQUIRED := I_HAVE_REVIEWED_THE_BACKUP_RETENTION_PLAN
OBSERVABILITY_VPS_HOST ?=
OBSERVABILITY_VPS_USER ?=
OBSERVABILITY_REMOTE_PROJECT ?= ~/solo-vps
OBSERVABILITY_SSH_IDENTITY_FILE ?=
METRICS_VPS_HOST ?=
METRICS_VPS_USER ?=
METRICS_REMOTE_PROJECT ?= ~/solo-vps
METRICS_SSH_IDENTITY_FILE ?=
OPS_LOG_CONTAINER ?= $(CONTAINER)
OPS_LOG_TAIL ?= $(if $(TAIL),$(TAIL),100)
BACKUP_TOOLING_VALIDATOR := scripts/validate_backup_tooling.py
BACKUP_CREDENTIALS_VALIDATOR := scripts/validate_backup_credentials_contract.py
BACKUP_POLICY_VALIDATOR := scripts/validate_backup_policy.py
BACKUP_RUNTIME_VALIDATOR := scripts/validate_backup_runtime_contract.py
BACKUP_RUNTIME := scripts/restic_runtime.py
DATABASE_BACKUP_CONTRACT_VALIDATOR := scripts/validate_database_backup_contract.py
DATABASE_BACKUP_CONTRACT := docs/contracts/database-backup-policy.yml
DATABASE_BACKUP_ADR := docs/adr/0003-coolify-native-database-backups.md
DATABASE_BACKUP_RUNTIME_VALIDATOR := scripts/validate_database_backup_runtime_contract.py
DATABASE_BACKUP_API := scripts/coolify_database_backup_api.py
DATABASE_RESTORE_EXERCISE := scripts/postgres_restore_exercise.py
DATABASE_BACKUP_STATE_DIR ?= $(SOLO_VPS_STATE_DIR)/database-backups
DATABASE_BACKUP_BASE_URL ?= http://127.0.0.1:8000/api/v1
DATABASE_BACKUP_DATABASE_UUID ?=
DATABASE_BACKUP_S3_STORAGE_UUID ?=
DATABASE_BACKUP_DATABASES ?=
DATABASE_BACKUP_DUMP_ALL ?= false
DATABASE_BACKUP_FREQUENCY ?= daily
DATABASE_BACKUP_RETENTION_AMOUNT_LOCALLY ?= 2
DATABASE_BACKUP_RETENTION_DAYS_S3 ?= 30
DATABASE_BACKUP_FRESHNESS_HOURS ?= 36
DATABASE_BACKUP_SCHEDULE_UUID ?=
DATABASE_BACKUP_CONFIRM ?=
DATABASE_BACKUP_CONFIRM_REQUIRED := I_HAVE_REVIEWED_THE_COOLIFY_DATABASE_BACKUP_POLICY
DATABASE_RESTORE_ARCHIVE ?=
DATABASE_RESTORE_HOST ?= 127.0.0.1
DATABASE_RESTORE_PORT ?= 5432
DATABASE_RESTORE_USER ?= postgres
DATABASE_RESTORE_DATABASE ?=
DATABASE_RESTORE_PGPASS_FILE ?=
DATABASE_RESTORE_VERIFY_QUERY ?=
DATABASE_RESTORE_EXPECT ?=
DATABASE_RESTORE_CONFIRM ?=
DATABASE_RESTORE_CONFIRM_REQUIRED := I_HAVE_VERIFIED_A_DISPOSABLE_POSTGRES_RESTORE_TARGET
DISASTER_RECOVERY_CONTRACT_VALIDATOR := scripts/validate_disaster_recovery_contract.py
RECOVERY_KIT := scripts/recovery_kit.py
COOLIFY_INSTANCE_RESTORE := scripts/coolify_instance_restore.py
RECOVERY_KIT_OUTPUT ?=
RECOVERY_SOURCE_REVISION ?= $(shell git rev-parse --verify HEAD 2>/dev/null || printf 'PRE-ALPHA-unversioned')
COOLIFY_INSTANCE_BACKUP_ARCHIVE ?=
RECOVERY_STAGING_ROOT ?=
RECOVERY_STAGING_CONFIRM ?=
RECOVERY_STAGING_CONFIRM_REQUIRED := I_HAVE_VERIFIED_A_PRIVATE_DISASTER_RECOVERY_STAGING_DIRECTORY
RECOVERY_TARGET_ID ?=
RECOVERY_TARGET_CONFIRM ?=
RECOVERY_TARGET_CONFIRM_REQUIRED := I_HAVE_VERIFIED_THE_REPLACEMENT_VPS_FOR_COOLIFY_RESTORE
BACKUP_ROLE_DIR := ansible/roles/backup
BACKUP_DEFAULTS := ansible/roles/backup/defaults/main.yml
SOPS_AGE_RECIPIENT ?=
SECRETS_ARTIFACT_DIR ?=
SSH ?= ssh
SSH_HARDENING_CONFIRM ?=
SSH_HARDENING_CONFIRM_REQUIRED := I_HAVE_VERIFIED_PROVIDER_RECOVERY
SSH_HARDENING_ADMIN_LOGIN_CONFIRM ?=
SSH_HARDENING_ADMIN_LOGIN_CONFIRM_REQUIRED := I_HAVE_VERIFIED_WORKSTATION_ADMIN_LOGIN
HUMAN_SSH_PUBLIC_KEY_FILE ?=
COOLIFY_RECOVERY_CONFIRM ?=
COOLIFY_RECOVERY_CONFIRM_REQUIRED := I_HAVE_REVIEWED_THE_PARTIAL_SOLO_VPS_INSTALL
YAML_FILES := $(shell find config ansible -type f \( -name '*.yml' -o -name '*.yaml' \) -print | sort)

export ANSIBLE_CONFIG
export ANSIBLE_COLLECTIONS_PATH
export PYTHONDONTWRITEBYTECODE := 1

.PHONY: docs docs-install docs-build validate-docs-i18n validate-platform-lifecycle test-platform-lifecycle platform-lifecycle-plan coolify-upgrade-preflight coolify-upgrade coolify-upgrade-resume coolify-evaluation-init check-coolify-evaluation-args coolify-evaluate-4-3-21-preflight coolify-evaluate-4-3-21-upgrade coolify-evaluate-4-3-21-resume verify-coolify-4-3-21-candidate validate-external-uptime test-external-uptime uptime-plan uptime-evidence validate-documentation-governance test-documentation-governance validate-operator-surface test-operator-surface apply secure platform backup recover update help-ops help-dev help-all validate-application-migration-contract test-application-migration-contract check-database-backup-args database-backup-plan database-backup-adopt database-backup-configure database-backup-trigger database-backup-verify database-restore-inspect database-restore-exercise validate-disaster-recovery test-disaster-recovery recovery-kit-export recovery-kit-verify recovery-kit-extract coolify-instance-restore-inspect coolify-instance-restore-plan coolify-instance-restore-apply help paths setup validate-state-layout test-state-layout test-inventory-config controller-check ssh-key init human-admin-key-file human-admin-key-stdin use-bootstrap use-admin prepare-access admin-handoff deps check-ansible-deps validate validate-yaml validate-firewall-contract test-firewall-contract validate-docker-contract test-docker-contract validate-onboarding-contract test-onboarding-contract validate-qa-contract test-qa-contract validate-readme-contract test-readme-contract validate-architecture-docs test-architecture-docs validate-community-policy test-community-policy validate-upgrade-guide test-upgrade-guide validate-release-process test-release-process validate-hosted-ci-contract test-hosted-ci-contract validate-disposable-clean-target test-disposable-clean-target prove-disposable-clean-target ci-fast-source ci-fast release-dry-run qa-tools qa-check qa-static validate-example-config validate-coolify-contract test-coolify-install-backend validate-example-app test-example-app validate-ci-template test-ci-template validate-coolify-image-handoff test-coolify-image-handoff test-coolify-deploy-api test-ci-deploy-transport validate-dependency-hygiene validate-secrets-policy test-sops-policy validate-secrets-toolchain test-secrets-toolchain test-workstation-secrets validate-public-product-hygiene test-public-product-hygiene verify-vps-secrets-boundary secrets-tools secrets-tools-offline check-secrets-tools test-sops-roundtrip secrets-crypto-proof secrets-crypto-proof-offline init-sops-policy validate-config ansible-syntax doctor doctor-local doctor-admin-local doctor-platform-local preflight bootstrap verify firewall verify-firewall updates verify-updates docker verify-docker coolify-readiness coolify coolify-recover verify-coolify ssh-harden verify-ssh validate-backup-tooling validate-backup-credentials test-backup-credentials validate-backup-policy test-backup-policy validate-backup-runtime test-backup-runtime validate-database-backup-contract test-database-backup-contract validate-database-backup-runtime test-database-backup-runtime test-doctor-platform validate-verify-contract test-verify-contract validate-audit-contract test-audit-contract validate-ops-visibility test-ops-visibility validate-observability-tooling test-observability-tooling validate-observability-credentials test-observability-credentials validate-metrics-credentials test-metrics-credentials validate-metrics-runtime test-metrics-runtime validate-observability-log-drain test-observability-log-drain validate-observability-runtime test-observability-runtime verify-platform audit ops-status ops-logs observability-tooling verify-observability-tooling observability-secrets-init observability-secrets-check observability-secrets-push verify-observability-credentials verify-observability-log-drain verify-observability-log-drain-disabled diagnose-observability-log-drain test-observability-loki observability-runtime verify-observability-runtime audit-observability-confidentiality check-ops-log-args check-backup-policy check-backup-retention-confirm backup-tooling verify-backup-tooling backup-readiness backup-runtime backup-repository-init backup-repository-adopt backup-status backup-check backup-now backup-schedule-enable backup-maintenance-schedule-enable backup-retention-plan backup-retention-apply backup-restore-test backup-restore-staging check-local-config check-local-inventory check-local-files check-ssh-hardening-confirm check-coolify-recovery-confirm check-coolify-api-deploy-confirm check-ci-deploy-transport-confirm plan-coolify-deploy-api check-coolify-deploy-api deploy-coolify-image-api prove-coolify-deploy-rollback plan-ci-deploy-transport ci-deploy-transport verify-ci-deploy-transport backup-secrets-init backup-secrets-check backup-secrets-push verify-backup-credentials

help: ## Show the supported operator command surface
	@printf '%s\n' \
		'Solo VPS (PRE-ALPHA)' \
		'' \
		'Normal lifecycle:' \
		'  make setup       Prepare this controller and persistent Solo VPS state' \
		'  make apply       Apply/resume the host baseline and switch to admin.user' \
		'  make secure      Activate SSH hardening after the two access proofs' \
		'  make platform    Install/verify pinned Coolify after reconnecting as admin.user' \
		'  make verify      Read-only platform verification' \
		'' \
		'Diagnostics / operations:' \
		'  make doctor      Read-only preflight and capability diagnostics' \
		'  make bootstrap   Lower-level host-baseline target used by make apply' \
		'  make backup      Run one configured off-site backup and verify freshness' \
		'  make recover     Show the safety-gated lost-VPS recovery entry point' \
		'  make update      Review Solo VPS source and Docker/Coolify update plans (no mutation)' \
		'' \
		'More commands:' \
		'  make help-ops    Operational diagnostics and advanced service commands' \
		'  make help-dev    Validation, QA, CI, and release-maintainer commands' \
		'  make help-all    Complete documented Make target catalog' \
		'' \
		'Documentation:' \
		'  make docs        Start the local Material for MkDocs preview' \
		'  make docs-build  Build documentation in strict mode'

docs-install: ## Create/update the isolated Material for MkDocs environment
	@test -x "$(DOCS_VENV)/bin/python" || $(PYTHON) -m venv "$(DOCS_VENV)"
	@"$(DOCS_VENV)/bin/python" -m pip install --disable-pip-version-check -r "$(DOCS_REQUIREMENTS)"


validate-docs-i18n: ## Validate complete English/Russian public documentation pairing
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(DOCS_I18N_VALIDATOR) .


docs: validate-docs-i18n docs-install ## Start the local Material for MkDocs preview server
	@NO_MKDOCS_2_WARNING=1 "$(DOCS_MKDOCS)" serve


docs-build: validate-docs-i18n docs-install ## Build the Material for MkDocs site with strict validation
	@NO_MKDOCS_2_WARNING=1 "$(DOCS_MKDOCS)" build --strict --site-dir "$(DOCS_SITE_DIR)"


help-ops: ## Show operational and advanced service commands
	@printf '%s\n' \
		'Solo VPS operational commands' \
		'  make paths' \
		'  make doctor' \
		'  make verify' \
		'  make audit' \
		'  make ops-status' \
		'  make ops-logs OPS_LOG_CONTAINER=<container>' \
		'  make verify-coolify' \
		'  make verify-ssh' \
		'  make backup-status' \
		'  make backup-check' \
		'  make backup-now' \
		'  make backup-restore-test' \
		'  make platform-lifecycle-plan' \
		'  make coolify-upgrade-preflight' \
		'  make uptime-plan UPTIME_HEALTH_URL=https://app.example.com/healthz' \
		'  make verify-observability-runtime' \
		'  make verify-metrics-runtime' \
		'' \
		'Detailed safety-gated recovery/database commands: docs/command-reference.md'

help-dev: ## Show validation, QA, CI, and release-maintainer commands
	@printf '%s\n' \
		'Solo VPS developer / maintainer commands' \
		'  make validate' \
		'  make ci-fast-source' \
		'  make ci-fast' \
		'  make qa-check' \
		'  make qa-static' \
		'  make release-dry-run RELEASE_VERSION=v0.x.y' \
		'' \
		'All source validators/tests remain available through: make help-all'

help-all: ## Show every documented Make target, including internal validators/tests
	@printf '%s\n' 'Solo VPS complete target catalog:'
	@awk 'BEGIN {FS = ":.*## "} /^[a-zA-Z0-9_.-]+:.*## / {printf "  %-34s %s\n", $$1, $$2}' $(MAKEFILE_LIST)


paths: ## Show source and persistent Solo VPS controller-state paths
	@printf '%s\n' \
		'Solo VPS paths' \
		'  source:     $(abspath .)' \
		'  data:       $(SOLO_VPS_DATA_DIR)' \
		'  config:     $(CONFIG)' \
		'  inventory:  $(INVENTORY)' \
		'  toolchain:  $(SOLO_VPS_TOOLCHAIN_DIR)' \
		'  SOPS policy: $(SOPS_POLICY)' \
		'  backup ciphertext: $(BACKUP_SECRET_FILE)' \
		'  observability ciphertext: $(OBSERVABILITY_SECRET_FILE)' \
		'  metrics ciphertext: $(METRICS_SECRET_FILE)' \
		'  evidence:   $(SOLO_VPS_EVIDENCE_DIR)' \
		'  state:      $(SOLO_VPS_STATE_DIR)'

setup: ## Prepare minimal Ubuntu controller prerequisites, persistent state, and pinned Ansible runtime
	@bash $(CONTROLLER_SETUP)
	@$(MAKE) --no-print-directory runtime-tools
	@$(MAKE) --no-print-directory init
	@printf '%s\n' 'NEXT: edit the one persistent config shown by make paths, configure the workstation public key, then run make apply.'

controller-check: ## Verify first-run controller prerequisites without installing anything
	@command -v $(PYTHON) >/dev/null 2>&1 || { printf '%s\n' 'ERROR: python3 is unavailable; run: make setup' >&2; exit 127; }
	@$(PYTHON) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else "ERROR: Python 3.12+ is required; run: make setup")'
	@$(PYTHON) -c 'import ensurepip, yaml' >/dev/null 2>&1 || { printf '%s\n' 'ERROR: Python venv/ensurepip or PyYAML is unavailable; run: make setup' >&2; exit 127; }
	@command -v ssh >/dev/null 2>&1 || { printf '%s\n' 'ERROR: OpenSSH client is unavailable; run: make setup' >&2; exit 127; }
	@command -v ssh-keygen >/dev/null 2>&1 || { printf '%s\n' 'ERROR: ssh-keygen is unavailable; run: make setup' >&2; exit 127; }

ssh-key: controller-check ## Create/reuse the default controller SSH key without overwriting an existing identity
	@$(PYTHON) $(SSH_KEY_SETUP)

init: controller-check ## Initialize persistent config/inventory outside the Git checkout without overwriting operator state
	@$(PYTHON) $(LOCAL_INIT) --root . --data-dir "$(SOLO_VPS_DATA_DIR)" --config "$(CONFIG)" --inventory "$(INVENTORY)"

human-admin-key-file: controller-check check-local-config ## Configure the human workstation public key from an explicit local .pub file
	@test -n "$(HUMAN_SSH_PUBLIC_KEY_FILE)" || { printf '%s\n' 'ERROR: set HUMAN_SSH_PUBLIC_KEY_FILE to the workstation .pub file.' >&2; exit 2; }
	@$(PYTHON) $(HUMAN_ADMIN_KEY_CONFIGURE) --config "$(CONFIG)" --public-key-file "$(HUMAN_SSH_PUBLIC_KEY_FILE)"

human-admin-key-stdin: controller-check check-local-config ## Configure the human workstation public key from stdin without copying a private key
	@$(PYTHON) $(HUMAN_ADMIN_KEY_CONFIGURE) --config "$(CONFIG)" --stdin

use-bootstrap: controller-check check-local-files validate-config ## Sync inventory to server.host and an explicit provider/bootstrap SSH user
	@test -n "$(SSH_USER)" || { printf '%s\n' 'ERROR: SSH_USER is required, for example: make use-bootstrap SSH_USER=root' >&2; exit 2; }
	@$(PYTHON) $(INVENTORY_CONFIGURE) --config "$(CONFIG)" --inventory "$(INVENTORY)" --user "$(SSH_USER)"

use-admin: controller-check check-local-files validate-config ## Sync inventory to server.host and config admin.user after bootstrap/hardening
	@$(PYTHON) $(INVENTORY_CONFIGURE) --config "$(CONFIG)" --inventory "$(INVENTORY)" --admin

prepare-access: controller-check check-local-config check-local-inventory ## Prepare the current same-VPS controller SSH identity when controller and target are the same host
	@$(PYTHON) $(ACCESS_PREPARE) --config $(CONFIG) --inventory $(INVENTORY)

admin-handoff: controller-check check-local-files ## Prepare /home/<admin>/solo-vps and external admin state so the same-VPS flow can continue without root
	@$(PYTHON) $(ADMIN_HANDOFF) --root . --config "$(CONFIG)" --inventory "$(INVENTORY)" --state-dir "$(SOLO_VPS_DATA_DIR)"

apply: controller-check check-local-files validate-config ## Apply/resume host baseline, verify it, and switch inventory to admin.user
	@$(PYTHON) $(OPERATOR_LIFECYCLE) apply --root . --config "$(CONFIG)" --inventory "$(INVENTORY)" $(if $(BOOTSTRAP_USER),--bootstrap-user "$(BOOTSTRAP_USER)",)

secure: check-local-files check-ssh-hardening-confirm ## Activate SSH hardening after provider recovery + fresh workstation login proofs
	@$(MAKE) --no-print-directory ssh-harden
	@$(MAKE) --no-print-directory verify-ssh
	@printf '%s\n' 'PASS Solo VPS SSH security transition' 'NEXT: reconnect as admin.user, cd ~/solo-vps, then run make platform.'

platform: doctor-admin-local ## Install/verify pinned Coolify after the hardened admin reconnect
	@$(MAKE) --no-print-directory coolify
	@$(MAKE) --no-print-directory verify-coolify
	@printf '%s\n' 'PASS Solo VPS application platform' 'NEXT: run make verify, then follow docs/operations/first-app.md.'

backup: doctor-admin-local ## EXTERNAL WRITE: run one configured off-site backup and verify repository/freshness
	@$(MAKE) --no-print-directory backup-now
	@$(MAKE) --no-print-directory backup-check

recover: ## Show the safety-gated lost-VPS recovery entry point without mutating anything
	@printf '%s\n' \
		'Solo VPS lost-VPS recovery is intentionally not one destructive command.' \
		'1. Start from a fresh replacement Ubuntu 24.04 VPS and a verified off-VPS recovery kit.' \
		'2. Follow docs/disaster-recovery.md; restore operations require explicit target markers/confirmations.' \
		'3. Use make recovery-kit-verify before any destructive restore step.'

.PHONY: source-update-plan

update: source-update-plan platform-lifecycle-plan ## Review source and platform lifecycle plans; does not mutate versions
	@printf '%s\n' \
		'PASS current Solo VPS source and platform lifecycle plans' \
		'NEXT: run make coolify-upgrade-preflight before any supported Coolify upgrade; mutation remains safety-gated.'

source-update-plan: validate-upgrade-guide ## Show the reviewed-tag/new-checkout Solo VPS source update contract
	@printf '%s\n' \
		'Solo VPS source update contract:' \
		'1. Keep config, encrypted bundles, SSH keys and recovery material outside the checkout.' \
		'2. Clone the reviewed release tag into a new directory; do not git pull the active checkout.' \
		'3. In the new checkout run make setup, make paths, make validate, make doctor, make verify and make audit.' \
		'4. Keep the previous checkout only as source rollback context; it is not a runtime/data rollback.' \
		'SEE: docs/upgrades.md#update-solo-vps-source'

validate-platform-lifecycle: ## Validate CRIT-011 Docker/Coolify version and upgrade lifecycle source boundaries
	@$(PYTHON) $(PLATFORM_LIFECYCLE_CONTRACT_VALIDATOR) .

test-platform-lifecycle: ## Run CRIT-011 Docker/Coolify lifecycle regression tests
	@$(PYTHON) -m unittest tests.test_platform_lifecycle tests.test_platform_lifecycle_contract tests.test_coolify_upgrade_checkpoint tests.test_coolify_sentinel_inspect

platform-lifecycle-plan: validate-platform-lifecycle ## Show the reviewed Docker/Coolify lifecycle policy without network or mutation
	@$(PYTHON) $(PLATFORM_LIFECYCLE) plan --policy "$(PLATFORM_LIFECYCLE_POLICY)"

coolify-upgrade-preflight: check-local-files ## Read-only preflight for the exact previous-supported -> current-supported Coolify path
	@$(ANSIBLE_PLAYBOOK) -i "$(INVENTORY)" $(PLAYBOOK_DIR)/coolify-upgrade-preflight.yml --extra-vars "@$(CONFIG)"

coolify-upgrade: check-local-files ## Upgrade only the supported previous Coolify release after backup and exact confirmations
	@test "$(COOLIFY_UPGRADE_CONFIRM)" = "$(COOLIFY_UPGRADE_CONFIRM_REQUIRED)" || { printf '%s\n' 'ERROR: set COOLIFY_UPGRADE_CONFIRM=I_HAVE_REVIEWED_THE_COOLIFY_UPGRADE_PLAN after reviewing the preflight.' >&2; exit 2; }
	@$(ANSIBLE_PLAYBOOK) -i "$(INVENTORY)" $(PLAYBOOK_DIR)/coolify-upgrade.yml --extra-vars "@$(CONFIG)" --extra-vars "solo_vps_coolify_upgrade_confirm=$(COOLIFY_UPGRADE_CONFIRM)"

coolify-upgrade-resume: check-local-files ## Explicitly resume a known interrupted supported Coolify upgrade; never auto-downgrades
	@test "$(COOLIFY_UPGRADE_RESUME_CONFIRM)" = "$(COOLIFY_UPGRADE_RESUME_CONFIRM_REQUIRED)" || { printf '%s\n' 'ERROR: set COOLIFY_UPGRADE_RESUME_CONFIRM=I_HAVE_REVIEWED_THE_INTERRUPTED_COOLIFY_UPGRADE only after reviewing the protected transaction marker and recovery choices.' >&2; exit 2; }
	@$(ANSIBLE_PLAYBOOK) -i "$(INVENTORY)" $(PLAYBOOK_DIR)/coolify-upgrade-resume.yml --extra-vars "@$(CONFIG)" --extra-vars "solo_vps_coolify_upgrade_resume_confirm=$(COOLIFY_UPGRADE_RESUME_CONFIRM)"

coolify-evaluation-init: ## Initialize isolated controller state for the disposable Coolify candidate
	@test -n "$(COOLIFY_EVALUATION_TARGET_ID)" || { printf '%s\n' 'ERROR: COOLIFY_EVALUATION_TARGET_ID is required.' >&2; exit 2; }
	@test -n "$(COOLIFY_EVALUATION_DATA_DIR)" || { printf '%s\n' 'ERROR: COOLIFY_EVALUATION_DATA_DIR is required.' >&2; exit 2; }
	@test "$(abspath $(COOLIFY_EVALUATION_DATA_DIR))" != "$(abspath $(SOLO_VPS_DEFAULT_DATA_DIR))" || { printf '%s\n' 'ERROR: evaluation state must not use the normal Solo VPS data directory.' >&2; exit 2; }
	@test "$(abspath $(SOLO_VPS_DATA_DIR))" = "$(abspath $(COOLIFY_EVALUATION_DATA_DIR))" || { printf '%s\n' 'ERROR: export SOLO_VPS_DATA_DIR=$$COOLIFY_EVALUATION_DATA_DIR before initialization.' >&2; exit 2; }
	@install -d -m 0700 "$(COOLIFY_EVALUATION_DATA_DIR)"
	@if test -e "$(COOLIFY_EVALUATION_MARKER)"; then grep -Fxq 'target_id=$(COOLIFY_EVALUATION_TARGET_ID)' "$(COOLIFY_EVALUATION_MARKER)" || { printf '%s\n' 'ERROR: evaluation state is already bound to another target ID.' >&2; exit 2; }; else printf '%s\n' 'purpose=coolify-4.3.21-disposable-evaluation' 'target_id=$(COOLIFY_EVALUATION_TARGET_ID)' > "$(COOLIFY_EVALUATION_MARKER)"; chmod 0600 "$(COOLIFY_EVALUATION_MARKER)"; fi
	@$(MAKE) --no-print-directory init

check-coolify-evaluation-args:
	@test -n "$(COOLIFY_EVALUATION_TARGET_ID)" || { printf '%s\n' 'ERROR: COOLIFY_EVALUATION_TARGET_ID is required and must identify a disposable VPS.' >&2; exit 2; }
	@test -n "$(COOLIFY_EVALUATION_DATA_DIR)" || { printf '%s\n' 'ERROR: COOLIFY_EVALUATION_DATA_DIR is required.' >&2; exit 2; }
	@test "$(abspath $(COOLIFY_EVALUATION_DATA_DIR))" != "$(abspath $(SOLO_VPS_DEFAULT_DATA_DIR))" || { printf '%s\n' 'ERROR: evaluation refuses the normal Solo VPS data directory.' >&2; exit 2; }
	@test "$(abspath $(SOLO_VPS_DATA_DIR))" = "$(abspath $(COOLIFY_EVALUATION_DATA_DIR))" || { printf '%s\n' 'ERROR: SOLO_VPS_DATA_DIR must equal COOLIFY_EVALUATION_DATA_DIR.' >&2; exit 2; }
	@test -f "$(COOLIFY_EVALUATION_MARKER)" && grep -Fxq 'target_id=$(COOLIFY_EVALUATION_TARGET_ID)' "$(COOLIFY_EVALUATION_MARKER)" || { printf '%s\n' 'ERROR: run make coolify-evaluation-init for this disposable target first.' >&2; exit 2; }
	@test -n "$(COOLIFY_SENTINEL_URL)" || { printf '%s\n' 'ERROR: COOLIFY_SENTINEL_URL is required and must be the candidate Coolify HTTPS dashboard URL.' >&2; exit 2; }

coolify-evaluate-4-3-21-preflight: check-local-files check-coolify-evaluation-args ## Read-only disposable evaluation of 4.1.2 -> 4.3.21 and Sentinel prerequisites
	@$(ANSIBLE_PLAYBOOK) -i "$(INVENTORY)" $(PLAYBOOK_DIR)/coolify-evaluate-4-3-21-preflight.yml --extra-vars "@$(CONFIG)" --extra-vars "solo_vps_coolify_evaluation_target_id=$(COOLIFY_EVALUATION_TARGET_ID) solo_vps_coolify_evaluation_sentinel_url=$(COOLIFY_SENTINEL_URL)"

coolify-evaluate-4-3-21-upgrade: check-local-files check-coolify-evaluation-args ## MUTATING: evaluate exact 4.1.2 -> 4.3.21 only on a reviewed disposable VPS
	@test "$(COOLIFY_EVALUATION_CONFIRM)" = "$(COOLIFY_EVALUATION_CONFIRM_REQUIRED)" || { printf '%s\n' 'ERROR: candidate mutation requires COOLIFY_EVALUATION_CONFIRM=I_HAVE_VERIFIED_A_DISPOSABLE_COOLIFY_4_3_21_TARGET.' >&2; exit 2; }
	@$(ANSIBLE_PLAYBOOK) -i "$(INVENTORY)" $(PLAYBOOK_DIR)/coolify-evaluate-4-3-21-upgrade.yml --extra-vars "@$(CONFIG)" --extra-vars "solo_vps_coolify_evaluation_target_id=$(COOLIFY_EVALUATION_TARGET_ID) solo_vps_coolify_evaluation_sentinel_url=$(COOLIFY_SENTINEL_URL) solo_vps_coolify_evaluation_confirm=$(COOLIFY_EVALUATION_CONFIRM) solo_vps_coolify_evaluation_interrupt_after_marker=$(COOLIFY_EVALUATION_INTERRUPT_AFTER_MARKER) solo_vps_coolify_upgrade_confirm=$(COOLIFY_UPGRADE_CONFIRM_REQUIRED)"

coolify-evaluate-4-3-21-resume: check-local-files check-coolify-evaluation-args ## MUTATING: forward-resume an interrupted disposable candidate evaluation
	@test "$(COOLIFY_EVALUATION_CONFIRM)" = "$(COOLIFY_EVALUATION_CONFIRM_REQUIRED)" || { printf '%s\n' 'ERROR: candidate resume requires COOLIFY_EVALUATION_CONFIRM=I_HAVE_VERIFIED_A_DISPOSABLE_COOLIFY_4_3_21_TARGET.' >&2; exit 2; }
	@$(ANSIBLE_PLAYBOOK) -i "$(INVENTORY)" $(PLAYBOOK_DIR)/coolify-evaluate-4-3-21-resume.yml --extra-vars "@$(CONFIG)" --extra-vars "solo_vps_coolify_evaluation_target_id=$(COOLIFY_EVALUATION_TARGET_ID) solo_vps_coolify_evaluation_sentinel_url=$(COOLIFY_SENTINEL_URL) solo_vps_coolify_evaluation_confirm=$(COOLIFY_EVALUATION_CONFIRM) solo_vps_coolify_upgrade_resume_confirm=$(COOLIFY_UPGRADE_RESUME_CONFIRM_REQUIRED)"

verify-coolify-4-3-21-candidate: check-local-files check-coolify-evaluation-args ## Read-only verification of Coolify 4.3.21 plus Sentinel on the disposable target
	@$(ANSIBLE_PLAYBOOK) -i "$(INVENTORY)" $(PLAYBOOK_DIR)/verify-coolify-4-3-21-candidate.yml --extra-vars "@$(CONFIG)" --extra-vars "solo_vps_coolify_evaluation_target_id=$(COOLIFY_EVALUATION_TARGET_ID) solo_vps_coolify_evaluation_sentinel_url=$(COOLIFY_SENTINEL_URL)"

validate-external-uptime: ## Validate the CRIT-015 provider-neutral external outage/alert contract without network access
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(EXTERNAL_UPTIME_CONTRACT_VALIDATOR) .

test-external-uptime: ## Run local positive/negative tests for the CRIT-015 external uptime/evidence boundary
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_external_uptime tests.test_external_uptime_contract

uptime-plan: ## Render the reviewed external HTTPS monitor policy without network/provider writes
	@test -n "$(UPTIME_HEALTH_URL)" || { printf '%s\n' 'ERROR: set UPTIME_HEALTH_URL to the public HTTPS application health endpoint.' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(EXTERNAL_UPTIME) plan \
		--health-url "$(UPTIME_HEALTH_URL)" \
		--interval-seconds "$(UPTIME_INTERVAL_SECONDS)" \
		--timeout-seconds "$(UPTIME_TIMEOUT_SECONDS)"

uptime-evidence: ## Record one sanitized external outage/recovery exercise summary outside the source tree
	@test -n "$(UPTIME_HEALTH_URL)" || { printf '%s\n' 'ERROR: UPTIME_HEALTH_URL is required.' >&2; exit 2; }
	@test -n "$(UPTIME_PROOF_ID)" || { printf '%s\n' 'ERROR: UPTIME_PROOF_ID is required.' >&2; exit 2; }
	@test -n "$(UPTIME_EXERCISE_MODE)" || { printf '%s\n' 'ERROR: UPTIME_EXERCISE_MODE is required.' >&2; exit 2; }
	@test -n "$(UPTIME_NOTIFICATION_CHANNEL)" || { printf '%s\n' 'ERROR: UPTIME_NOTIFICATION_CHANNEL is required.' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(EXTERNAL_UPTIME) record \
		--health-url "$(UPTIME_HEALTH_URL)" \
		--interval-seconds "$(UPTIME_INTERVAL_SECONDS)" \
		--timeout-seconds "$(UPTIME_TIMEOUT_SECONDS)" \
		--proof-id "$(UPTIME_PROOF_ID)" \
		--exercise-mode "$(UPTIME_EXERCISE_MODE)" \
		--notification-channel "$(UPTIME_NOTIFICATION_CHANNEL)" \
		--provider-artifact-sha256 "$(UPTIME_PROVIDER_ARTIFACT_SHA256)" \
		--provider-artifact-review-confirm "$(UPTIME_PROVIDER_ARTIFACT_REVIEW_CONFIRM)" \
		--notification-test-received-at "$(UPTIME_NOTIFICATION_TEST_RECEIVED_AT)" \
		--outage-started-at "$(UPTIME_OUTAGE_STARTED_AT)" \
		--alert-received-at "$(UPTIME_ALERT_RECEIVED_AT)" \
		--service-restored-at "$(UPTIME_SERVICE_RESTORED_AT)" \
		--recovery-received-at "$(UPTIME_RECOVERY_RECEIVED_AT)" \
		--confirm "$(UPTIME_EVIDENCE_CONFIRM)" \
		--evidence-dir "$(UPTIME_EVIDENCE_DIR)"

validate-ai-coding: ## Validate repository-local Codex agents, skills, and orchestration defaults
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(AI_CODING_VALIDATOR) .

validate-documentation-governance: ## Validate CRIT-008/009/018/019 documentation truth/size/optionality boundaries
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(DOCUMENTATION_GOVERNANCE_VALIDATOR) .

test-documentation-governance: ## Run documentation-governance regression tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_documentation_governance

validate-operator-surface: ## Validate the CRIT-006/CRIT-007 primary lifecycle/help contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(OPERATOR_SURFACE_VALIDATOR) .

test-operator-surface: ## Run positive/negative tests for the primary operator command surface
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_operator_surface

deps: ## Explicitly install pinned Ansible collection dependencies into the persistent controller path
	@test -x "$(ANSIBLE_GALAXY)" || { printf '%s\n' 'ERROR: persistent ansible-galaxy is unavailable; run: make qa-tools' >&2; exit 127; }
	@ANSIBLE_COLLECTIONS_PATH="$(ANSIBLE_COLLECTIONS_PATH)" $(ANSIBLE_GALAXY) collection install -r $(ANSIBLE_REQUIREMENTS) -p "$(ANSIBLE_COLLECTIONS_PATH)"

check-ansible-deps: ## Confirm required Ansible collection modules are already installed
	@command -v "$(ANSIBLE_DOC)" >/dev/null 2>&1 || { printf '%s\n' 'ERROR: persistent ansible-doc is unavailable; run: make qa-tools' >&2; exit 127; }
	@$(ANSIBLE_DOC) -t module community.general.ufw >/dev/null 2>&1 || { \
		printf '%s\n' 'ERROR: required Ansible collection module community.general.ufw is unavailable.' 'Run: make deps' >&2; \
		exit 2; \
	}

validate: validate-ai-coding validate-platform-lifecycle test-platform-lifecycle validate-docs-i18n validate-documentation-governance test-documentation-governance validate-operator-surface test-operator-surface validate-application-migration-contract test-application-migration-contract validate-hosted-ci-contract test-hosted-ci-contract validate-disposable-clean-target test-disposable-clean-target validate-disaster-recovery test-disaster-recovery validate-state-layout test-state-layout test-inventory-config validate-yaml validate-firewall-contract test-firewall-contract validate-docker-contract test-docker-contract validate-onboarding-contract test-onboarding-contract validate-example-config validate-coolify-contract test-coolify-install-backend validate-example-app test-example-app validate-ci-template test-ci-template test-coolify-image-handoff test-coolify-deploy-api test-ci-deploy-transport validate-dependency-hygiene validate-secrets-policy test-sops-policy validate-secrets-toolchain test-secrets-toolchain validate-workstation-secrets test-workstation-secrets validate-public-product-hygiene test-public-product-hygiene validate-backup-tooling validate-backup-credentials test-backup-credentials validate-backup-policy test-backup-policy validate-backup-runtime test-backup-runtime validate-database-backup-contract test-database-backup-contract validate-database-backup-runtime test-database-backup-runtime test-doctor-platform validate-verify-contract test-verify-contract validate-audit-contract test-audit-contract validate-ops-visibility test-ops-visibility validate-observability-tooling test-observability-tooling validate-observability-credentials test-observability-credentials validate-metrics-credentials test-metrics-credentials validate-metrics-runtime test-metrics-runtime validate-observability-log-drain test-observability-log-drain validate-observability-runtime test-observability-runtime validate-qa-contract test-qa-contract validate-readme-contract test-readme-contract validate-architecture-docs test-architecture-docs validate-community-policy test-community-policy validate-upgrade-guide test-upgrade-guide validate-release-process test-release-process validate-external-uptime test-external-uptime ## Run static/local checks available without contacting a server
	@if [ -f "$(QA_READY_MARKER)" ]; then \
		$(MAKE) --no-print-directory qa-static; \
	elif command -v "$(ANSIBLE_PLAYBOOK)" >/dev/null 2>&1; then \
		$(MAKE) --no-print-directory ansible-syntax; \
	else \
		printf '%s\n' 'SKIP Ansible QA: run make qa-tools to install the pinned persistent toolchain.'; \
	fi


validate-state-layout: ## Validate that generated controller/operator state stays outside the Git checkout
	@$(PYTHON) $(STATE_LAYOUT_VALIDATOR) .

test-state-layout: ## Run source/state-boundary regression tests
	@$(PYTHON) -m unittest tests.test_state_layout

test-inventory-config: ## Run bootstrap/admin inventory synchronization regression tests
	@$(PYTHON) -m unittest tests.test_inventory_config

validate-firewall-contract: ## Validate M5 UFW status parsing and pre-assert evidence without contacting a server
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(FIREWALL_CONTRACT_VALIDATOR) .

test-firewall-contract: ## Run positive/negative tests for M5 UFW status parsing
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_firewall_contract

validate-docker-contract: ## Validate M7 repository refresh/candidate/install sequencing without contacting a server
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(DOCKER_CONTRACT_VALIDATOR) .

test-docker-contract: ## Run positive/negative tests for M7 repository installation sequencing
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_docker_contract

validate-onboarding-contract: ## Validate guided first-run setup/access/defaults without contacting a server
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(ONBOARDING_CONTRACT_VALIDATOR) .

test-onboarding-contract: ## Run positive/negative tests for first-run onboarding automation
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_onboarding_contract

validate-qa-contract: ## Validate pinned M20 controller QA dependencies and lint sequencing without network access
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(QA_CONTRACT_VALIDATOR) .

test-qa-contract: ## Run local positive/negative tests for the M20 controller QA contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_qa_contract

validate-readme-contract: ## Validate the M26 public README/Quick Start contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(README_CONTRACT_VALIDATOR) .

test-readme-contract: ## Run local positive/negative tests for the M26 README contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_readme_contract

validate-architecture-docs: ## Validate M27 architecture boundaries, ADR statuses, and source links
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(ARCHITECTURE_DOCS_VALIDATOR) .

test-architecture-docs: ## Run local M27 architecture-documentation drift tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_architecture_docs

validate-community-policy: ## Validate M28 security/contribution policy and selected Apache-2.0 license
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(COMMUNITY_POLICY_VALIDATOR) .

test-community-policy: ## Run local M28 community-policy positive/negative tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_community_policy

validate-upgrade-guide: ## Validate M29 upgrade/recovery guidance against current project sources
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(UPGRADE_GUIDE_VALIDATOR) .

test-upgrade-guide: ## Run local M29 upgrade-guide positive/negative drift tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_upgrade_guide


validate-hosted-ci-contract: ## Validate the public GitHub-hosted repository fast CI gate without contacting GitHub
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(HOSTED_CI_CONTRACT_VALIDATOR) .

test-hosted-ci-contract: ## Run positive/negative tests for the hosted repository CI contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_hosted_ci_contract

validate-disposable-clean-target: ## Validate the CRIT-004 provider-neutral disposable clean-target harness without contacting a server
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(DISPOSABLE_CLEAN_TARGET_CONTRACT_VALIDATOR) .

test-disposable-clean-target: ## Run local positive/negative tests for the disposable clean-target safety/evidence contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_disposable_clean_target tests.test_disposable_clean_target_contract

prove-disposable-clean-target: validate-disposable-clean-target test-disposable-clean-target
	@test -n "$(DISPOSABLE_TARGET_HOST)" || { printf '%s\n' 'ERROR: DISPOSABLE_TARGET_HOST is required.' >&2; exit 2; }
	@test -n "$(DISPOSABLE_TARGET_BOOTSTRAP_IDENTITY_FILE)" || { printf '%s\n' 'ERROR: DISPOSABLE_TARGET_BOOTSTRAP_IDENTITY_FILE is required.' >&2; exit 2; }
	@test -n "$(DISPOSABLE_TARGET_HOST_KEY_SHA256)" || { printf '%s\n' 'ERROR: DISPOSABLE_TARGET_HOST_KEY_SHA256 is required.' >&2; exit 2; }
	@test -n "$(DISPOSABLE_TARGET_ID)" || { printf '%s\n' 'ERROR: DISPOSABLE_TARGET_ID is required.' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(DISPOSABLE_CLEAN_TARGET_PROOF) --root . \
		--target "$(DISPOSABLE_TARGET_HOST)" \
		--bootstrap-user "$(DISPOSABLE_TARGET_BOOTSTRAP_USER)" \
		--bootstrap-identity "$(DISPOSABLE_TARGET_BOOTSTRAP_IDENTITY_FILE)" \
		--admin-user "$(DISPOSABLE_TARGET_ADMIN_USER)" \
		--target-id "$(DISPOSABLE_TARGET_ID)" \
		--host-key-sha256 "$(DISPOSABLE_TARGET_HOST_KEY_SHA256)" \
		--confirm "$(DISPOSABLE_TARGET_CONFIRM)" \
		--provider-recovery-confirm "$(DISPOSABLE_TARGET_PROVIDER_RECOVERY_CONFIRM)" \
		--evidence-dir "$(DISPOSABLE_TARGET_EVIDENCE_DIR)"

ci-fast-source: validate-ai-coding validate-platform-lifecycle test-platform-lifecycle validate-documentation-governance test-documentation-governance validate-operator-surface test-operator-surface validate-application-migration-contract test-application-migration-contract validate-hosted-ci-contract test-hosted-ci-contract validate-disposable-clean-target test-disposable-clean-target validate-disaster-recovery test-disaster-recovery validate-backup-runtime test-backup-runtime validate-metrics-credentials test-metrics-credentials validate-metrics-runtime test-metrics-runtime validate-backup-policy test-backup-policy validate-database-backup-contract test-database-backup-contract validate-database-backup-runtime test-database-backup-runtime validate-state-layout test-state-layout validate-yaml validate-onboarding-contract test-onboarding-contract validate-coolify-contract test-coolify-install-backend validate-ci-template test-ci-template test-coolify-deploy-api validate-public-product-hygiene test-public-product-hygiene validate-qa-contract test-qa-contract validate-readme-contract test-readme-contract validate-architecture-docs test-architecture-docs validate-release-process test-release-process validate-external-uptime test-external-uptime ## Run the bounded source-only part of the public hosted CI gate

ci-fast: ci-fast-source qa-tools qa-static ## Run the full public hosted CI fast gate, including the pinned real Ansible QA layer

validate-release-process: ## Validate the M30 PRE-ALPHA release-process and dry-run source contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(RELEASE_PROCESS_VALIDATOR) .

test-release-process: ## Run local M30 release-process positive/negative tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_release_process

release-dry-run: validate ## Check a candidate PRE-ALPHA release without creating a tag, release, upload, or external write
	@test -n "$(RELEASE_VERSION)" || { printf '%s\n' 'ERROR: RELEASE_VERSION is required, e.g. make release-dry-run RELEASE_VERSION=v0.1.0' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(RELEASE_DRY_RUN) --root . --version "$(RELEASE_VERSION)"
	@$(MAKE) --no-print-directory qa-static
	@printf '%s\n' 'PASS release dry run: source snapshot + pinned real QA gates passed; no release actions were performed.'

.PHONY: runtime-tools
runtime-tools: controller-check ## Install/reuse the pinned Ansible runtime without developer lint/test tools
	@bash scripts/runtime_tools.sh "$(PYTHON)" "$(QA_VENV)" "$(QA_COLLECTIONS_DIR)"

qa-tools: controller-check ## Install the additional pinned developer/release QA tools
	@$(PYTHON) -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 12) else "ERROR: Python 3.12+ is required for the pinned controller toolchain.")'
	@rm -f "$(QA_READY_MARKER)"
	@$(PYTHON) -m venv $(QA_VENV)
	@$(QA_PYTHON) -m pip install --disable-pip-version-check --no-cache-dir -r tools/qa-requirements.txt
	@ANSIBLE_COLLECTIONS_PATH="$(abspath $(QA_COLLECTIONS_DIR))" $(QA_ANSIBLE_GALAXY) collection install -r ansible/requirements.yml -p "$(abspath $(QA_COLLECTIONS_DIR))"
	@touch "$(QA_READY_MARKER)"

qa-check: ## Verify exact persistent QA tool and Ansible collection versions without network access
	@test -f "$(QA_READY_MARKER)" || { printf '%s\n' 'ERROR: M20 QA environment is incomplete or missing; rerun: make qa-tools' >&2; exit 2; }
	@$(QA_PYTHON) -c 'from importlib.metadata import version; expected={"ansible-core":"2.21.3","ansible-lint":"26.6.0","yamllint":"1.38.0"}; actual={k:version(k) for k in expected}; assert actual == expected, f"QA package drift: expected {expected}, found {actual}"; print(f"PASS QA Python packages: {actual}")'
	@ANSIBLE_COLLECTIONS_PATH="$(abspath $(QA_COLLECTIONS_DIR))" $(QA_ANSIBLE_GALAXY) collection list community.general | awk '$$1 == "community.general" && $$2 == "13.0.1" { found=1 } END { if (!found) exit 1 }' || { printf '%s\n' 'ERROR: pinned community.general 13.0.1 is unavailable in the M20 QA collection path; rerun: make qa-tools' >&2; exit 2; }
	@ANSIBLE_COLLECTIONS_PATH="$(abspath $(QA_COLLECTIONS_DIR))" $(QA_ANSIBLE_DOC) -t module community.general.ufw >/dev/null

qa-static: qa-check ## Run yamllint, real Ansible syntax checks, and ansible-lint using only the pinned local QA environment
	@$(QA_YAMLLINT) -c .yamllint $(QA_YAML_PATHS)
	@$(QA_PYTHON) -m unittest tests.test_docker_version_templates tests.test_firewall_listener_templates
	@ANSIBLE_COLLECTIONS_PATH="$(abspath $(QA_COLLECTIONS_DIR))" $(MAKE) --no-print-directory ansible-syntax ANSIBLE_PLAYBOOK="$(abspath $(QA_ANSIBLE_PLAYBOOK))" ANSIBLE_DOC="$(abspath $(QA_ANSIBLE_DOC))"
	@ANSIBLE_COLLECTIONS_PATH="$(abspath $(QA_COLLECTIONS_DIR))" $(QA_ANSIBLE_LINT) --offline ansible/

validate-yaml: ## Parse project YAML files with Python/PyYAML
	@$(PYTHON) -c 'import pathlib, sys, yaml; files=sys.argv[1:]; [yaml.safe_load(pathlib.Path(p).read_text(encoding="utf-8")) for p in files]; print(f"PASS YAML parse: {len(files)} files")' $(YAML_FILES)

validate-example-config: ## Validate the public config example against the current contract
	@$(PYTHON) $(CONFIG_VALIDATOR) $(EXAMPLE_CONFIG)

validate-coolify-contract: ## Validate the project-pinned M9 release, install, and exposure contract
	@$(PYTHON) $(COOLIFY_CONTRACT_VALIDATOR) $(COOLIFY_DEFAULTS)
	@$(PYTHON) $(COOLIFY_COMPOSE_OVERRIDE_VALIDATOR) $(COOLIFY_COMPOSE_OVERRIDE)
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(COOLIFY_INSTALL_BACKEND_VALIDATOR) .

test-coolify-install-backend: ## Run local positive/negative tests for the M9 installation safety contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_coolify_install_backend tests.test_coolify_env tests.test_coolify_proxy

validate-example-app: ## Validate the M10 sample application container contract without Docker
	@$(PYTHON) $(EXAMPLE_APP_VALIDATOR) $(EXAMPLE_APP_DIR)

test-example-app: ## Run dependency-free local HTTP tests for the M10 sample application
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s $(EXAMPLE_APP_DIR) -p 'test_*.py'

validate-application-migration-contract: ## Validate CRIT-016 app-owned migration preflight and image-only rollback boundary
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(APPLICATION_MIGRATION_CONTRACT_VALIDATOR) .

test-application-migration-contract: ## Run CRIT-016 migration-safety positive/negative regression tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_application_migration_contract

validate-ci-template: ## Validate the M11 GitHub Actions/GHCR template without GitHub or registry access
	@$(PYTHON) $(CI_TEMPLATE_VALIDATOR) $(CI_TEMPLATE)

test-ci-template: ## Run workflow regressions plus the portable consumer deployment-helper suite
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_github_actions_template tests.test_app_starter tests.test_release_revision
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest discover -s templates/github-actions/tests -p 'test_*.py'

validate-coolify-image-handoff: ## Validate one exact immutable GHCR image reference before a Coolify Docker Image handoff
	@test -n "$(COOLIFY_IMAGE_REF)" || { printf '%s\n' 'ERROR: COOLIFY_IMAGE_REF is required, e.g. ghcr.io/owner/app@sha256:<64hex>' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(COOLIFY_IMAGE_HANDOFF_VALIDATOR) "$(COOLIFY_IMAGE_REF)"

test-coolify-image-handoff: ## Run positive/negative regression tests for the immutable GHCR -> Coolify image-reference contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_coolify_image_handoff

test-coolify-deploy-api: ## Run offline regression tests for the loopback-only Coolify immutable deploy API helper
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_coolify_deploy_api tests.test_coolify_deploy_rollback_proof

test-ci-deploy-transport: ## Run offline regression tests for the restricted GitHub-hosted runner SSH tunnel contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_ci_deploy_transport

plan-ci-deploy-transport: ## Print the restricted SSH tunnel/sshd contract without host or GitHub mutation
	@test -n "$(CI_DEPLOY_SERVER_HOST)" || { printf '%s\n' 'ERROR: CI_DEPLOY_SERVER_HOST is required.' >&2; exit 2; }
	@test -n "$(CI_DEPLOY_PUBLIC_KEY_FILE)" || { printf '%s\n' 'ERROR: CI_DEPLOY_PUBLIC_KEY_FILE is required and must point to one Ed25519 public key.' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(CI_DEPLOY_TRANSPORT) --server-host "$(CI_DEPLOY_SERVER_HOST)" --public-key-file "$(CI_DEPLOY_PUBLIC_KEY_FILE)"

plan-coolify-deploy-api: ## Print the exact loopback Coolify API mutation plan without credentials or network access
	@test -n "$(COOLIFY_RESOURCE_UUID)" || { printf '%s\n' 'ERROR: COOLIFY_RESOURCE_UUID is required.' >&2; exit 2; }
	@test -n "$(COOLIFY_IMAGE_REF)" || { printf '%s\n' 'ERROR: COOLIFY_IMAGE_REF is required.' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(COOLIFY_DEPLOY_API) --base-url "$(COOLIFY_API_BASE_URL)" --resource-uuid "$(COOLIFY_RESOURCE_UUID)" --image-ref "$(COOLIFY_IMAGE_REF)"

check-coolify-deploy-api: ## Read-only validate the isolated Docker Image resource through loopback Coolify API
	@test -n "$(COOLIFY_RESOURCE_UUID)" || { printf '%s\n' 'ERROR: COOLIFY_RESOURCE_UUID is required.' >&2; exit 2; }
	@test -n "$(COOLIFY_IMAGE_REF)" || { printf '%s\n' 'ERROR: COOLIFY_IMAGE_REF is required.' >&2; exit 2; }
	@test -n "$$COOLIFY_API_TOKEN" || { printf '%s\n' 'ERROR: COOLIFY_API_TOKEN must be exported for API check; do not put it on the command line.' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(COOLIFY_DEPLOY_API) --base-url "$(COOLIFY_API_BASE_URL)" --resource-uuid "$(COOLIFY_RESOURCE_UUID)" --image-ref "$(COOLIFY_IMAGE_REF)" --check

check-coolify-api-deploy-confirm: ## Refuse loopback Coolify API mutation without explicit operator confirmation
	@test "$(COOLIFY_API_DEPLOY_CONFIRM)" = "$(COOLIFY_API_DEPLOY_CONFIRM_REQUIRED)" || { \
		printf '%s\n' 'ERROR: Coolify API deployment is an explicit application mutation.' \
		  'Re-run with COOLIFY_API_DEPLOY_CONFIRM=$(COOLIFY_API_DEPLOY_CONFIRM_REQUIRED)' >&2; \
		exit 2; \
	}

deploy-coolify-image-api: check-coolify-api-deploy-confirm ## Deploy one exact immutable GHCR digest through loopback Coolify API
	@test -n "$(COOLIFY_RESOURCE_UUID)" || { printf '%s\n' 'ERROR: COOLIFY_RESOURCE_UUID is required.' >&2; exit 2; }
	@test -n "$(COOLIFY_IMAGE_REF)" || { printf '%s\n' 'ERROR: COOLIFY_IMAGE_REF is required.' >&2; exit 2; }
	@test -n "$$COOLIFY_API_TOKEN" || { printf '%s\n' 'ERROR: COOLIFY_API_TOKEN must be exported for API deployment; do not put it on the command line.' >&2; exit 2; }
	@COOLIFY_API_DEPLOY_CONFIRM="$(COOLIFY_API_DEPLOY_CONFIRM)" PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(COOLIFY_DEPLOY_API) --base-url "$(COOLIFY_API_BASE_URL)" --resource-uuid "$(COOLIFY_RESOURCE_UUID)" --image-ref "$(COOLIFY_IMAGE_REF)" --apply

# Maintainer-only destructive proof. Intentionally hidden from `make help` because
# it starts one failed deployment before requiring automatic rollback to known-good.
prove-coolify-deploy-rollback:
	@test -n "$(COOLIFY_RESOURCE_UUID)" || { printf '%s\n' 'ERROR: COOLIFY_RESOURCE_UUID is required.' >&2; exit 2; }
	@test -n "$$COOLIFY_API_TOKEN" || { printf '%s\n' 'ERROR: COOLIFY_API_TOKEN must be exported for rollback proof; do not put it on the command line.' >&2; exit 2; }
	@test "$(COOLIFY_ROLLBACK_PROOF_CONFIRM)" = "$(COOLIFY_ROLLBACK_PROOF_CONFIRM_REQUIRED)" || { \
		printf '%s\n' 'ERROR: rollback proof deliberately starts a failed deployment.' \
		  'Re-run with COOLIFY_ROLLBACK_PROOF_CONFIRM=$(COOLIFY_ROLLBACK_PROOF_CONFIRM_REQUIRED)' >&2; \
		exit 2; \
	}
	@COOLIFY_ROLLBACK_PROOF_CONFIRM="$(COOLIFY_ROLLBACK_PROOF_CONFIRM)" PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(COOLIFY_ROLLBACK_PROOF) --base-url "$(COOLIFY_API_BASE_URL)" --resource-uuid "$(COOLIFY_RESOURCE_UUID)" --allow-domain

validate-dependency-hygiene: ## Validate M12 dependency/image update policy without GitHub access
	@$(PYTHON) $(DEPENDENCY_HYGIENE_VALIDATOR) $(DEPENDABOT_CONFIG) $(EXAMPLE_APP_DIR)/Dockerfile $(ANSIBLE_REQUIREMENTS)

validate-secrets-policy: ## Validate M13 repository SOPS/age policy without reading any private identity
	@$(PYTHON) $(SOPS_POLICY_VALIDATOR) . --policy "$(SOPS_POLICY)" --recipient-file "$(SOPS_RECIPIENT_FILE)"

test-sops-policy: ## Run local M13 public-policy initializer tests with public test recipients only
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_sops_policy

validate-secrets-toolchain: ## Validate pinned M13 SOPS/age controller artifacts without network access
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(SECRETS_TOOLCHAIN) validate --manifest $(SECRETS_TOOLCHAIN_MANIFEST)

test-secrets-toolchain: ## Run offline M13 SOPS/age toolchain and disposable-roundtrip helper tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_secrets_toolchain tests.test_sops_roundtrip_helper

validate-workstation-secrets: ## Validate the simple one-workstation + one-VPS M13 contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(WORKSTATION_SECRETS_VALIDATOR) .

test-workstation-secrets: ## Run regression tests for the Windows/Linux workstation M13 contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_workstation_secrets_contract

validate-public-product-hygiene: ## Reject operator-specific values/evidence from public Solo VPS source
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(PUBLIC_PRODUCT_HYGIENE_VALIDATOR) .

test-public-product-hygiene: ## Run positive/negative public-source hygiene regression tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_public_product_hygiene

verify-vps-secrets-boundary: validate-secrets-policy ## Read-only M13 proof that production age private identity is absent from this VPS
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(VPS_SECRETS_BOUNDARY_VERIFIER) $(if $(strip $(VPS_SECRETS_ADMIN_HOME)),--home "$(VPS_SECRETS_ADMIN_HOME)",)

backup-secrets-init: validate-secrets-policy check-secrets-tools ## Workstation: create external SOPS-encrypted M14 backup credentials without plaintext files
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(BACKUP_SECRET_BUNDLE) init --root . --manifest $(SECRETS_TOOLCHAIN_MANIFEST) --policy "$(SOPS_POLICY)" --encrypted "$(BACKUP_SECRET_FILE)" --key-file "$(AGE_KEY_FILE)"

backup-secrets-check: validate-secrets-policy check-secrets-tools ## Workstation: decrypt/validate the external M14 backup bundle without printing values
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(BACKUP_SECRET_BUNDLE) check --root . --manifest $(SECRETS_TOOLCHAIN_MANIFEST) --policy "$(SOPS_POLICY)" --encrypted "$(BACKUP_SECRET_FILE)" --key-file "$(AGE_KEY_FILE)"

backup-secrets-push: validate-secrets-policy check-secrets-tools ## Workstation: decrypt in memory and deliver only runtime backup credentials to the VPS over SSH stdin
	@test -n "$(BACKUP_VPS_HOST)" || { printf '%s\n' 'ERROR: set BACKUP_VPS_HOST to the VPS SSH host/IP.' >&2; exit 2; }
	@test -n "$(BACKUP_VPS_USER)" || { printf '%s\n' 'ERROR: set BACKUP_VPS_USER to the managed admin SSH user.' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(BACKUP_SECRET_BUNDLE) push --root . --manifest $(SECRETS_TOOLCHAIN_MANIFEST) --policy "$(SOPS_POLICY)" --encrypted "$(BACKUP_SECRET_FILE)" --key-file "$(AGE_KEY_FILE)" --ssh "$(SSH)" --vps-host "$(BACKUP_VPS_HOST)" --vps-user "$(BACKUP_VPS_USER)" --remote-project '$(BACKUP_REMOTE_PROJECT)' $(if $(strip $(BACKUP_SSH_IDENTITY_FILE)),--identity-file "$(BACKUP_SSH_IDENTITY_FILE)",)

verify-backup-credentials: ## VPS: read-only root verification of the materialized M14 runtime credential file
	@if [ "$$(id -u)" -eq 0 ]; then \
		PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(BACKUP_CREDENTIAL_INSTALLER) verify; \
	else \
		sudo -n env PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(BACKUP_CREDENTIAL_INSTALLER) verify; \
	fi


secrets-tools: ## Download checksum-verified pinned SOPS/age binaries into the user cache (Linux amd64/arm64)
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(SECRETS_TOOLCHAIN) install --manifest $(SECRETS_TOOLCHAIN_MANIFEST)

secrets-tools-offline: ## Import exact pinned SOPS/age release files from SECRETS_ARTIFACT_DIR without network access
	@test -n "$(SECRETS_ARTIFACT_DIR)" || { printf '%s\n' 'ERROR: set SECRETS_ARTIFACT_DIR to a directory containing the exact pinned release filenames.' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(SECRETS_TOOLCHAIN) install --manifest $(SECRETS_TOOLCHAIN_MANIFEST) --artifact-dir "$(SECRETS_ARTIFACT_DIR)"

check-secrets-tools: ## Verify the cached pinned SOPS/age controller binaries without downloading
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(SECRETS_TOOLCHAIN) check --manifest $(SECRETS_TOOLCHAIN_MANIFEST)

test-sops-roundtrip: check-secrets-tools ## Create a disposable age identity and prove local SOPS encrypt/decrypt, then delete it
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(SOPS_ROUNDTRIP) --manifest $(SECRETS_TOOLCHAIN_MANIFEST)

secrets-crypto-proof: validate-secrets-toolchain test-secrets-toolchain ## Install exact pinned SOPS/age tools and run the disposable crypto proof
	@$(MAKE) --no-print-directory secrets-tools
	@$(MAKE) --no-print-directory check-secrets-tools
	@$(MAKE) --no-print-directory test-sops-roundtrip

secrets-crypto-proof-offline: validate-secrets-toolchain test-secrets-toolchain ## Import exact pinned artifacts, then run the same disposable crypto proof
	@test -n "$(SECRETS_ARTIFACT_DIR)" || { printf '%s\n' 'ERROR: set SECRETS_ARTIFACT_DIR to a directory containing the exact pinned release filenames.' >&2; exit 2; }
	@$(MAKE) --no-print-directory secrets-tools-offline SECRETS_ARTIFACT_DIR="$(SECRETS_ARTIFACT_DIR)"
	@$(MAKE) --no-print-directory check-secrets-tools
	@$(MAKE) --no-print-directory test-sops-roundtrip

validate-backup-tooling: ## Validate the source-only M14 pinned restic host-tooling contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(BACKUP_TOOLING_VALIDATOR) $(BACKUP_ROLE_DIR)

validate-backup-credentials: ## Validate the source-only M14 workstation-to-VPS backup credential contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(BACKUP_CREDENTIALS_VALIDATOR) .

test-backup-credentials: ## Run M14 credential schema/install/contract regression tests without real secrets or SSH
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_backup_credentials tests.test_backup_secret_bundle tests.test_backup_credentials_contract

validate-backup-policy: ## Validate M14 non-secret repository/scope/retention policy using the public example
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(BACKUP_POLICY_VALIDATOR) $(EXAMPLE_CONFIG) $(BACKUP_DEFAULTS) --allow-documentation-endpoint

test-backup-policy: ## Run local positive/negative tests for the M14 non-secret backup policy
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_backup_policy

validate-backup-runtime: ## Validate the source-only M14 operational restic runtime/schedule contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(BACKUP_RUNTIME_VALIDATOR) .

test-backup-runtime: ## Run local M14 repository/backup/freshness/retention/restore runtime regression tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_restic_runtime tests.test_backup_runtime_contract

validate-database-backup-contract: ## Validate the source-only accepted M15 PostgreSQL backup responsibility contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(DATABASE_BACKUP_CONTRACT_VALIDATOR) $(DATABASE_BACKUP_CONTRACT) $(DATABASE_BACKUP_ADR) $(BACKUP_DEFAULTS) --root .

test-database-backup-contract: ## Run local positive/negative tests for the M15 database-backup boundary
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_database_backup_contract

validate-database-backup-runtime: ## Validate the source-only M15 Coolify schedule + disposable restore runtime contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(DATABASE_BACKUP_RUNTIME_VALIDATOR) .

test-database-backup-runtime: ## Run offline M15 Coolify backup API and disposable restore regression tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_coolify_database_backup_api tests.test_postgres_restore_exercise tests.test_database_backup_runtime_contract

validate-disaster-recovery: ## Validate M16 lost-VPS recovery inputs, staging and restore boundaries
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(DISASTER_RECOVERY_CONTRACT_VALIDATOR) .

test-disaster-recovery: ## Run M16 recovery-kit, Coolify-instance restore and contract regressions
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_disaster_recovery tests.test_disaster_recovery_contract

recovery-kit-export: ## Export a private recovery kit; copy and verify it off the VPS before claiming DR readiness
	@test -n "$(RECOVERY_KIT_OUTPUT)" || { printf '%s\n' 'ERROR: set RECOVERY_KIT_OUTPUT to a new protected archive path.' >&2; exit 2; }
	@$(PYTHON) $(RECOVERY_KIT) export --data-dir "$(SOLO_VPS_DATA_DIR)" --output "$(RECOVERY_KIT_OUTPUT)" --source-revision "$(RECOVERY_SOURCE_REVISION)"

recovery-kit-verify: ## Verify one copied recovery kit without decrypting secrets
	@test -n "$(RECOVERY_KIT_OUTPUT)" || { printf '%s\n' 'ERROR: set RECOVERY_KIT_OUTPUT to the copied recovery kit path.' >&2; exit 2; }
	@$(PYTHON) $(RECOVERY_KIT) verify --output "$(RECOVERY_KIT_OUTPUT)"

recovery-kit-extract: ## Extract verified recovery inputs into the external data root without overwriting existing files
	@test -n "$(RECOVERY_KIT_OUTPUT)" || { printf '%s\n' 'ERROR: set RECOVERY_KIT_OUTPUT to the copied recovery kit path.' >&2; exit 2; }
	@$(PYTHON) $(RECOVERY_KIT) extract --output "$(RECOVERY_KIT_OUTPUT)" --data-dir "$(SOLO_VPS_DATA_DIR)"

coolify-instance-restore-inspect: ## Inspect a private Coolify instance database dump without restoring it
	@test -n "$(COOLIFY_INSTANCE_BACKUP_ARCHIVE)" || { printf '%s\n' 'ERROR: set COOLIFY_INSTANCE_BACKUP_ARCHIVE to the downloaded Coolify instance .dmp.' >&2; exit 2; }
	@$(PYTHON) $(COOLIFY_INSTANCE_RESTORE) inspect --archive "$(COOLIFY_INSTANCE_BACKUP_ARCHIVE)"

coolify-instance-restore-plan: ## Read-only replacement-VPS restore plan using staged restic material and fresh pinned Coolify
	@test -n "$(COOLIFY_INSTANCE_BACKUP_ARCHIVE)" -a -n "$(RECOVERY_STAGING_ROOT)" || { printf '%s\n' 'ERROR: set COOLIFY_INSTANCE_BACKUP_ARCHIVE and RECOVERY_STAGING_ROOT.' >&2; exit 2; }
	@$(PYTHON) $(COOLIFY_INSTANCE_RESTORE) plan --archive "$(COOLIFY_INSTANCE_BACKUP_ARCHIVE)" --recovery-root "$(RECOVERY_STAGING_ROOT)"

# Hidden destructive replacement-VPS target. Intentionally absent from normal help output.
coolify-instance-restore-apply:
	@test -n "$(COOLIFY_INSTANCE_BACKUP_ARCHIVE)" -a -n "$(RECOVERY_STAGING_ROOT)" -a -n "$(RECOVERY_TARGET_ID)" || { printf '%s\n' 'ERROR: archive, staged recovery root and target id are required.' >&2; exit 2; }
	@sudo -n env SOLO_VPS_DISASTER_RECOVERY_CONFIRM="$(RECOVERY_TARGET_CONFIRM)" $(PYTHON) $(COOLIFY_INSTANCE_RESTORE) restore --archive "$(COOLIFY_INSTANCE_BACKUP_ARCHIVE)" --recovery-root "$(RECOVERY_STAGING_ROOT)" --target-id "$(RECOVERY_TARGET_ID)"

check-database-backup-args:
	@test -n "$(DATABASE_BACKUP_DATABASE_UUID)" || { printf '%s\n' 'ERROR: DATABASE_BACKUP_DATABASE_UUID is required.' >&2; exit 2; }
	@test -n "$(DATABASE_BACKUP_S3_STORAGE_UUID)" || { printf '%s\n' 'ERROR: DATABASE_BACKUP_S3_STORAGE_UUID is required.' >&2; exit 2; }
	@if [ "$(DATABASE_BACKUP_DUMP_ALL)" != "true" ] && [ -z "$(DATABASE_BACKUP_DATABASES)" ]; then printf '%s\n' 'ERROR: set DATABASE_BACKUP_DATABASES or DATABASE_BACKUP_DUMP_ALL=true.' >&2; exit 2; fi

database-backup-plan: check-database-backup-args ## Print desired Coolify-owned PostgreSQL backup policy; no API token/request
	@$(PYTHON) $(DATABASE_BACKUP_API) plan --base-url "$(DATABASE_BACKUP_BASE_URL)" --database-uuid "$(DATABASE_BACKUP_DATABASE_UUID)" --s3-storage-uuid "$(DATABASE_BACKUP_S3_STORAGE_UUID)" --frequency "$(DATABASE_BACKUP_FREQUENCY)" --databases-to-backup "$(DATABASE_BACKUP_DATABASES)" --dump-all "$(DATABASE_BACKUP_DUMP_ALL)" --retention-amount-locally "$(DATABASE_BACKUP_RETENTION_AMOUNT_LOCALLY)" --retention-days-s3 "$(DATABASE_BACKUP_RETENTION_DAYS_S3)" --freshness-hours "$(DATABASE_BACKUP_FRESHNESS_HOURS)" --state-dir "$(DATABASE_BACKUP_STATE_DIR)"

database-backup-adopt: check-database-backup-args ## Coolify-read-only adoption of one existing matching backup schedule into external state
	@test -n "$(DATABASE_BACKUP_SCHEDULE_UUID)" || { printf '%s\n' 'ERROR: DATABASE_BACKUP_SCHEDULE_UUID is required for adoption.' >&2; exit 2; }
	@$(PYTHON) $(DATABASE_BACKUP_API) adopt --base-url "$(DATABASE_BACKUP_BASE_URL)" --database-uuid "$(DATABASE_BACKUP_DATABASE_UUID)" --s3-storage-uuid "$(DATABASE_BACKUP_S3_STORAGE_UUID)" --frequency "$(DATABASE_BACKUP_FREQUENCY)" --databases-to-backup "$(DATABASE_BACKUP_DATABASES)" --dump-all "$(DATABASE_BACKUP_DUMP_ALL)" --retention-amount-locally "$(DATABASE_BACKUP_RETENTION_AMOUNT_LOCALLY)" --retention-days-s3 "$(DATABASE_BACKUP_RETENTION_DAYS_S3)" --freshness-hours "$(DATABASE_BACKUP_FRESHNESS_HOURS)" --state-dir "$(DATABASE_BACKUP_STATE_DIR)" --backup-uuid "$(DATABASE_BACKUP_SCHEDULE_UUID)"

database-backup-configure: check-database-backup-args ## EXTERNAL WRITE: create/update only the explicitly managed Coolify PostgreSQL backup schedule
	@COOLIFY_DATABASE_BACKUP_CONFIRM="$(DATABASE_BACKUP_CONFIRM)" $(PYTHON) $(DATABASE_BACKUP_API) configure --base-url "$(DATABASE_BACKUP_BASE_URL)" --database-uuid "$(DATABASE_BACKUP_DATABASE_UUID)" --s3-storage-uuid "$(DATABASE_BACKUP_S3_STORAGE_UUID)" --frequency "$(DATABASE_BACKUP_FREQUENCY)" --databases-to-backup "$(DATABASE_BACKUP_DATABASES)" --dump-all "$(DATABASE_BACKUP_DUMP_ALL)" --retention-amount-locally "$(DATABASE_BACKUP_RETENTION_AMOUNT_LOCALLY)" --retention-days-s3 "$(DATABASE_BACKUP_RETENTION_DAYS_S3)" --freshness-hours "$(DATABASE_BACKUP_FRESHNESS_HOURS)" --state-dir "$(DATABASE_BACKUP_STATE_DIR)"

database-backup-trigger: check-database-backup-args ## EXTERNAL WRITE: trigger the managed Coolify backup and wait for a new successful execution
	@COOLIFY_DATABASE_BACKUP_CONFIRM="$(DATABASE_BACKUP_CONFIRM)" $(PYTHON) $(DATABASE_BACKUP_API) trigger --base-url "$(DATABASE_BACKUP_BASE_URL)" --database-uuid "$(DATABASE_BACKUP_DATABASE_UUID)" --s3-storage-uuid "$(DATABASE_BACKUP_S3_STORAGE_UUID)" --frequency "$(DATABASE_BACKUP_FREQUENCY)" --databases-to-backup "$(DATABASE_BACKUP_DATABASES)" --dump-all "$(DATABASE_BACKUP_DUMP_ALL)" --retention-amount-locally "$(DATABASE_BACKUP_RETENTION_AMOUNT_LOCALLY)" --retention-days-s3 "$(DATABASE_BACKUP_RETENTION_DAYS_S3)" --freshness-hours "$(DATABASE_BACKUP_FRESHNESS_HOURS)" --state-dir "$(DATABASE_BACKUP_STATE_DIR)"

database-backup-verify: check-database-backup-args ## Read-only Coolify schedule + latest execution freshness verification
	@$(PYTHON) $(DATABASE_BACKUP_API) verify --base-url "$(DATABASE_BACKUP_BASE_URL)" --database-uuid "$(DATABASE_BACKUP_DATABASE_UUID)" --s3-storage-uuid "$(DATABASE_BACKUP_S3_STORAGE_UUID)" --frequency "$(DATABASE_BACKUP_FREQUENCY)" --databases-to-backup "$(DATABASE_BACKUP_DATABASES)" --dump-all "$(DATABASE_BACKUP_DUMP_ALL)" --retention-amount-locally "$(DATABASE_BACKUP_RETENTION_AMOUNT_LOCALLY)" --retention-days-s3 "$(DATABASE_BACKUP_RETENTION_DAYS_S3)" --freshness-hours "$(DATABASE_BACKUP_FRESHNESS_HOURS)" --state-dir "$(DATABASE_BACKUP_STATE_DIR)"

database-restore-inspect: ## Inspect one downloaded custom-format database archive without restoring it
	@test -n "$(DATABASE_RESTORE_ARCHIVE)" || { printf '%s\n' 'ERROR: DATABASE_RESTORE_ARCHIVE is required.' >&2; exit 2; }
	@$(PYTHON) $(DATABASE_RESTORE_EXERCISE) inspect --archive "$(DATABASE_RESTORE_ARCHIVE)"

database-restore-exercise: ## DESTRUCTIVE TEST TARGET: restore only into an explicitly disposable empty database and verify one read-only query
	@test -n "$(DATABASE_RESTORE_ARCHIVE)" -a -n "$(DATABASE_RESTORE_DATABASE)" -a -n "$(DATABASE_RESTORE_PGPASS_FILE)" -a -n "$(DATABASE_RESTORE_VERIFY_QUERY)" || { printf '%s\n' 'ERROR: restore archive/database/pgpass/verify query are required.' >&2; exit 2; }
	@SOLO_VPS_DATABASE_RESTORE_CONFIRM="$(DATABASE_RESTORE_CONFIRM)" $(PYTHON) $(DATABASE_RESTORE_EXERCISE) restore --archive "$(DATABASE_RESTORE_ARCHIVE)" --host "$(DATABASE_RESTORE_HOST)" --port "$(DATABASE_RESTORE_PORT)" --user "$(DATABASE_RESTORE_USER)" --database "$(DATABASE_RESTORE_DATABASE)" --pgpass-file "$(DATABASE_RESTORE_PGPASS_FILE)" --verify-query "$(DATABASE_RESTORE_VERIFY_QUERY)" --expect "$(DATABASE_RESTORE_EXPECT)"

test-doctor-platform: ## Run local M17 capability-report tests without SSH or network access
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_doctor_platform

validate-verify-contract: ## Validate the M18 read-only verification orchestration contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(VERIFY_CONTRACT_VALIDATOR) .

test-verify-contract: ## Run local M18 verification-contract positive/negative tests
	@SOLO_VPS_TEST_ANSIBLE_PLAYBOOK="$(ANSIBLE_PLAYBOOK)" PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_verify_contract tests.test_managed_verification

validate-audit-contract: ## Validate the M19 read-only security-audit orchestration contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(AUDIT_CONTRACT_VALIDATOR) .

test-audit-contract: ## Run local M19 security-audit positive/negative contract tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_audit_contract

validate-ops-visibility: ## Validate M22 read-only status/logging UX without contacting a server
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(OPS_VISIBILITY_VALIDATOR) .

test-ops-visibility: ## Run local M22 operational-visibility positive/negative contract tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_ops_visibility_contract

validate-observability-tooling: ## Validate the pinned Grafana Alloy host-tooling contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(OBSERVABILITY_TOOLING_VALIDATOR) .

test-observability-tooling: ## Run local Alloy tooling positive/negative contract tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_observability_tooling

validate-observability-credentials: ## Validate the workstation-to-VPS Grafana Cloud credential boundary
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(OBSERVABILITY_CREDENTIALS_VALIDATOR) .

test-observability-credentials: ## Run observability credential schema/install/contract tests without real secrets or SSH
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_observability_credentials tests.test_observability_secret_bundle tests.test_observability_credentials_contract

validate-metrics-credentials: ## Validate the workstation-to-VPS Grafana Cloud Metrics credential boundary
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(METRICS_CREDENTIALS_VALIDATOR) .

test-metrics-credentials: ## Run metrics credential schema/install/contract tests without real secrets or SSH
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_metrics_credentials tests.test_metrics_credentials_contract

validate-metrics-runtime: ## Validate the source-only host metrics Alloy runtime contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(METRICS_RUNTIME_VALIDATOR) .

test-metrics-runtime: ## Run host metrics runtime contract regression tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_metrics_runtime

validate-observability-log-drain: ## Validate the historical Coolify-native Grafana Cloud log-drain contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(OBSERVABILITY_LOG_DRAIN_VALIDATOR) .

test-observability-log-drain: ## Run local Coolify/Grafana log-drain contract regression tests
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_observability_log_drain

validate-observability-runtime: ## Validate the non-root Alloy + restricted Docker API proxy runtime contract
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(OBSERVABILITY_RUNTIME_VALIDATOR) .

test-observability-runtime: ## Run positive/negative tests for the repository-managed retained-log runtime
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) -m unittest tests.test_observability_runtime

check-backup-policy: check-local-config ## Validate local non-secret backup metadata before any backup readiness SSH
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(BACKUP_POLICY_VALIDATOR) $(CONFIG) $(BACKUP_DEFAULTS)

check-backup-retention-confirm: ## Require explicit review before destructive restic forget --prune
	@test "$(BACKUP_RETENTION_CONFIRM)" = "$(BACKUP_RETENTION_CONFIRM_REQUIRED)" || { \
		printf '%s\n' \
			'ERROR: backup retention deletes snapshots and prunes unreferenced repository data.' \
			'Run: make backup-retention-plan' \
			'Then, only after reviewing the dry-run, rerun with:' \
			'  BACKUP_RETENTION_CONFIRM=$(BACKUP_RETENTION_CONFIRM_REQUIRED) make backup-retention-apply' >&2; \
		exit 2; \
	}

init-sops-policy: ## Initialize persistent public SOPS policy outside the Git checkout; never reads a private key
	@test -n "$(SOPS_AGE_RECIPIENT)" || { printf '%s\n' 'ERROR: set SOPS_AGE_RECIPIENT=age1... (public recipient only).' >&2; exit 2; }
	@$(PYTHON) $(SOPS_POLICY_INIT) --policy "$(SOPS_POLICY)" --recipient-file "$(SOPS_RECIPIENT_FILE)" --recipient "$(SOPS_AGE_RECIPIENT)"


validate-config: check-local-config ## Validate local non-secret configuration before any SSH connection
	@$(PYTHON) $(CONFIG_VALIDATOR) $(CONFIG)

ansible-syntax: check-ansible-deps ## Run Ansible syntax checks against safe example inputs
	@command -v "$(ANSIBLE_PLAYBOOK)" >/dev/null 2>&1 || { printf '%s\n' 'ERROR: ansible-playbook is required.' >&2; exit 127; }
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/preflight.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/base.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/users.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/ci-deploy-transport.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-ci-deploy-transport.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/firewall.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/updates.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/docker.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/coolify-readiness.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/coolify.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/recover-coolify.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-coolify.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/coolify-upgrade-preflight.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/coolify-upgrade.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/coolify-upgrade-resume.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/coolify-evaluate-4-3-21-preflight.yml --syntax-check -e @$(EXAMPLE_CONFIG) -e solo_vps_coolify_evaluation_target_id=syntax-check -e solo_vps_coolify_evaluation_sentinel_url=https://coolify.example.com
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/coolify-evaluate-4-3-21-upgrade.yml --syntax-check -e @$(EXAMPLE_CONFIG) -e solo_vps_coolify_evaluation_target_id=syntax-check -e solo_vps_coolify_evaluation_sentinel_url=https://coolify.example.com
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/coolify-evaluate-4-3-21-resume.yml --syntax-check -e @$(EXAMPLE_CONFIG) -e solo_vps_coolify_evaluation_target_id=syntax-check -e solo_vps_coolify_evaluation_sentinel_url=https://coolify.example.com
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-coolify-4-3-21-candidate.yml --syntax-check -e @$(EXAMPLE_CONFIG) -e solo_vps_coolify_evaluation_target_id=syntax-check -e solo_vps_coolify_evaluation_sentinel_url=https://coolify.example.com
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/backup-tooling.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-backup-tooling.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/backup-readiness.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/backup-runtime.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-backup-runtime.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml --syntax-check -e @$(EXAMPLE_CONFIG) -e solo_vps_backup_operation=repository-status
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/observability-tooling.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-observability-tooling.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-observability-log-drain.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-observability-log-drain-disabled.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/test-observability-loki.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/observability-runtime.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-observability-runtime.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/metrics-runtime.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-metrics-runtime.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/audit-observability-confidentiality.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/bootstrap.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-base.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-users.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-firewall.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-updates.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-docker.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-platform.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/ssh-harden.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify-ssh.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/verify.yml --syntax-check -e @$(EXAMPLE_CONFIG)
	@$(ANSIBLE_PLAYBOOK) -i $(EXAMPLE_INVENTORY) $(PLAYBOOK_DIR)/audit.yml --syntax-check -e @$(EXAMPLE_CONFIG)

check-local-config:
	@test -f "$(CONFIG)" || { printf 'ERROR: missing %s (run: make init).\n' "$(CONFIG)" >&2; exit 2; }

check-local-inventory:
	@test -f "$(INVENTORY)" || { printf 'ERROR: missing %s (run: make init).\n' "$(INVENTORY)" >&2; exit 2; }

check-local-files: check-local-config check-local-inventory

check-ssh-hardening-confirm: ## Require provider recovery plus explicit workstation-admin-login proof before SSH hardening
	@test "$(SSH_HARDENING_CONFIRM)" = "$(SSH_HARDENING_CONFIRM_REQUIRED)" -a "$(SSH_HARDENING_ADMIN_LOGIN_CONFIRM)" = "$(SSH_HARDENING_ADMIN_LOGIN_CONFIRM_REQUIRED)" || { \
		printf '%s\n' \
			'ERROR: SSH hardening is access-critical and intentionally not part of bootstrap.' \
			'Keep provider console/recovery available and first prove a fresh admin login from the normal workstation.' \
			'Then rerun with both acknowledgements:' \
			'  SSH_HARDENING_CONFIRM=$(SSH_HARDENING_CONFIRM_REQUIRED) SSH_HARDENING_ADMIN_LOGIN_CONFIRM=$(SSH_HARDENING_ADMIN_LOGIN_CONFIRM_REQUIRED) make ssh-harden' >&2; \
		exit 2; \
	}


check-ci-deploy-transport-confirm: ## Refuse SSH transport mutation without explicit operator confirmation
	@test "$(CI_DEPLOY_TRANSPORT_CONFIRM)" = "$(CI_DEPLOY_TRANSPORT_CONFIRM_REQUIRED)" || { \
		printf '%s\n' \
			'ERROR: CI deploy transport changes a dedicated SSH account and sshd Match policy.' \
			'Keep the current ops session/provider recovery path available, review the plan, then rerun with:' \
			'  CI_DEPLOY_TRANSPORT_CONFIRM=$(CI_DEPLOY_TRANSPORT_CONFIRM_REQUIRED) make ci-deploy-transport' >&2; \
		exit 2; \
	}

check-coolify-recovery-confirm: ## Require explicit acknowledgement before adopting an unmarked interrupted Coolify first install
	@test "$(COOLIFY_RECOVERY_CONFIRM)" = "$(COOLIFY_RECOVERY_CONFIRM_REQUIRED)" || { \
		printf '%s\n' \
			'ERROR: unmarked Coolify recovery is explicit and fail-closed.' \
			'Review that /data/coolify came from the interrupted Solo VPS first-install attempt, then rerun with:' \
			'  COOLIFY_RECOVERY_CONFIRM=$(COOLIFY_RECOVERY_CONFIRM_REQUIRED) make coolify-recover' >&2; \
		exit 2; \
	}

doctor-local: check-local-files ## Validate local tooling, dependencies, public key, config, and single-VPS inventory without SSH
	@$(PYTHON) $(DOCTOR) --config $(CONFIG) --inventory $(INVENTORY) --ansible-playbook "$(ANSIBLE_PLAYBOOK)" --ssh "$(SSH)"
	@$(MAKE) --no-print-directory check-ansible-deps

doctor-admin-local: check-local-files ## Validate that access-critical workflows will connect as admin.user
	@$(PYTHON) $(DOCTOR) --config $(CONFIG) --inventory $(INVENTORY) --ansible-playbook "$(ANSIBLE_PLAYBOOK)" --ssh "$(SSH)" --require-admin-inventory-user
	@$(MAKE) --no-print-directory check-ansible-deps

doctor-platform-local: doctor-local ## Report optional platform capability readiness without network access
	@$(PYTHON) $(PLATFORM_DOCTOR) --root . --config "$(CONFIG)" --inventory "$(INVENTORY)" --sops-policy "$(SOPS_POLICY)" --sops-recipient "$(SOPS_RECIPIENT_FILE)"

doctor: doctor-platform-local ## Run platform-aware local diagnostics, then remote preflight
	@$(MAKE) --no-print-directory preflight

preflight: validate-config check-local-inventory ## Run read-only config and supported-target checks
	@command -v "$(ANSIBLE_PLAYBOOK)" >/dev/null 2>&1 || { printf '%s\n' 'ERROR: ansible-playbook is required.' >&2; exit 127; }
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/preflight.yml -e @$(CONFIG)

bootstrap: doctor-local ## Preflight, then apply the current host bootstrap baseline (does not harden sshd)
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/bootstrap.yml -e @$(CONFIG)

verify: doctor-platform-local ## Check the host and every completed SSH/Coolify phase without changing them
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify.yml -e @$(CONFIG)

firewall: doctor-local ## Apply only the M5 UFW host firewall baseline
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/firewall.yml -e @$(CONFIG)

verify-firewall: doctor-local ## Read-only verification of the M5 host firewall/exposure baseline
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-firewall.yml -e @$(CONFIG)

updates: doctor-local ## Apply only the M6 automatic security update baseline
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/updates.yml -e @$(CONFIG)

verify-updates: doctor-local ## Read-only verification of the M6 automatic security update baseline
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-updates.yml -e @$(CONFIG)

docker: doctor-local ## Apply only the M7 Docker host baseline
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/docker.yml -e @$(CONFIG)

verify-docker: doctor-local ## Read-only verification of the M7 Docker host baseline
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-docker.yml -e @$(CONFIG)

verify-platform: doctor-platform-local ## Read-only M18 platform exposure/service summary with explicit evidence boundaries
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-platform.yml -e @$(CONFIG)

audit: doctor-platform-local ## Read-only M19 security audit of implemented host controls and exposure
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/audit.yml -e @$(CONFIG)

ops-status: doctor-admin-local ## Read-only M22 host/container status and one-shot resource summary
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/ops-status.yml -e @$(CONFIG)

check-ops-log-args: ## Validate the explicit bounded Docker log request
	@case "$(OPS_LOG_CONTAINER)" in \
		''|*[!A-Za-z0-9_.-]*) printf '%s\n' 'ERROR: CONTAINER must be one exact Docker container name from: make ops-status' >&2; exit 2 ;; \
	esac
	@case "$(OPS_LOG_TAIL)" in \
		''|*[!0-9]*) printf '%s\n' 'ERROR: TAIL must be an integer from 1 to 1000' >&2; exit 2 ;; \
	esac
	@test "$(OPS_LOG_TAIL)" -ge 1 -a "$(OPS_LOG_TAIL)" -le 1000 || { printf '%s\n' 'ERROR: TAIL must be an integer from 1 to 1000' >&2; exit 2; }

ops-logs: doctor-admin-local check-ops-log-args ## Read-only M22 bounded Docker logs for one explicitly selected container
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/ops-logs.yml -e @$(CONFIG) -e solo_vps_ops_log_container="$(OPS_LOG_CONTAINER)" -e solo_vps_ops_log_tail="$(OPS_LOG_TAIL)"

observability-tooling: doctor-admin-local ## Install only the pinned Grafana Alloy binary; does not start services or send telemetry
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/observability-tooling.yml -e @$(CONFIG)

verify-observability-tooling: doctor-admin-local ## Read-only verification of pinned Grafana Alloy host tooling
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-observability-tooling.yml -e @$(CONFIG)

observability-secrets-init: validate-secrets-policy check-secrets-tools ## Workstation: create external SOPS-encrypted Grafana Cloud Logs credentials
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(OBSERVABILITY_SECRET_BUNDLE) init --root . --manifest $(SECRETS_TOOLCHAIN_MANIFEST) --policy "$(SOPS_POLICY)" --encrypted "$(OBSERVABILITY_SECRET_FILE)" --key-file "$(AGE_KEY_FILE)"

observability-secrets-check: validate-secrets-policy check-secrets-tools ## Workstation: decrypt/validate the Grafana Cloud Logs bundle without printing values
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(OBSERVABILITY_SECRET_BUNDLE) check --root . --manifest $(SECRETS_TOOLCHAIN_MANIFEST) --policy "$(SOPS_POLICY)" --encrypted "$(OBSERVABILITY_SECRET_FILE)" --key-file "$(AGE_KEY_FILE)"

observability-secrets-push: validate-secrets-policy check-secrets-tools ## Workstation: decrypt in memory and deliver Grafana Cloud Logs credentials over SSH stdin
	@test -n "$(OBSERVABILITY_VPS_HOST)" -a -n "$(OBSERVABILITY_VPS_USER)" || { printf '%s\n' 'ERROR: set OBSERVABILITY_VPS_HOST and OBSERVABILITY_VPS_USER.' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(OBSERVABILITY_SECRET_BUNDLE) push --root . --manifest $(SECRETS_TOOLCHAIN_MANIFEST) --policy "$(SOPS_POLICY)" --encrypted "$(OBSERVABILITY_SECRET_FILE)" --key-file "$(AGE_KEY_FILE)" --vps-host "$(OBSERVABILITY_VPS_HOST)" --vps-user "$(OBSERVABILITY_VPS_USER)" --remote-project "$(OBSERVABILITY_REMOTE_PROJECT)" $(if $(OBSERVABILITY_SSH_IDENTITY_FILE),--identity-file "$(OBSERVABILITY_SSH_IDENTITY_FILE)",)

verify-observability-credentials: ## VPS: read-only root verification of the materialized Grafana Cloud Logs credential file
	@if [ "$$(id -u)" -eq 0 ]; then \
		PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(OBSERVABILITY_CREDENTIAL_INSTALLER) verify; \
	else \
		sudo -n env PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(OBSERVABILITY_CREDENTIAL_INSTALLER) verify; \
	fi

verify-observability-log-drain: doctor-admin-local ## Read-only verification of the Coolify-native application log drain and opted-in resources
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-observability-log-drain.yml -e @$(CONFIG)

verify-observability-log-drain-disabled: doctor-admin-local ## Read-only recovery check: prove Custom FluentBit is fully stopped before UI-managed recreation
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-observability-log-drain-disabled.yml -e @$(CONFIG)

diagnose-observability-log-drain: doctor-admin-local ## Read-only diagnosis of collector networks and runtime port materialization
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/diagnose-observability-log-drain.yml -e @$(CONFIG)

test-observability-loki: doctor-admin-local ## EXTERNAL WRITE: send one non-secret synthetic log entry to Grafana Cloud Loki to prove endpoint/auth independently of Coolify
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/test-observability-loki.yml -e @$(CONFIG)

observability-runtime: doctor-admin-local validate-observability-runtime ## MUTATING: start non-root Alloy + loopback read-only Docker API proxy for retained app logs
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/observability-runtime.yml -e @$(CONFIG)

verify-observability-runtime: doctor-admin-local ## Read-only verification of Alloy, restricted Docker API proxy, loopback listeners and component health
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-observability-runtime.yml -e @$(CONFIG)

# Maintainer-only CRIT-005 security gate; intentionally hidden from `make help`.
audit-observability-confidentiality: doctor-admin-local
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/audit-observability-confidentiality.yml -e @$(CONFIG)

metrics-tooling: doctor-admin-local ## Install/verify the pinned Grafana Alloy binary used by host metrics; does not start metrics
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/observability-tooling.yml -e @$(CONFIG)

metrics-secrets-init: validate-secrets-policy check-secrets-tools ## Workstation: create external SOPS-encrypted Grafana Cloud Metrics credentials
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(METRICS_SECRET_BUNDLE) init --root . --manifest $(SECRETS_TOOLCHAIN_MANIFEST) --policy "$(SOPS_POLICY)" --encrypted "$(METRICS_SECRET_FILE)" --key-file "$(AGE_KEY_FILE)"

metrics-secrets-check: validate-secrets-policy check-secrets-tools ## Workstation: decrypt/validate the Grafana Cloud Metrics bundle without printing values
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(METRICS_SECRET_BUNDLE) check --root . --manifest $(SECRETS_TOOLCHAIN_MANIFEST) --policy "$(SOPS_POLICY)" --encrypted "$(METRICS_SECRET_FILE)" --key-file "$(AGE_KEY_FILE)"

metrics-secrets-push: validate-secrets-policy check-secrets-tools ## Workstation: decrypt in memory and deliver Grafana Cloud Metrics credentials over SSH stdin
	@test -n "$(METRICS_VPS_HOST)" -a -n "$(METRICS_VPS_USER)" || { printf '%s\n' 'ERROR: set METRICS_VPS_HOST and METRICS_VPS_USER.' >&2; exit 2; }
	@PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(METRICS_SECRET_BUNDLE) push --root . --manifest $(SECRETS_TOOLCHAIN_MANIFEST) --policy "$(SOPS_POLICY)" --encrypted "$(METRICS_SECRET_FILE)" --key-file "$(AGE_KEY_FILE)" --vps-host "$(METRICS_VPS_HOST)" --vps-user "$(METRICS_VPS_USER)" --remote-project "$(METRICS_REMOTE_PROJECT)" $(if $(METRICS_SSH_IDENTITY_FILE),--identity-file "$(METRICS_SSH_IDENTITY_FILE)",)

verify-metrics-credentials: ## VPS: read-only root verification of the materialized Grafana Cloud Metrics credential file
	@if [ "$$(id -u)" -eq 0 ]; then \
		PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(METRICS_CREDENTIAL_INSTALLER) verify; \
	else \
		sudo -n env PYTHONDONTWRITEBYTECODE=1 $(PYTHON) $(METRICS_CREDENTIAL_INSTALLER) verify; \
	fi

metrics-runtime: metrics-tooling verify-metrics-credentials validate-metrics-runtime ## MUTATING: collect a small host metric set and send it to Grafana Cloud
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/metrics-runtime.yml -e @$(CONFIG)

verify-metrics-runtime: doctor-admin-local ## Read-only verification of the host metrics service and loopback readiness
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-metrics-runtime.yml -e @$(CONFIG)

backup-tooling: doctor-admin-local ## Install only the pinned M14 restic host binary; does not initialize or run backups
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-tooling.yml -e @$(CONFIG)

verify-backup-tooling: doctor-admin-local ## Read-only verification of pinned M14 restic host tooling
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-backup-tooling.yml -e @$(CONFIG)

backup-readiness: doctor-admin-local check-backup-policy ## Read-only M14 local-source/policy readiness; never contacts the repository
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-readiness.yml -e @$(CONFIG)

backup-runtime: doctor-admin-local check-backup-policy validate-backup-runtime ## Install root-only M14 restic runtime + daily timer units; timer is not auto-enabled
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-runtime.yml -e @$(CONFIG)

verify-backup-runtime: doctor-admin-local ## Read-only verification of installed backup runtime files and timer state; does not contact storage
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-backup-runtime.yml -e @$(CONFIG)

backup-repository-init: doctor-admin-local ## EXTERNAL WRITE: initialize a new encrypted restic repository; fails if repository already opens
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml -e @$(CONFIG) -e solo_vps_backup_operation=repository-init

backup-repository-adopt: doctor-admin-local ## Read/check an existing encrypted restic repository before using it
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml -e @$(CONFIG) -e solo_vps_backup_operation=repository-adopt

backup-status: doctor-admin-local ## Read-only repository access + latest matching snapshot status (does not run full restic check)
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml -e @$(CONFIG) -e solo_vps_backup_operation=status

backup-check: doctor-admin-local ## Read-only restic repository integrity check + latest matching snapshot freshness
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml -e @$(CONFIG) -e solo_vps_backup_operation=check

backup-now: doctor-admin-local ## EXTERNAL WRITE: create one encrypted /data/coolify control-plane snapshot and enforce freshness
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml -e @$(CONFIG) -e solo_vps_backup_operation=backup

backup-schedule-enable: doctor-admin-local ## Enable daily backup timer only after repository check + fresh matching snapshot pass
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml -e @$(CONFIG) -e solo_vps_backup_operation=schedule-enable

backup-maintenance-schedule-enable: doctor-admin-local check-backup-retention-confirm ## Enable weekly retention/prune only after explicit dry-run review
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml -e @$(CONFIG) -e solo_vps_backup_operation=maintenance-schedule-enable -e solo_vps_backup_retention_confirm="$(BACKUP_RETENTION_CONFIRM)"

backup-retention-plan: doctor-admin-local ## Read-only restic forget dry-run using the reviewed retention policy
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml -e @$(CONFIG) -e solo_vps_backup_operation=retention-plan

backup-retention-apply: doctor-admin-local check-backup-retention-confirm ## DESTRUCTIVE EXTERNAL WRITE: apply reviewed retention + prune, then restic check/freshness
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml -e @$(CONFIG) -e solo_vps_backup_operation=retention-apply -e solo_vps_backup_retention_confirm="$(BACKUP_RETENTION_CONFIRM)"

backup-restore-test: doctor-admin-local ## Restore latest matching filesystem snapshot into temporary /var/tmp and delete the test tree
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml -e @$(CONFIG) -e solo_vps_backup_operation=restore-test

# Hidden M16 recovery operation: reads off-site storage and retains private staged material on an explicitly recovering replacement VPS.
backup-restore-staging: doctor-admin-local
	@test -n "$(RECOVERY_STAGING_ROOT)" || { printf '%s\n' 'ERROR: set RECOVERY_STAGING_ROOT to a new /var/tmp/solo-vps-disaster-recovery/<id> path.' >&2; exit 2; }
	@test "$(RECOVERY_STAGING_CONFIRM)" = "$(RECOVERY_STAGING_CONFIRM_REQUIRED)" || { printf '%s\n' 'ERROR: recovery staging requires the exact private-staging acknowledgement.' >&2; exit 2; }
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/backup-operation.yml -e @$(CONFIG) -e solo_vps_backup_operation=restore-staging -e solo_vps_backup_recovery_staging_target="$(RECOVERY_STAGING_ROOT)" -e solo_vps_backup_recovery_staging_confirm="$(RECOVERY_STAGING_CONFIRM)"

coolify-readiness: doctor-admin-local ## Read-only M9 first-install readiness check
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/coolify-readiness.yml -e @$(CONFIG)

coolify: doctor-admin-local validate-coolify-contract ## MUTATING: first-install pinned Coolify, recover known pending transactions, then verify
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/coolify.yml -e @$(CONFIG)

coolify-recover: doctor-admin-local validate-coolify-contract check-coolify-recovery-confirm ## MUTATING: verify and adopt an explicitly reviewed unmarked interrupted first install
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/recover-coolify.yml -e @$(CONFIG) -e solo_vps_coolify_recovery_allow_unmarked=true

verify-coolify: doctor-admin-local ## Read-only M9 managed Coolify/image/exposure/Docker-ownership verification
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-coolify.yml -e @$(CONFIG)

ci-deploy-transport: doctor-admin-local check-ci-deploy-transport-confirm ## MUTATING: install the dedicated forwarding-only M11 CI deployment SSH identity
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/ci-deploy-transport.yml -e @$(CONFIG)

verify-ci-deploy-transport: doctor-admin-local ## Read-only verification of the forwarding-only M11 CI deployment SSH identity
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-ci-deploy-transport.yml -e @$(CONFIG)

ssh-harden: check-local-files check-ssh-hardening-confirm ## Prepare the same-VPS admin workspace, then activate SSH hardening
	@$(PYTHON) $(DOCTOR) --config $(CONFIG) --inventory $(INVENTORY) --ansible-playbook "$(ANSIBLE_PLAYBOOK)" --ssh "$(SSH)" --require-admin-inventory-user
	@$(MAKE) --no-print-directory admin-handoff
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/ssh-harden.yml -e @$(CONFIG) -e solo_vps_ssh_hardening_confirm="$(SSH_HARDENING_CONFIRM)" -e solo_vps_ssh_human_login_confirm="$(SSH_HARDENING_ADMIN_LOGIN_CONFIRM)"

verify-ssh: doctor-admin-local ## Read-only verification of activated OpenSSH hardening
	@$(ANSIBLE_PLAYBOOK) -i $(INVENTORY) $(PLAYBOOK_DIR)/verify-ssh.yml -e @$(CONFIG)

.PHONY: validate-metrics-credentials test-metrics-credentials validate-metrics-runtime test-metrics-runtime metrics-tooling metrics-secrets-init metrics-secrets-check metrics-secrets-push verify-metrics-credentials metrics-runtime verify-metrics-runtime
