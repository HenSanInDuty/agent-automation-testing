"""Short-lived screenshot delivery for external vision providers."""

import json
from base64 import urlsafe_b64encode
from contextlib import asynccontextmanager
from pathlib import Path
from time import time
from uuid import UUID

import httpx
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class SupabaseTemporaryVisionImageStore:
    """Never returns or persists a signed URL outside the model-call scope."""

    def __init__(
        self, *, url: str | None, service_role_key: str | None, bucket: str, ttl: int
    ) -> None:
        self._url, self._key, self._bucket, self._ttl = url, service_role_key, bucket, ttl

    @asynccontextmanager
    async def deliver(self, *, tenant_id: str, session_id: UUID, sequence: int, image: bytes):
        if not self._url or not self._key:
            raise ValueError("temporary vision image store is not configured")
        path = f"vision/{tenant_id}/{session_id}/{sequence}.png"
        headers = {"Authorization": f"Bearer {self._key}", "apikey": self._key}
        async with httpx.AsyncClient(base_url=self._url.rstrip("/"), timeout=30) as client:
            response = await client.post(
                f"/storage/v1/object/{self._bucket}/{path}",
                headers={**headers, "Content-Type": "image/png", "x-upsert": "false"},
                content=image,
            )
            response.raise_for_status()
            try:
                signed = await client.post(
                    f"/storage/v1/object/sign/{self._bucket}/{path}", headers=headers,
                    json={"expiresIn": self._ttl},
                )
                signed.raise_for_status()
                relative = signed.json().get("signedURL")
                if not isinstance(relative, str) or not relative.startswith("/"):
                    raise ValueError("temporary vision image URL is invalid")
                yield f"{self._url.rstrip('/')}{relative}"
            finally:
                await client.delete(f"/storage/v1/object/{self._bucket}/{path}", headers=headers)


