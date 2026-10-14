"""Exercise the pinned RustFS image with disposable storage and synthetic evidence."""

import json
import re
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from time import monotonic, sleep
from uuid import uuid4

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from config import Settings
from domain.vision import VisualSessionScope
from infrastructure.artifacts.rustfs import RustFSArtifactStore
from vision_trace_fixtures import frame, operation

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def disposable_rustfs():
    docker = shutil.which("docker")
    if docker is None:
        pytest.skip("Docker is required for the isolated RustFS storage check")
    match = re.search(r"^    image: (rustfs/rustfs:[^\s]+)$",
                      (ROOT / "docker-compose.yml").read_text(), re.MULTILINE)
    assert match, "Compose must pin the RustFS image"
    image = match.group(1)
    available = subprocess.run(
        [docker, "image", "inspect", image], capture_output=True, timeout=15,
    )
    if available.returncode:
        pytest.skip(f"Docker or pinned image unavailable; run docker pull {image}")
    name = "auto-at-rustfs-fixture-" + uuid4().hex
    try:
        subprocess.run(
            [docker, "run", "--rm", "-d", "--name", name,
             "-p", "127.0.0.1::9000", "--tmpfs", "/data:rw,uid=10001,gid=10001,mode=755",
             "--tmpfs", "/logs:rw,uid=10001,gid=10001,mode=755",
             "-e", "RUSTFS_ACCESS_KEY=fixture-access",
             "-e", "RUSTFS_SECRET_KEY=fixture-secret-only",
             "-e", "RUSTFS_CONSOLE_ENABLE=false",
             "-e", "RUSTFS_OBS_LOG_DIRECTORY=/logs", image, "/data"],
            capture_output=True, check=True, timeout=30,
        )
        details = json.loads(subprocess.check_output(
            [docker, "inspect", name], text=True, timeout=15,
        ))[0]
        port = details["NetworkSettings"]["Ports"]["9000/tcp"][0]["HostPort"]
        settings = Settings(
            _env_file=None, rustfs_endpoint=f"http://127.0.0.1:{port}",
            rustfs_access_key="fixture-access", rustfs_secret_key="fixture-secret-only",
            rustfs_bucket="fixture-evidence", rustfs_secure=False, rustfs_path_style=True,
        )
        client = boto3.client(
            "s3", endpoint_url=settings.rustfs_endpoint,
            aws_access_key_id=settings.rustfs_access_key,
            aws_secret_access_key=settings.rustfs_secret_key,
            region_name="us-east-1",
            config=Config(connect_timeout=1, read_timeout=3, retries={"max_attempts": 0},
                          proxies={}, s3={"addressing_style": "path"}),
        )
        store = RustFSArtifactStore(settings, client)
        store._bucket_ready = False
        deadline = monotonic() + 45
        while True:
            try:
                store._ensure_bucket()
                break
            except (BotoCoreError, ClientError):
                if monotonic() >= deadline:
                    pytest.fail("isolated RustFS did not become ready")
                sleep(0.5)
        yield store
    finally:
        subprocess.run([docker, "rm", "-f", "-v", name], capture_output=True, timeout=30)


def test_pinned_rustfs_creates_and_preserves_operation_evidence(disposable_rustfs):
    store = disposable_rustfs
    scope = VisualSessionScope("fixture-tenant", uuid4(), uuid4())
    intent = operation(scope)
    content = b"\x89PNG\r\n\x1a\nsynthetic-evidence"
    record = frame(intent, "before", content)

    # alpha.69 returns NoSuchKey here even though the key has never existed.
    store.write_operation_frame(record, content)
    store.write_operation_frame(record, content)
    assert store.read_operation_frame(record) == content
    different = frame(intent, "before", content + b"conflict")
    with pytest.raises(ValueError, match="verification"):
        store.write_operation_frame(different, content + b"conflict")
    assert store.read_operation_frame(record) == content


def test_pinned_rustfs_allows_only_one_competing_frame_writer(disposable_rustfs):
    store = disposable_rustfs
    scope = VisualSessionScope("fixture-tenant", uuid4(), uuid4())
    # Competing writers use distinct bytes but the same operation/role key.
    for _ in range(5):
        intent = operation(scope)
        barrier = Barrier(4)

        def write(index, intent=intent, barrier=barrier):
            content = b"\x89PNG\r\n\x1a\nwriter-" + str(index).encode()
            record = frame(intent, "before", content)
            barrier.wait(timeout=10)
            try:
                store.write_operation_frame(record, content)
            except ValueError:
                return None
            return record, content

        with ThreadPoolExecutor(max_workers=4) as pool:
            winners = [result for result in pool.map(write, range(4)) if result is not None]
        assert len(winners) == 1
        record, content = winners[0]
        assert store.read_operation_frame(record) == content
