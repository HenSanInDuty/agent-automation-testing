"""Versioned contracts shared by the control plane and runner adapters."""

from auto_at.contracts.vision import (
    VisualCheckpoint,
    VisualExplorationRequest,
    VisualExplorationResult,
    VisualLocatorDescriptor,
    VisualLocatorEvidence,
    VisualLocatorHandoff,
    VisualOperation,
    VisualOperationFrame,
    VisualTrajectoryEdge,
    VisualWorkerCommand,
)

__all__ = [
    "VisualExplorationRequest", "VisualExplorationResult", "VisualTrajectoryEdge",
    "VisualCheckpoint", "VisualLocatorDescriptor", "VisualLocatorEvidence",
    "VisualLocatorHandoff", "VisualOperation", "VisualOperationFrame", "VisualWorkerCommand",
]

