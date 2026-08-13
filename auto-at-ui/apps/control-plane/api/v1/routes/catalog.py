"""Authorized project and test-case catalog HTTP boundary."""

from typing import Annotated
from uuid import UUID, uuid4

from auto_at.contracts.execution import TargetType
from config import Settings, get_settings
from domain.authorization import (
    AuthorizationError,
    Permission,
    Principal,
    actor_for_tenant,
    require,
)
from domain.entities import Project, TestCase
from fastapi import APIRouter, Depends, HTTPException, Query, status
from infrastructure.persistence.repositories import SqlAlchemyCatalogRepository
from infrastructure.persistence.session import create_session_factory, transactional_session
from pydantic import BaseModel, Field

from api.v1.dependencies.authorization import current_principal, current_tenant, require_csrf

router = APIRouter(prefix="/projects", tags=["projects"])


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    default_target: TargetType = TargetType.WEB_UI


class ProjectResponse(ProjectRequest):
    id: UUID


class TestCaseRequest(BaseModel):
    id: str = Field(min_length=1, max_length=200, pattern=r"^[A-Za-z0-9._:-]+$")
    name: str = Field(min_length=1, max_length=200)
    target_type: TargetType
    revision: str = Field(min_length=7, max_length=128)
    specification: dict[str, object] = Field(default_factory=dict)


class TestCaseResponse(TestCaseRequest):
    project_id: UUID


class TestCaseNameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)


def project_response(project: Project) -> ProjectResponse:
    return ProjectResponse(id=project.id, name=project.name, default_target=project.default_target)


def test_case_response(test_case: TestCase) -> TestCaseResponse:
    return TestCaseResponse(
        id=test_case.id,
        project_id=test_case.project_id,
        name=test_case.name,
        target_type=test_case.target_type,
        revision=test_case.revision,
        specification=test_case.specification,
    )


@router.get("", response_model=list[ProjectResponse])
def list_projects(
    q: Annotated[str | None, Query(max_length=200)] = None,
    tenant_id: Annotated[str, Depends(current_tenant)] = "",
    principal: Annotated[Principal, Depends(current_principal)] = None,  # type: ignore[assignment]
    settings: Annotated[Settings, Depends(get_settings)] = None,  # type: ignore[assignment]
) -> list[ProjectResponse]:
    try:
        require(actor_for_tenant(principal, tenant_id), Permission.READ)
    except AuthorizationError as error:
        raise HTTPException(status_code=404, detail="Projects not found.") from error
    with create_session_factory(settings)() as session:
        return [
            project_response(project)
            for project in SqlAlchemyCatalogRepository(session).list_projects(tenant_id, q)
        ]


@router.post(
    "",
    response_model=ProjectResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_project(
    payload: ProjectRequest,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProjectResponse:
    try:
        require(actor_for_tenant(principal, tenant_id), Permission.MANAGE_PROJECT)
    except AuthorizationError as error:
        raise HTTPException(status_code=404, detail="Projects not found.") from error
    project = Project(uuid4(), tenant_id, payload.name.strip(), payload.default_target)
    with transactional_session(create_session_factory(settings)) as session:
        SqlAlchemyCatalogRepository(session).add_project(project)
    return project_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: UUID,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> ProjectResponse:
    with create_session_factory(settings)() as session:
        project = SqlAlchemyCatalogRepository(session).get_project(tenant_id, project_id)
    try:
        if project is None:
            raise AuthorizationError("not found")
        require(actor_for_tenant(principal, tenant_id, project_id), Permission.READ)
    except AuthorizationError as error:
        raise HTTPException(status_code=404, detail="Project not found.") from error
    return project_response(project)


@router.get("/{project_id}/tests", response_model=list[TestCaseResponse])
def list_test_cases(
    project_id: UUID,
    q: Annotated[str | None, Query(max_length=200)] = None,
    tenant_id: Annotated[str, Depends(current_tenant)] = "",
    principal: Annotated[Principal, Depends(current_principal)] = None,
    settings: Annotated[Settings, Depends(get_settings)] = None,
) -> list[TestCaseResponse]:  # type: ignore[assignment]
    with create_session_factory(settings)() as session:
        repository = SqlAlchemyCatalogRepository(session)
        project = repository.get_project(tenant_id, project_id)
        tests = [] if project is None else repository.list_test_cases(tenant_id, project_id, q)
    try:
        if project is None:
            raise AuthorizationError("not found")
        require(actor_for_tenant(principal, tenant_id, project_id), Permission.READ)
    except AuthorizationError as error:
        raise HTTPException(status_code=404, detail="Project not found.") from error
    return [test_case_response(test_case) for test_case in tests]


@router.post(
    "/{project_id}/tests",
    response_model=TestCaseResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_csrf)],
)
def create_test_case(
    project_id: UUID,
    payload: TestCaseRequest,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TestCaseResponse:
    with transactional_session(create_session_factory(settings)) as session:
        repository = SqlAlchemyCatalogRepository(session)
        project = repository.get_project(tenant_id, project_id)
        try:
            if project is None:
                raise AuthorizationError("not found")
            require(actor_for_tenant(principal, tenant_id, project_id), Permission.MANAGE_PROJECT)
            if repository.get_test_case(tenant_id, payload.id) is not None:
                raise ValueError("A test case with this ID already exists.")
        except AuthorizationError as error:
            raise HTTPException(status_code=404, detail="Project not found.") from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        test_case = TestCase(
            payload.id,
            tenant_id,
            project_id,
            payload.target_type,
            payload.revision,
            payload.specification,
            payload.name.strip(),
        )
        repository.add_test_case(test_case)
    return test_case_response(test_case)


@router.put(
    "/{project_id}/tests/{test_case_id}/name",
    response_model=TestCaseResponse,
    dependencies=[Depends(require_csrf)],
)
def rename_test_case(
    project_id: UUID,
    test_case_id: str,
    payload: TestCaseNameRequest,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TestCaseResponse:
    with transactional_session(create_session_factory(settings)) as session:
        repository = SqlAlchemyCatalogRepository(session)
        test_case = repository.get_test_case(tenant_id, test_case_id)
        try:
            if test_case is None or test_case.project_id != project_id:
                raise AuthorizationError("not found")
            require(actor_for_tenant(principal, tenant_id, project_id), Permission.MANAGE_PROJECT)
        except AuthorizationError as error:
            raise HTTPException(status_code=404, detail="Test case not found.") from error
        renamed = repository.rename_test_case(tenant_id, test_case_id, payload.name.strip())
    if renamed is None:
        raise HTTPException(status_code=404, detail="Test case not found.")
    return test_case_response(renamed)


@router.get("/{project_id}/tests/{test_case_id}", response_model=TestCaseResponse)
def get_test_case(
    project_id: UUID,
    test_case_id: str,
    tenant_id: Annotated[str, Depends(current_tenant)],
    principal: Annotated[Principal, Depends(current_principal)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> TestCaseResponse:
    with create_session_factory(settings)() as session:
        test_case = SqlAlchemyCatalogRepository(session).get_test_case(tenant_id, test_case_id)
    try:
        if test_case is None or test_case.project_id != project_id:
            raise AuthorizationError("not found")
        require(actor_for_tenant(principal, tenant_id, project_id), Permission.READ)
    except AuthorizationError as error:
        raise HTTPException(status_code=404, detail="Test case not found.") from error
    return test_case_response(test_case)
