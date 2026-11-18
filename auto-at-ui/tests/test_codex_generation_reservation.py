"""Durable call reservation prevents replay even after transient spool cleanup."""

from uuid import uuid4

import pytest
import test_codex_bridge_repository as repository_tests
import test_codex_generation as generation_tests
from infrastructure.codex_bridge.generation_model import (
    GenerationBridgeError,
    generation_model_factory,
)
from infrastructure.persistence.models import ConfigurationModel
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker
from test_codex_generation import policy, published

pytest_plugins = ["vision_trace_fixtures"]
codex_database = repository_tests.codex_database
bridge = generation_tests.bridge


def test_reservation_survives_new_client_and_contains_metadata_only(codex_database, bridge):
    factory = sessionmaker(codex_database, expire_on_commit=False)
    model_factory = generation_model_factory(bridge.model.settings, factory)
    model = model_factory(bridge.item, policy(), lambda *_: None)
    job = published(bridge)
    model.reserve_call(job)
    with factory() as db:
        saved = db.scalar(select(ConfigurationModel).where(
            ConfigurationModel.tenant_id == job.tenant_id,
            ConfigurationModel.key == f"generation.codex.call.v1.{job.job_id}",
        ))
        assert saved.value["input_hash"] == job.input_hash
        assert "redacted_request" not in saved.value
    replacement = model_factory(bridge.item, policy(), lambda *_: None)
    with pytest.raises(GenerationBridgeError, match="interrupted"):
        replacement.reserve_call(job)
    replacement.reserve_call(job.model_copy(update={"job_id": uuid4()}))
