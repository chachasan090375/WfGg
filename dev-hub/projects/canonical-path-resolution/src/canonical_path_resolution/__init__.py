"""ChaCha DEV canonical path resolution and governed recovery primitives.

This package deliberately owns no component registry and no agent catalogue.
Authoritative data is injected through provider protocols.
"""

from .resolver import CanonicalPathResolver, Resolution, ResolutionStatus
from .reconciler import DriftResult, PathDriftReconciler
from .non_progress import AttemptSnapshot, NonProgressDecision, NonProgressDetector
from .recovery import RecoveryPlan, RecoveryRequest, MultiAgentRecoveryRouter

__all__ = [
    "CanonicalPathResolver",
    "Resolution",
    "ResolutionStatus",
    "DriftResult",
    "PathDriftReconciler",
    "AttemptSnapshot",
    "NonProgressDecision",
    "NonProgressDetector",
    "RecoveryPlan",
    "RecoveryRequest",
    "MultiAgentRecoveryRouter",
]
