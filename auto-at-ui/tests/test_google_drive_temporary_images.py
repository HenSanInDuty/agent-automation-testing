import asyncio
import json
from uuid import uuid4

import httpx
from agents.vision.temporary_images import GoogleDriveTemporaryVisionImageStore


def test_google_drive_temporary_delivery_unlists_then_deletes_the_file() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/upload/drive/v3/files":
            return httpx.Response(200, json={"id": "temporary-file"})
        if request.url.path.endswith("/permissions"):
            assert json.loads(request.content) == {
                "type": "anyone", "role": "reader", "allowFileDiscovery": False
            }
            return httpx.Response(200, json={"id": "permission"})
        if request.method == "GET" and request.url.path.endswith("/temporary-file"):
            return httpx.Response(
                200,
                json={"webContentLink": "https://drive.usercontent.google.com/download?id=temporary-file"},
            )
        if request.method == "DELETE":
            return httpx.Response(204)
        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    store = GoogleDriveTemporaryVisionImageStore(
        service_account_file="/run/secrets/google-drive-service-account.json",
        folder_id="shared-drive-folder",
        ttl=60,
        delete_after_delivery=True,
        transport=httpx.MockTransport(handler),
    )

    async def access() -> str:
        async def test_token(_credentials):
            return "access-token"

        store._load_credentials = lambda _filename: {}  # type: ignore[method-assign]
        store._access_token = test_token  # type: ignore[method-assign]
        async with store.deliver(
            tenant_id="tenant-a", session_id=uuid4(), sequence=1, image=b"png-bytes"
        ) as image_url:
            assert image_url == "https://drive.usercontent.google.com/download?id=temporary-file"
        return "completed"

    assert asyncio.run(access()) == "completed"
    assert [request.method for request in requests] == ["POST", "POST", "GET", "DELETE"]
    upload = requests[0]
    assert upload.headers["authorization"] == "Bearer access-token"
    assert b'"parents":["shared-drive-folder"]' in upload.content
    assert "supportsAllDrives=true" in str(upload.url)


def test_google_drive_delivery_deletes_file_when_vision_call_fails() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST" and request.url.path == "/upload/drive/v3/files":
            return httpx.Response(200, json={"id": "temporary-file"})
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"webContentLink": "https://drive.usercontent.google.com/download?id=temporary-file"},
            )
        return httpx.Response(204 if request.method == "DELETE" else 200, json={})

    store = GoogleDriveTemporaryVisionImageStore(
        service_account_file="/run/secrets/google-drive-service-account.json",
        folder_id="folder",
        ttl=60,
        delete_after_delivery=True,
        transport=httpx.MockTransport(handler),
    )

    async def access() -> None:
        async def test_token(_credentials):
            return "access-token"

        store._load_credentials = lambda _filename: {}  # type: ignore[method-assign]
        store._access_token = test_token  # type: ignore[method-assign]
        try:
            async with store.deliver(
                tenant_id="tenant-a", session_id=uuid4(), sequence=1, image=b"png-bytes"
            ):
                raise RuntimeError("provider failure")
        except RuntimeError:
            pass

    asyncio.run(access())
    assert methods == ["POST", "POST", "GET", "DELETE"]


def test_google_drive_delivery_can_retain_an_unlisted_file() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "POST" and request.url.path == "/upload/drive/v3/files":
            return httpx.Response(200, json={"id": "retained-file"})
        if request.method == "GET":
            return httpx.Response(
                200,
                json={"webContentLink": "https://drive.usercontent.google.com/download?id=retained-file"},
            )
        return httpx.Response(200, json={})

    store = GoogleDriveTemporaryVisionImageStore(
        service_account_file=None,
        folder_id="folder",
        ttl=60,
        oauth_client_id="client-id",
        oauth_client_secret="client-secret",
        oauth_refresh_token="refresh-token",
        delete_after_delivery=False,
        transport=httpx.MockTransport(handler),
    )

    async def access() -> None:
        async def test_token():
            return "access-token"

        store._token = test_token  # type: ignore[method-assign]
        async with store.deliver(
            tenant_id="tenant-a", session_id=uuid4(), sequence=1, image=b"png-bytes"
        ):
            pass

    asyncio.run(access())
    assert methods == ["POST", "POST", "GET"]


def test_google_drive_uses_oauth_refresh_token_for_my_drive() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://oauth2.googleapis.com/token"
        assert request.content == (
            b"client_id=client-id&client_secret=client-secret&refresh_token=refresh-token"
            b"&grant_type=refresh_token"
        )
        return httpx.Response(200, json={"access_token": "oauth-access-token"})

    store = GoogleDriveTemporaryVisionImageStore(
        service_account_file=None,
        folder_id="my-drive-folder",
        ttl=60,
        oauth_client_id="client-id",
        oauth_client_secret="client-secret",
        oauth_refresh_token="refresh-token",
        transport=httpx.MockTransport(handler),
    )

    assert asyncio.run(store._token()) == "oauth-access-token"
