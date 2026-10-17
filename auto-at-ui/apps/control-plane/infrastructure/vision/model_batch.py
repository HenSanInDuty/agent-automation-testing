"""Shared image delivery: direct inline Gemini requests or existing HF Drive delivery."""

import asyncio
import math
from collections.abc import Callable
from contextlib import asynccontextmanager
from time import monotonic

from agents.shared.models import LanguageModel
from agents.shared.openrouter import create_vision_language_model
from agents.shared.runtime import AgentStepGuard, VisionPolicy
from agents.vision.executor import VisualCandidateBatchOutcome, execute_visual_candidate_batch
from agents.vision.temporary_images import GoogleDriveTemporaryVisionImageStore
from application.vision_model_batch import VisionModelSession
from config import Settings


class VisionModelBatch:
    def __init__(
        self, settings: Settings, *, model_factory=create_vision_language_model,
        image_store_factory=GoogleDriveTemporaryVisionImageStore,
    ) -> None:
        self.settings = settings
        self._model_factory = model_factory
        self._image_store_factory = image_store_factory

    async def __call__(
        self, *, session: VisionModelSession, screenshot: bytes, task_intent: str,
        policy: VisionPolicy, max_candidates: int, guard: AgentStepGuard, sequence: int,
        check_policy: Callable[[], object], remaining_seconds: float,
    ) -> VisualCandidateBatchOutcome:
        if not math.isfinite(remaining_seconds) or remaining_seconds <= 0:
            return _unavailable("provider_timeout")
        if (session.provider, session.model) != (policy.provider, policy.model):
            return _unavailable("policy_changed")
        settings = self.settings
        key = (
            settings.gemini_api_key if policy.provider == "gemini"
            else settings.huggingface_api_key
        )
        if not key:
            return _unavailable("provider_not_configured")
        deadline = monotonic() + remaining_seconds

        @asynccontextmanager
        async def delivery():
            check_policy()
            if monotonic() >= deadline:
                raise TimeoutError
            if policy.provider == "gemini":
                # Do not even construct the Drive adapter for inline delivery.
                yield None
                return
            store = self._image_store_factory(
                service_account_file=settings.google_drive_service_account_file,
                oauth_client_id=settings.google_drive_oauth_client_id,
                oauth_client_secret=settings.google_drive_oauth_client_secret,
                oauth_refresh_token=settings.google_drive_oauth_refresh_token,
                folder_id=settings.google_drive_vision_folder_id,
                ttl=settings.vision_temporary_url_ttl_seconds,
                delete_after_delivery=settings.google_drive_vision_delete_after_delivery,
            )
            async with store.deliver(
                tenant_id=session.tenant_id, session_id=session.id,
                sequence=sequence, image=screenshot,
            ) as image_url:
                check_policy()
                if monotonic() >= deadline:
                    raise TimeoutError
                yield image_url

        try:
            async with asyncio.timeout(remaining_seconds):
                outcome = await execute_visual_candidate_batch(
                    screenshot=screenshot, content_type="image/png", task_intent=task_intent,
                    policy=policy,
                    model=_DeadlineModel(
                        self._model_factory(
                            settings, policy, timeout_seconds=min(30.0, remaining_seconds),
                        ), deadline,
                    ),
                    max_candidates=max_candidates, guard=guard, image_delivery=delivery(),
                )
                check_policy()
                if monotonic() >= deadline:
                    return _unavailable("provider_timeout")
                return outcome
        except TimeoutError:
            return _unavailable("provider_timeout")


class _DeadlineModel:
    def __init__(self, model: LanguageModel, deadline: float) -> None:
        self.model, self.deadline = model, deadline

    async def ainvoke(self, payload, **kwargs):
        remaining = min(30.0, self.deadline - monotonic())
        if remaining <= 0:
            raise TimeoutError
        async with asyncio.timeout(remaining):
            return await self.model.ainvoke(payload, **kwargs)


def _unavailable(reason: str) -> VisualCandidateBatchOutcome:
    return VisualCandidateBatchOutcome(
        status="unavailable", detail="vision model request unavailable", failure_reason=reason,
    )
