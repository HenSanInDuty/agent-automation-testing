"""Provider-neutral actor and authorization policy.

Authentication adapters construct a :class:`Principal`; application use cases
use this module rather than trusting a tenant identifier supplied by a client.
"""

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID


class Role(StrEnum):
    VIEWER = "viewer"
    CONTRIBUTOR = "contributor"
    REVIEWER = "reviewer"
    PROJECT_ADMIN = "project_admin"
    TENANT_ADMIN = "tenant_admin"
    SERVICE = "service"


class Permission(StrEnum):
    READ = "read"
    CREATE_RUN = "create_run"
    CANCEL_RUN = "cancel_run"
    DECIDE_PROPOSAL = "decide_proposal"
    MANAGE_PROJECT = "manage_project"
    MANAGE_TENANT = "manage_tenant"
    SUBMIT_GENERATION = "submit_generation"
    DECIDE_GENERATION = "decide_generation"
    READ_VISION_DEBUG_EVIDENCE = "read_vision_debug_evidence"


_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.VIEWER: frozenset({Permission.READ}),
    Role.CONTRIBUTOR: frozenset(
        {
            Permission.READ,
            Permission.CREATE_RUN,
            Permission.CANCEL_RUN,
            Permission.SUBMIT_GENERATION,
            Permission.DECIDE_GENERATION,
        }
    ),
    Role.REVIEWER: frozenset({Permission.READ, Permission.DECIDE_PROPOSAL}),
    Role.PROJECT_ADMIN: frozenset(
        {
            Permission.READ,
            Permission.CREATE_RUN,
            Permission.CANCEL_RUN,
            Permission.DECIDE_PROPOSAL,
            Permission.MANAGE_PROJECT,
            Permission.SUBMIT_GENERATION,
            Permission.DECIDE_GENERATION,
        }
    ),
    Role.TENANT_ADMIN: frozenset(
        {
            Permission.READ,
            Permission.CREATE_RUN,
            Permission.CANCEL_RUN,
            Permission.DECIDE_PROPOSAL,
            Permission.MANAGE_PROJECT,
            Permission.MANAGE_TENANT,
            Permission.SUBMIT_GENERATION,
            Permission.DECIDE_GENERATION,
            Permission.READ_VISION_DEBUG_EVIDENCE,
        }
    ),
    Role.SERVICE: frozenset({Permission.READ, Permission.CREATE_RUN, Permission.CANCEL_RUN}),
}


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated identity and tenant/project grants supplied by an adapter."""

    subject: str
    tenant_roles: dict[str, frozenset[Role]]
    project_roles: dict[tuple[str, UUID], frozenset[Role]]
    is_service: bool = False


@dataclass(frozen=True, slots=True)
class Actor:
    subject: str
    tenant_id: str
    roles: frozenset[Role]
    is_service: bool = False

    def allows(self, permission: Permission) -> bool:
        return permission in set().union(*(_ROLE_PERMISSIONS[role] for role in self.roles))


class AuthorizationError(PermissionError):
    """Raised without resource details to avoid cross-tenant enumeration."""


def actor_for_tenant(principal: Principal, tenant_id: str, project_id: UUID | None = None) -> Actor:
    roles = principal.tenant_roles.get(tenant_id, frozenset())
    if project_id is not None:
        roles = roles | principal.project_roles.get((tenant_id, project_id), frozenset())
    if not roles:
        raise AuthorizationError("resource not found")
    return Actor(principal.subject, tenant_id, roles, principal.is_service)


def require(actor: Actor, permission: Permission) -> None:
    if not actor.allows(permission):
        raise AuthorizationError("resource not found")
    protected_human_permissions = {
        Permission.DECIDE_PROPOSAL,
        Permission.READ_VISION_DEBUG_EVIDENCE,
    }
    if permission in protected_human_permissions and actor.is_service:
        raise AuthorizationError("resource not found")
