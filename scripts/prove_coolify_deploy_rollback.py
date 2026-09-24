#!/usr/bin/env python3
"""Maintainer-only V3 proof for failed immutable-image deployment rollback.

The proof intentionally asks Coolify to deploy a syntactically valid sentinel digest
that should not exist in the current GHCR repository. The production helper must
fail the candidate deployment, restore the previously configured immutable digest,
redeploy it, and return DEPLOY_FAILED_ROLLBACK_OK. The Makefile proof target opts in
to public-domain applications because the release candidate itself is verified against
the real demo resource; generic API helpers still fail closed unless --allow-domain is
passed explicitly. Response bodies/tokens are not printed by this wrapper.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from typing import Any
from urllib.parse import quote

try:
    from scripts.coolify_deploy_api import (
        CoolifyApiClient,
        CoolifyDeployError,
        DeploymentNotStarted,
        DeploymentRollbackError,
        ImmutableImageState,
        apply_deployment,
        build_plan,
        load_token_from_environment,
        normalize_base_url,
        validate_application_state,
        validate_persisted_image_state,
    )
except ModuleNotFoundError:  # Direct execution as scripts/prove_coolify_deploy_rollback.py
    from coolify_deploy_api import (
        CoolifyApiClient,
        CoolifyDeployError,
        DeploymentNotStarted,
        DeploymentRollbackError,
        ImmutableImageState,
        apply_deployment,
        build_plan,
        load_token_from_environment,
        normalize_base_url,
        validate_application_state,
        validate_persisted_image_state,
    )

ROLLBACK_PROOF_CONFIRMATION = "I_HAVE_REVIEWED_THE_FAILED_DEPLOYMENT_ROLLBACK_PROOF"
_RESOURCE_UUID_RE = re.compile(r"^[a-z0-9]{8,64}$")
_COOLIFY_DIGEST_TAG_RE = re.compile(r"^sha256-([0-9a-f]{64})$")
_SENTINEL_DIGEST_ZERO = "0" * 64
_SENTINEL_DIGEST_F = "f" * 64


def _clean(value: Any) -> str:
    return "" if value is None else str(value).strip()


def require_proof_confirmation() -> None:
    if os.environ.get("COOLIFY_ROLLBACK_PROOF_CONFIRM", "") != ROLLBACK_PROOF_CONFIRMATION:
        raise CoolifyDeployError(
            "rollback proof is a deliberate failed deployment; require COOLIFY_ROLLBACK_PROOF_CONFIRM="
            + ROLLBACK_PROOF_CONFIRMATION
        )


def _application_url(base_url: str, resource_uuid: str) -> str:
    normalized = normalize_base_url(base_url)
    if not _RESOURCE_UUID_RE.fullmatch(resource_uuid):
        raise CoolifyDeployError("resource UUID must contain only lowercase letters/digits and be 8-64 characters")
    return f"{normalized}/applications/{quote(resource_uuid, safe='')}"


def discover_known_good(
    client: CoolifyApiClient,
    *,
    base_url: str,
    resource_uuid: str,
    expected_port: str,
    allow_domain: bool,
) -> tuple[ImmutableImageState, dict[str, Any]]:
    application = client.request("GET", _application_url(base_url, resource_uuid))
    image_name = _clean(application.get("docker_registry_image_name"))
    image_tag = _clean(application.get("docker_registry_image_tag"))
    match = _COOLIFY_DIGEST_TAG_RE.fullmatch(image_tag)
    if not image_name or match is None:
        raise CoolifyDeployError("rollback proof requires the current desired image to be an immutable sha256 digest")
    known_good = ImmutableImageState(image_name=image_name, image_tag=image_tag)
    baseline_plan = build_plan(
        base_url=base_url,
        resource_uuid=resource_uuid,
        image_ref=known_good.image_ref,
        expected_port=expected_port,
        allow_domain=allow_domain,
    )
    validate_application_state(application, baseline_plan)
    if _clean(application.get("status")) != "running:healthy":
        raise CoolifyDeployError("rollback proof requires the application to start from running:healthy")
    return known_good, application


def sentinel_candidate_ref(known_good: ImmutableImageState) -> str:
    current_digest = known_good.image_ref.rsplit("@sha256:", 1)[1]
    sentinel = _SENTINEL_DIGEST_F if current_digest == _SENTINEL_DIGEST_ZERO else _SENTINEL_DIGEST_ZERO
    return f"{known_good.image_name}@sha256:{sentinel}"


def prove_rollback(
    client: CoolifyApiClient,
    *,
    base_url: str,
    resource_uuid: str,
    expected_port: str = "8080",
    allow_domain: bool = False,
    poll_interval: float = 2.0,
    poll_timeout: float = 180.0,
) -> dict[str, Any]:
    known_good, baseline = discover_known_good(
        client,
        base_url=base_url,
        resource_uuid=resource_uuid,
        expected_port=expected_port,
        allow_domain=allow_domain,
    )
    candidate_ref = sentinel_candidate_ref(known_good)
    candidate_plan = build_plan(
        base_url=base_url,
        resource_uuid=resource_uuid,
        image_ref=candidate_ref,
        expected_port=expected_port,
        allow_domain=allow_domain,
    )

    try:
        apply_deployment(
            client,
            candidate_plan,
            poll_interval=poll_interval,
            poll_timeout=poll_timeout,
        )
    except DeploymentRollbackError as exc:
        if exc.outcome != "DEPLOY_FAILED_ROLLBACK_OK":
            # Preserve the structured rollback-failed evidence and token-free
            # recovery command for the maintainer instead of collapsing it into
            # a generic proof error.
            raise
        deployment_error = exc.deployment_error
    else:
        raise CoolifyDeployError(
            "rollback proof sentinel candidate unexpectedly deployed successfully; stop and inspect the selected repository"
        )

    after = client.request("GET", candidate_plan.application_url)
    validate_persisted_image_state(after, candidate_plan, known_good)
    final_status = _clean(after.get("status"))
    if final_status != "running:healthy":
        raise CoolifyDeployError(
            f"rollback restored desired image but final application status is {final_status or '<empty>'}, not running:healthy"
        )
    baseline_fqdn = _clean(baseline.get("fqdn"))
    final_fqdn = _clean(after.get("fqdn"))
    if final_fqdn != baseline_fqdn:
        raise CoolifyDeployError("rollback proof changed the application's public-domain configuration")

    return {
        "status": "PASS",
        "outcome": "DEPLOY_FAILED_ROLLBACK_OK",
        "failure_mode": "syntactically-valid sentinel digest expected to be absent from the current repository",
        "resource_uuid": resource_uuid,
        "known_good_image_ref": known_good.image_ref,
        "candidate_image_ref": candidate_ref,
        "deployment_failure_observed": bool(deployment_error),
        "desired_state_restored": True,
        "application_status": final_status,
        "public_domain_present": bool(baseline_fqdn),
        "public_domain_preserved": True,
        "token_printed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Maintainer-only proof of Coolify failed-deployment image rollback.")
    parser.add_argument("--resource-uuid", required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/api/v1")
    parser.add_argument("--expected-port", default="8080")
    parser.add_argument("--allow-domain", action="store_true")
    parser.add_argument("--poll-timeout", type=float, default=180.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    try:
        if args.poll_timeout <= 0 or args.poll_interval < 0:
            raise CoolifyDeployError("poll timeout must be > 0 and poll interval must be >= 0")
        require_proof_confirmation()
        token = load_token_from_environment()
        evidence = prove_rollback(
            CoolifyApiClient(token),
            base_url=args.base_url,
            resource_uuid=args.resource_uuid,
            expected_port=args.expected_port,
            allow_domain=args.allow_domain,
            poll_interval=args.poll_interval,
            poll_timeout=args.poll_timeout,
        )
        if args.json:
            print(json.dumps(evidence, indent=2, sort_keys=True))
        else:
            print("PASS Coolify failed-deployment rollback proof")
            for key, value in evidence.items():
                if key != "status":
                    print(f"  {key}: {value}")
        return 0
    except DeploymentNotStarted as exc:
        print("ERROR Coolify failed-deployment rollback proof did not start", file=sys.stderr)
        for key, value in exc.as_dict().items():
            if key != "status":
                print(f"  {key}: {value}", file=sys.stderr)
        print(
            "  action: use a reviewed short-lived maintainer token that can update and deploy the selected application; "
            "no rollback is required because the candidate PATCH was not accepted.",
            file=sys.stderr,
        )
        return 2
    except DeploymentRollbackError as exc:
        print("ERROR Coolify failed-deployment rollback proof transaction", file=sys.stderr)
        for key, value in exc.as_dict().items():
            if key != "status":
                print(f"  {key}: {value}", file=sys.stderr)
        print(
            "  recovery_note: automatic rollback failed; if the application is not running:healthy, "
            "export a reviewed short-lived COOLIFY_API_TOKEN and use the printed recovery_command on the VPS.",
            file=sys.stderr,
        )
        return 3
    except CoolifyDeployError as exc:
        print(f"ERROR Coolify failed-deployment rollback proof: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
