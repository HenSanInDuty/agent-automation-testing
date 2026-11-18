"""Stable target identity across fresh DOM snapshots of the same page."""

from auto_at.contracts.codex_bridge import content_hash
from auto_at.contracts.vision_coverage import VisualPageControl, VisualPageInventory


def target_key(checkpoint, descriptor):
    return checkpoint.url_fingerprint + ":" + content_hash(descriptor)


def inventory(checkpoint, bound, attempted, scope="all"):
    elements = {element.element_id: element for element in bound.observation.elements}
    controls = {}
    for binding in bound.bindings:
        element = elements[binding.element_id]
        key = target_key(checkpoint, binding.descriptor)
        previous = attempted.get(key)
        controls[key] = VisualPageControl(
            key=content_hash(binding.descriptor), role=element.role, name=element.name,
            button_kind=element.button_kind,
            **(previous or {}),
        )
    return VisualPageInventory(
        state_id=checkpoint.state_id, checkpoint_id=checkpoint.id,
        page_url=checkpoint.page_url, url_fingerprint=checkpoint.url_fingerprint,
        controls=tuple(controls.values()), interaction_scope=scope,
        truncated=bound.observation.truncated,
        scrollable=bound.observation.scrollable, skipped_count=bound.observation.skipped_count,
    )


def remaining_observation(checkpoint, bound, attempted):
    bindings = tuple(b for b in bound.bindings
                     if target_key(checkpoint, b.descriptor) not in attempted)
    ids = {binding.element_id for binding in bindings}
    observation = bound.observation.model_copy(update={
        "elements": tuple(e for e in bound.observation.elements if e.element_id in ids),
    })
    return bound.model_copy(update={"observation": observation, "bindings": bindings})
