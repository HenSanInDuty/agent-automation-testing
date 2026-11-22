"""Sign in first, choose the tenant afterwards — against a disposable PostgreSQL database."""

import pytest
from api.v1.dependencies import authorization
from api.v1.routes import auth as auth_routes
from application.authentication import AccountService, AuthenticationError
from config import get_settings
from domain.authorization import Role
from fastapi.testclient import TestClient
from infrastructure.persistence.models import SessionModel, TenantMembershipModel, UserModel
from main import app
from sqlalchemy.orm import sessionmaker

pytest_plugins = ["vision_trace_fixtures"]

PASSWORD = "SyntheticPass123"


@pytest.fixture
def accounts(disposable_database):
    for model in (UserModel, TenantMembershipModel, SessionModel):
        model.__table__.create(disposable_database)
    factory = sessionmaker(disposable_database, expire_on_commit=False)
    with factory.begin() as session:
        service = AccountService(session)
        service.create_user("tenant-b", "multi@example.test", Role.VIEWER, PASSWORD)
        multi = service._user_by_email("multi@example.test")
        session.add(
            TenantMembershipModel(
                tenant_id="tenant-a", user_id=multi.id, role=Role.TENANT_ADMIN.value,
                created_at=multi.created_at,
            )
        )
        service.create_user("tenant-a", "single@example.test", Role.CONTRIBUTOR, PASSWORD)
        service.create_user("tenant-c", "other@example.test", Role.VIEWER, PASSWORD)
    return factory


@pytest.fixture
def client(accounts, monkeypatch):
    for module in (auth_routes, authorization):
        monkeypatch.setattr(module, "create_session_factory", lambda _: accounts)
    previous = app.dependency_overrides.copy()
    app.dependency_overrides[get_settings] = lambda: get_settings().model_copy(
        update={"auth_login_max_attempts": 100}
    )
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def login(client: TestClient, email: str, **extra):
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD, **extra}
    )


def test_login_without_tenant_lists_every_membership_and_asks_to_choose(client):
    response = login(client, "multi@example.test")
    assert response.status_code == 200
    body = response.json()
    assert body["tenant_id"] == "tenant-a"
    assert body["role"] == "tenant_admin"
    assert body["tenant_selection_required"] is True
    assert body["tenants"] == [
        {"tenant_id": "tenant-a", "role": "tenant_admin"},
        {"tenant_id": "tenant-b", "role": "viewer"},
    ]
    assert client.get("/api/v1/auth/me").json()["tenant_id"] == "tenant-a"


def test_single_membership_signs_straight_in(client):
    body = login(client, "single@example.test").json()
    assert body["tenant_id"] == "tenant-a"
    assert body["tenant_selection_required"] is False
    assert body["tenants"] == [{"tenant_id": "tenant-a", "role": "contributor"}]


def test_explicit_tenant_keeps_working_and_never_asks_again(client):
    body = login(client, "multi@example.test", tenant_id="tenant-b").json()
    assert body["tenant_id"] == "tenant-b"
    assert body["role"] == "viewer"
    assert body["tenant_selection_required"] is False
    assert login(client, "multi@example.test", tenant_id="tenant-c").status_code == 401


def test_switching_tenant_rotates_the_session_and_applies_the_tenant_role(client):
    login(client, "multi@example.test")
    old_token = client.cookies.get("auto_at_session")
    csrf = client.cookies.get("auto_at_csrf")
    assert [item["tenant_id"] for item in client.get("/api/v1/auth/tenants").json()] == [
        "tenant-a", "tenant-b",
    ]
    response = client.post(
        "/api/v1/auth/tenant", json={"tenant_id": "tenant-b"}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200
    assert response.json()["tenant_id"] == "tenant-b"
    assert response.json()["role"] == "viewer"
    assert client.cookies.get("auto_at_session") != old_token
    me = client.get("/api/v1/auth/me").json()
    assert (me["tenant_id"], me["role"]) == ("tenant-b", "viewer")
    stale = TestClient(app, cookies={"auto_at_session": old_token})
    assert stale.get("/api/v1/auth/me").status_code == 401


def test_switching_requires_csrf_and_membership(client):
    login(client, "multi@example.test")
    csrf = client.cookies.get("auto_at_csrf")
    assert client.post("/api/v1/auth/tenant", json={"tenant_id": "tenant-b"}).status_code == 403
    denied = client.post(
        "/api/v1/auth/tenant", json={"tenant_id": "tenant-c"}, headers={"X-CSRF-Token": csrf}
    )
    assert denied.status_code == 404
    assert client.get("/api/v1/auth/me").json()["tenant_id"] == "tenant-a"


def test_tenant_endpoints_require_a_session(client):
    assert client.get("/api/v1/auth/tenants").status_code == 401
    assert client.post("/api/v1/auth/tenant", json={"tenant_id": "tenant-a"}).status_code in {
        401, 403,
    }


def test_wrong_password_and_unknown_user_fail_identically(accounts):
    with accounts.begin() as session:
        service = AccountService(session)
        for email, password in (
            ("multi@example.test", "WrongPassword123"),
            ("nobody@example.test", PASSWORD),
        ):
            with pytest.raises(AuthenticationError, match="Invalid email or password."):
                service.login(None, email, password, 60)
