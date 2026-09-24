from __future__ import annotations

import unittest
from unittest import mock

from scripts.coolify_deploy_api import (
    CoolifyDeployError,
    DeploymentNotStarted,
    DeploymentRollbackError,
    ImmutableImageState,
)
from scripts.prove_coolify_deploy_rollback import (
    ROLLBACK_PROOF_CONFIRMATION,
    prove_rollback,
    require_proof_confirmation,
    sentinel_candidate_ref,
)

RESOURCE_UUID = "example123resource456"
GOOD_DIGEST = "a" * 64
GOOD_REF = f"ghcr.io/example-user/hello-app@sha256:{GOOD_DIGEST}"


def app_state(**overrides):
    value = {
        "uuid": RESOURCE_UUID,
        "name": "hello-app-ghcr",
        "build_pack": "dockerimage",
        "ports_exposes": "8080",
        "ports_mappings": None,
        "fqdn": None,
        "docker_registry_image_name": "ghcr.io/example-user/hello-app",
        "docker_registry_image_tag": f"sha256-{GOOD_DIGEST}",
        "status": "running:healthy",
    }
    value.update(overrides)
    return value


class RollbackProofTests(unittest.TestCase):
    def test_confirmation_is_explicit_and_separate_from_normal_deploy(self) -> None:
        with mock.patch.dict("scripts.prove_coolify_deploy_rollback.os.environ", {}, clear=True):
            with self.assertRaisesRegex(CoolifyDeployError, "COOLIFY_ROLLBACK_PROOF_CONFIRM"):
                require_proof_confirmation()
        with mock.patch.dict(
            "scripts.prove_coolify_deploy_rollback.os.environ",
            {"COOLIFY_ROLLBACK_PROOF_CONFIRM": ROLLBACK_PROOF_CONFIRMATION},
            clear=True,
        ):
            require_proof_confirmation()

    def test_sentinel_candidate_is_same_repository_and_different_digest(self) -> None:
        known_good = ImmutableImageState(
            image_name="ghcr.io/example-user/hello-app",
            image_tag=f"sha256-{GOOD_DIGEST}",
        )
        candidate = sentinel_candidate_ref(known_good)
        self.assertTrue(candidate.startswith("ghcr.io/example-user/hello-app@sha256:"))
        self.assertNotEqual(candidate, GOOD_REF)
        self.assertTrue(candidate.endswith("0" * 64))

    def test_sentinel_avoids_zero_digest_collision(self) -> None:
        known_good = ImmutableImageState(
            image_name="ghcr.io/example-user/hello-app",
            image_tag=f"sha256-{'0' * 64}",
        )
        self.assertTrue(sentinel_candidate_ref(known_good).endswith("f" * 64))

    def test_proof_requires_healthy_immutable_baseline_before_mutation(self) -> None:
        class FakeClient:
            def request(self, method, url, payload=None):
                return app_state(status="running:unhealthy")

        with self.assertRaisesRegex(CoolifyDeployError, "start from running:healthy"):
            prove_rollback(
                FakeClient(),
                base_url="http://127.0.0.1:8000/api/v1",
                resource_uuid=RESOURCE_UUID,
            )

    def test_proof_accepts_rollback_ok_and_rechecks_exact_known_good_health(self) -> None:
        responses = [app_state(), app_state()]

        class FakeClient:
            def request(self, method, url, payload=None):
                return responses.pop(0)

        rollback = DeploymentRollbackError(
            outcome="DEPLOY_FAILED_ROLLBACK_OK",
            candidate_image_ref=f"ghcr.io/example-user/hello-app@sha256:{'0' * 64}",
            previous_image_ref=GOOD_REF,
            deployment_error="Coolify candidate deployment ended with status=failed",
        )
        with mock.patch("scripts.prove_coolify_deploy_rollback.apply_deployment", side_effect=rollback):
            evidence = prove_rollback(
                FakeClient(),
                base_url="http://127.0.0.1:8000/api/v1",
                resource_uuid=RESOURCE_UUID,
            )
        self.assertEqual(evidence["outcome"], "DEPLOY_FAILED_ROLLBACK_OK")
        self.assertEqual(evidence["known_good_image_ref"], GOOD_REF)
        self.assertTrue(evidence["desired_state_restored"])
        self.assertEqual(evidence["application_status"], "running:healthy")
        self.assertFalse(evidence["token_printed"])


    def test_public_domain_proof_requires_explicit_allow_domain(self) -> None:
        public = app_state(fqdn="https://hello.example")

        class FakeClient:
            def request(self, method, url, payload=None):
                return public

        with self.assertRaisesRegex(CoolifyDeployError, "no public domain"):
            prove_rollback(
                FakeClient(),
                base_url="http://127.0.0.1:8000/api/v1",
                resource_uuid=RESOURCE_UUID,
            )

    def test_public_domain_proof_is_supported_when_explicitly_allowed(self) -> None:
        responses = [app_state(fqdn="https://hello.example"), app_state(fqdn="https://hello.example")]

        class FakeClient:
            def request(self, method, url, payload=None):
                return responses.pop(0)

        rollback = DeploymentRollbackError(
            outcome="DEPLOY_FAILED_ROLLBACK_OK",
            candidate_image_ref=f"ghcr.io/example-user/hello-app@sha256:{'0' * 64}",
            previous_image_ref=GOOD_REF,
            deployment_error="Coolify candidate deployment ended with status=failed",
        )
        with mock.patch("scripts.prove_coolify_deploy_rollback.apply_deployment", side_effect=rollback):
            evidence = prove_rollback(
                FakeClient(),
                base_url="http://127.0.0.1:8000/api/v1",
                resource_uuid=RESOURCE_UUID,
                allow_domain=True,
            )
        self.assertEqual(evidence["outcome"], "DEPLOY_FAILED_ROLLBACK_OK")
        self.assertEqual(evidence["application_status"], "running:healthy")
        self.assertTrue(evidence["public_domain_present"])
        self.assertTrue(evidence["public_domain_preserved"])

    def test_public_domain_change_after_rollback_is_rejected(self) -> None:
        responses = [app_state(fqdn="https://hello.example"), app_state(fqdn="https://changed.example")]

        class FakeClient:
            def request(self, method, url, payload=None):
                return responses.pop(0)

        rollback = DeploymentRollbackError(
            outcome="DEPLOY_FAILED_ROLLBACK_OK",
            candidate_image_ref=f"ghcr.io/example-user/hello-app@sha256:{'0' * 64}",
            previous_image_ref=GOOD_REF,
            deployment_error="candidate failed",
        )
        with mock.patch("scripts.prove_coolify_deploy_rollback.apply_deployment", side_effect=rollback):
            with self.assertRaisesRegex(CoolifyDeployError, "public-domain configuration"):
                prove_rollback(
                    FakeClient(),
                    base_url="http://127.0.0.1:8000/api/v1",
                    resource_uuid=RESOURCE_UUID,
                    allow_domain=True,
                )

    def test_make_target_explicitly_allows_public_domain_for_release_proof(self) -> None:
        from pathlib import Path

        makefile = (Path(__file__).resolve().parents[1] / "Makefile").read_text(encoding="utf-8")
        target = makefile.split("prove-coolify-deploy-rollback:", 1)[1].split("\n\n", 1)[0]
        self.assertIn("--allow-domain", target)

    def test_proof_preserves_not_started_outcome_without_fake_rollback(self) -> None:
        class FakeClient:
            def request(self, method, url, payload=None):
                return app_state()

        rejected = DeploymentNotStarted(
            "Coolify candidate desired-state PATCH was rejected before mutation could be confirmed: HTTP 403"
        )
        with mock.patch("scripts.prove_coolify_deploy_rollback.apply_deployment", side_effect=rejected):
            with self.assertRaises(DeploymentNotStarted) as caught:
                prove_rollback(
                    FakeClient(),
                    base_url="http://127.0.0.1:8000/api/v1",
                    resource_uuid=RESOURCE_UUID,
                )
        self.assertEqual(caught.exception.as_dict()["outcome"], "DEPLOY_NOT_STARTED")
        self.assertFalse(caught.exception.as_dict()["mutation_started"])

    def test_proof_rejects_rollback_failed_outcome(self) -> None:
        class FakeClient:
            def request(self, method, url, payload=None):
                return app_state()

        rollback = DeploymentRollbackError(
            outcome="DEPLOY_FAILED_ROLLBACK_FAILED",
            candidate_image_ref=f"ghcr.io/example-user/hello-app@sha256:{'0' * 64}",
            previous_image_ref=GOOD_REF,
            deployment_error="candidate failed",
            rollback_error="rollback failed",
            recovery_command="safe-command",
        )
        with mock.patch("scripts.prove_coolify_deploy_rollback.apply_deployment", side_effect=rollback):
            with self.assertRaises(DeploymentRollbackError) as caught:
                prove_rollback(
                    FakeClient(),
                    base_url="http://127.0.0.1:8000/api/v1",
                    resource_uuid=RESOURCE_UUID,
                )
        self.assertEqual(caught.exception.outcome, "DEPLOY_FAILED_ROLLBACK_FAILED")
        self.assertEqual(caught.exception.recovery_command, "safe-command")


if __name__ == "__main__":
    unittest.main()