class GoogleDriveTemporaryVisionImageStore:
    """Deliver a screenshot through a non-discoverable public Drive file.

    Google Drive has no equivalent to an S3 signed URL. The returned link is
    never persisted or emitted by this application. Deletion on context exit is
    configurable; retained files keep their ``anyone:reader`` permission.
    """

    _drive_scope = "https://www.googleapis.com/auth/drive"

    def __init__(
        self,
        *,
        service_account_file: str | None,
        folder_id: str | None,
        ttl: int,
        oauth_client_id: str | None = None,
        oauth_client_secret: str | None = None,
        oauth_refresh_token: str | None = None,
        delete_after_delivery: bool = True,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._service_account_file = service_account_file
        self._oauth_client_id = oauth_client_id
        self._oauth_client_secret = oauth_client_secret
        self._oauth_refresh_token = oauth_refresh_token
        self._delete_after_delivery = delete_after_delivery
        self._folder_id = folder_id
        self._ttl = ttl
        self._transport = transport

    @asynccontextmanager
    async def deliver(self, *, tenant_id: str, session_id: UUID, sequence: int, image: bytes):
        del tenant_id, session_id, sequence
        if not self._folder_id:
            raise ValueError("temporary Google Drive vision image store is not configured")
        if not self._has_oauth_credentials() and not self._service_account_file:
            raise ValueError("temporary Google Drive vision image store is not configured")
        if not 1 <= self._ttl <= 60:
            raise ValueError("temporary Google Drive URL TTL is outside policy")
        token = await self._token()
        headers = {"Authorization": f"Bearer {token}"}
        file_id: str | None = None
        async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
            try:
                upload = await client.post(
                    "https://www.googleapis.com/upload/drive/v3/files",
                    params={"uploadType": "multipart", "supportsAllDrives": "true", "fields": "id"},
                    headers={
                        **headers,
                        "Content-Type": "multipart/related; boundary=auto-at-boundary",
                    },
                    content=self._multipart_body(image),
                )
                upload.raise_for_status()
                file_id = upload.json().get("id")
                if not isinstance(file_id, str) or not file_id:
                    raise ValueError("Google Drive upload did not return a file ID")
                permission = await client.post(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}/permissions",
                    params={"supportsAllDrives": "true", "sendNotificationEmail": "false"},
                    headers={**headers, "Content-Type": "application/json"},
                    json={"type": "anyone", "role": "reader", "allowFileDiscovery": False},
                )
                permission.raise_for_status()
                metadata = await client.get(
                    f"https://www.googleapis.com/drive/v3/files/{file_id}",
                    params={"supportsAllDrives": "true", "fields": "webContentLink"},
                    headers=headers,
                )
                metadata.raise_for_status()
                download_url = metadata.json().get("webContentLink")
                if not isinstance(download_url, str) or not download_url.startswith("https://"):
                    raise ValueError("Google Drive upload did not return a downloadable link")
                # This URL is not persisted or emitted anywhere outside this scope.
                yield download_url
            finally:
                if file_id and self._delete_after_delivery:
                    deleted = await client.delete(
                        f"https://www.googleapis.com/drive/v3/files/{file_id}",
                        params={"supportsAllDrives": "true"},
                        headers=headers,
                    )
                    deleted.raise_for_status()

    async def _access_token(self, credentials: dict[str, str]) -> str:
        now = int(time())
        assertion = self._signed_jwt(
            credentials,
            {
                "iss": credentials["client_email"],
                "scope": self._drive_scope,
                "aud": credentials.get("token_uri", "https://oauth2.googleapis.com/token"),
                "iat": now,
                "exp": now + 600,
            },
        )
        async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
            response = await client.post(
                credentials.get("token_uri", "https://oauth2.googleapis.com/token"),
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
        response.raise_for_status()
        token = response.json().get("access_token")
        if not isinstance(token, str) or not token:
            raise ValueError("Google OAuth did not return an access token")
        return token

    async def _token(self) -> str:
        if self._has_oauth_credentials():
            async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
                response = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": self._oauth_client_id,
                        "client_secret": self._oauth_client_secret,
                        "refresh_token": self._oauth_refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
            response.raise_for_status()
            token = response.json().get("access_token")
            if not isinstance(token, str) or not token:
                raise ValueError("Google OAuth did not return an access token")
            return token
        if not self._service_account_file:
            raise ValueError("Google Drive credentials are unavailable")
        return await self._access_token(self._load_credentials(self._service_account_file))

    def _has_oauth_credentials(self) -> bool:
        return bool(
            self._oauth_client_id and self._oauth_client_secret and self._oauth_refresh_token
        )

    def _load_credentials(self, filename: str) -> dict[str, str]:
        try:
            loaded = json.loads(Path(filename).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError("Google Drive service account credentials are unavailable") from error
        required = ("client_email", "private_key")
        if not isinstance(loaded, dict) or any(
            not isinstance(loaded.get(key), str) for key in required
        ):
            raise ValueError("Google Drive service account credentials are invalid")
        return loaded

    def _signed_jwt(self, credentials: dict[str, str], claims: dict[str, object]) -> str:
        def encoded(value: dict[str, object]) -> bytes:
            return urlsafe_b64encode(json.dumps(value, separators=(",", ":")).encode()).rstrip(b"=")

        signing_input = b".".join((encoded({"alg": "RS256", "typ": "JWT"}), encoded(claims)))
        try:
            key = serialization.load_pem_private_key(
                credentials["private_key"].encode(), password=None
            )
            signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
        except (TypeError, ValueError) as error:
            raise ValueError("Google Drive service account credentials are invalid") from error
        return b".".join((signing_input, urlsafe_b64encode(signature).rstrip(b"="))).decode()

    def _multipart_body(self, image: bytes) -> bytes:
        metadata = json.dumps(
            {"name": "vision-screenshot.png", "parents": [self._folder_id]}, separators=(",", ":")
        ).encode()
        return b"".join(
            (
                b"--auto-at-boundary\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n",
                metadata,
                b"\r\n--auto-at-boundary\r\nContent-Type: image/png\r\n\r\n",
                image,
                b"\r\n--auto-at-boundary--\r\n",
            )
        )
