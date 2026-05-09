# coding=utf-8
"""
AI UI Components Package.

Contains UI-related components for the AI system.
Currently includes P4ApprovalPanel (GATE_3 human-in-the-loop approval).

@ANCHOR: AI_UI_PACKAGE
"""
from aot.ai.ui.p4_approval_panel import (
    P4ApprovalPanel,
    UserDecision,
    UserDecisionType,
    DraftStatus,
    DraftRecord,
    SafetyStatus,
    SafetyInfo,
    ActionSummary,
    ConfidenceMetadata,
    get_p4_approval_panel,
)

__all__ = [
    'P4ApprovalPanel',
    'UserDecision',
    'UserDecisionType',
    'DraftStatus',
    'DraftRecord',
    'SafetyStatus',
    'SafetyInfo',
    'ActionSummary',
    'ConfidenceMetadata',
    'get_p4_approval_panel',
]