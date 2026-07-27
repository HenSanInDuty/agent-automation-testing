from uuid import uuid4

import pytest
from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    Role,
    actor_for_tenant,
    require,
)


def test_project_reviewer_can_decide_only_in_the_granted_project() -> None:
    project_id = uuid4()
    principal = Principal(
        subject="reviewer-1",
        tenant_roles={},
        project_roles={("tenant-a", project_id): frozenset({Role.REVIEWER})},
    )

    actor = actor_for_tenant(principal, "tenant-a", project_id)

    require(actor, Permission.DECIDE_PROPOSAL)
    with pytest.raises(AuthorizationError):
        actor_for_tenant(principal, "tenant-a", uuid4())


def test_service_identity_can_never_decide_a_proposal() -> None:
    principal = Principal(
        subject="worker-1",
        tenant_roles={"tenant-a": frozenset({Role.REVIEWER, Role.SERVICE})},
        project_roles={},
        is_service=True,
    )

    with pytest.raises(AuthorizationError):
        require(actor_for_tenant(principal, "tenant-a"), Permission.DECIDE_PROPOSAL)


def test_tenant_admin_can_manage_tenant() -> None:
    principal = Principal(
        subject="admin-1",
        tenant_roles={"tenant-a": frozenset({Role.TENANT_ADMIN})},
        project_roles={},
    )

    require(actor_for_tenant(principal, "tenant-a"), Permission.MANAGE_TENANT)


def test_contributor_can_submit_and_decide_generated_drafts_but_reviewer_cannot() -> None:
    project_id = uuid4()
    contributor = Principal(
        subject="contributor-1",
        tenant_roles={},
        project_roles={
            ("tenant-a", project_id): frozenset({Role.CONTRIBUTOR}),
        },
    )
    actor = actor_for_tenant(contributor, "tenant-a", project_id)

    require(actor, Permission.SUBMIT_GENERATION)
    require(actor, Permission.DECIDE_GENERATION)

    reviewer = Principal(
        subject="reviewer-1",
        tenant_roles={},
        project_roles={
            ("tenant-a", project_id): frozenset({Role.REVIEWER}),
        },
    )
    with pytest.raises(AuthorizationError):
        require(actor_for_tenant(reviewer, "tenant-a", project_id), Permission.DECIDE_GENERATION)
