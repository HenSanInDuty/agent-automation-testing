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


def merge_inventory(previous, current):
    """Union of the observations of one state (the agent scrolls without a new checkpoint).

    Controls are keyed by descriptor hash and the latest status wins; the list is capped at the
    contract's 100 controls and then marked truncated. Flags describe the newest observation,
    except that truncation and skipped controls are never forgotten.
    """
    if previous is None:
        return current
    controls = {control.key: control for control in previous.controls}
    controls.update({control.key: control for control in current.controls})
    ordered = tuple(controls.values())
    return current.model_copy(update={
        "controls": ordered[:100],
        "truncated": previous.truncated or current.truncated or len(ordered) > 100,
        "skipped_count": max(previous.skipped_count, current.skipped_count),
    })


def remaining_observation(checkpoint, bound, attempted):
    bindings = tuple(b for b in bound.bindings
                     if target_key(checkpoint, b.descriptor) not in attempted)
    ids = {binding.element_id for binding in bindings}
    observation = bound.observation.model_copy(update={
        "elements": tuple(e for e in bound.observation.elements if e.element_id in ids),
    })
    return bound.model_copy(update={"observation": observation, "bindings": bindings})
