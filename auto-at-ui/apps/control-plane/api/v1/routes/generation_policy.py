from typing import Annotated

from application.generation_policy import GenerationPolicies, GenerationPolicyError
from auto_at.contracts.codex_generation import GenerationProviderPolicy
from domain.authorization import AuthorizationError, Principal
from fastapi import APIRouter, Depends, HTTPException

from api.v1.dependencies.authorization import current_principal, current_tenant, require_csrf
from api.v1.dependencies.generation_policy import generation_policies

router = APIRouter(prefix="/test-generations", tags=["test-generations"])


@router.get("/provider")
def get_provider(
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    policies: Annotated[GenerationPolicies, Depends(generation_policies)],
):
    try:
        return policies.catalogue(tenant_id, principal)
    except AuthorizationError as error:
        raise HTTPException(403, "Tenant access denied.") from error


@router.put("/provider", dependencies=[Depends(require_csrf)])
def set_provider(
    payload: GenerationProviderPolicy,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    policies: Annotated[GenerationPolicies, Depends(generation_policies, scope="function")],
):
    try:
        return policies.update(tenant_id, principal, payload)
    except AuthorizationError as error:
        raise HTTPException(
            403, "Only tenant administrators can change generation settings.",
        ) from error
    except GenerationPolicyError as error:
        raise HTTPException(409, "The selected generation provider is unavailable.") from error
