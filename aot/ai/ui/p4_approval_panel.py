# coding=utf-8
"""
P4ApprovalPanel — v5.1 GATE_3 Implementation.

Human-in-the-loop approval panel for Step 4 (P4_HUMAN_GATE).
Per 002_DESIGN.yaml Section 7, Component P4.

Responsibilities:
- Draft registration (advisory summary + confidence + sources + safety status)
- User approve/modify/dismiss handling
- GATE_3 orchestration

@ANCHOR: P4_APPROVAL_PANEL
@phase gate_3_p4_human_gate
"""
import logging
import uuid
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum
from datetime import datetime, timedelta
from concurrent.futures import TimeoutError

logger = logging.getLogger(__name__)


class UserDecisionType(Enum):
    """User decision types for P4ApprovalPanel."""
    CONFIRM = "CONFIRM"      # Proceed to DAEMON dispatch
    MODIFY = "MODIFY"        # Return to PLANNING with edits
    DISMISS = "DISMISS"      # Log and exit (user sovereignty preserved)
    TIMEOUT = "TIMEOUT"      # No response within timeout period


class DraftStatus(Enum):
    """Draft status types."""
    PENDING = "pending"      # Awaiting user decision
    CONFIRMED = "confirmed"   # User confirmed
    MODIFIED = "modified"     # User modified and resubmitted
    DISMISSED = "dismissed"   # User dismissed
    EXPIRED = "expired"       # Timeout reached
    CANCELLED = "cancelled"   # Cancelled by system


class SafetyStatus(Enum):
    """Safety/VEE status indicators."""
    PASSED = "passed"         # All safety checks passed
    WARNING = "warning"       # Some concerns, proceed with caution
    BLOCKED = "blocked"       # Safety check failed, action blocked


@dataclass
class ActionSummary:
    """
    Schema: ActionSummary for draft registration.
    Contains advisory-formatted action description.
    """
    action_id: str
    action_type: str
    tool_name: str
    target_id: str
    parameters: Dict[str, Any]
    display_summary: str  # Advisory-formatted summary
    description: str = ""  # Human-readable description


@dataclass
class ConfidenceMetadata:
    """
    Schema: ConfidenceMetadata per 002_DESIGN.yaml Section 6.
    """
    display_confidence: float  # 0.0 - 1.0
    winning_level: str  # L1, L2, or L3
    confidence_sources: List[str]
    override_chain: List[str]


@dataclass
class SafetyInfo:
    """
    Safety/VEE status information for display.
    """
    status: SafetyStatus
    vee_validation_score: Optional[float] = None
    vee_evaluation_risk: Optional[str] = None  # LOW, MEDIUM, HIGH, CRITICAL
    warnings: List[str] = field(default_factory=list)
    block_reason: Optional[str] = None


@dataclass
class DraftRecord:
    """
    Internal draft record stored in memory.
    """
    draft_id: str
    action_summary: ActionSummary
    confidence: ConfidenceMetadata
    sources: List[str]  # Context sources used (L1, L2, L3)
    safety_info: SafetyInfo
    status: DraftStatus
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    user_decision: Optional[UserDecisionType] = None
    edited_actions: Optional[List[Dict[str, Any]]] = None
    user_notes: Optional[str] = None
    history_id: Optional[str] = None  # Link to AIHistory record


@dataclass
class UserDecision:
    """
    Schema: UserDecision per 002_DESIGN.yaml Section 6.
    Output of P4ApprovalPanel.await_user_decision().
    """
    decision: UserDecisionType
    draft_id: str
    edited_actions: Optional[List[Dict[str, Any]]] = None
    user_notes: Optional[str] = None


class P4ApprovalPanel:
    """
    P4ApprovalPanel — GATE_3 Implementation.

    Human-in-the-loop approval panel that enforces user agency
    while displaying advisory information about proposed actions.

    Responsibilities (per DESIGN Section 7):
    - Draft registration (advisory summary + confidence + sources + safety status)
    - User approve/modify/dismiss handling
    - GATE_3 orchestration

    Advisory Enforcement:
    - All displayed text uses advisory framing
    - Confidence scores explicitly displayed
    - Safety/VEE status icons/text displayed
    - User options: CONFIRM / MODIFY / DISMISS (equal weight)

    @phase gate_3_p4_human_gate
    @stability beta
    """

    # Default timeout for user decision (5 minutes)
    DEFAULT_TIMEOUT_SECONDS = 300

    def __init__(self):
        """Initialize P4ApprovalPanel."""
        self._drafts: Dict[str, DraftRecord] = {}
        self._pending_decisions: Dict[str, threading.Event] = {}
        self._decision_results: Dict[str, UserDecision] = {}
        logger.info("P4ApprovalPanel: INITIALIZED")

    # -------------------------------------------------------------------------
    # Public API — Draft Management
    # -------------------------------------------------------------------------

    def register_draft(
        self,
        action_summary: ActionSummary,
        confidence: ConfidenceMetadata,
        sources: List[str],
        safety_info: SafetyInfo,
        history_id: Optional[str] = None,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    ) -> str:
        """
        Register a draft for user approval.

        GATE_3 Primary Entry Point:
        Registers an action draft with full advisory context for user review.

        Args:
            action_summary: Advisory-formatted action summary
            confidence: Confidence metadata from L1/L2/L3 selection
            sources: List of context sources used (e.g., ['L1', 'L2', 'L3'])
            safety_info: Safety/VEE status information
            history_id: Optional link to AIHistory record
            timeout_seconds: Timeout for user decision

        Returns:
            draft_id: String identifier for tracking this draft

        @ANCHOR: P4_REGISTER_DRAFT
        """
        draft_id = str(uuid.uuid4())
        now = datetime.utcnow()

        draft = DraftRecord(
            draft_id=draft_id,
            action_summary=action_summary,
            confidence=confidence,
            sources=sources,
            safety_info=safety_info,
            status=DraftStatus.PENDING,
            created_at=now,
            updated_at=now,
            expires_at=now + timedelta(seconds=timeout_seconds),
            history_id=history_id
        )

        self._drafts[draft_id] = draft
        self._pending_decisions[draft_id] = threading.Event()

        logger.info(
            f"P4.register_draft: draft_id={draft_id}, "
            f"action={action_summary.tool_name}, "
            f"confidence={confidence.display_confidence:.2f}, "
            f"safety={safety_info.status.value}"
        )

        return draft_id

    def get_draft_status(self, draft_id: str) -> Optional[DraftRecord]:
        """
        Get the current status of a draft.

        Args:
            draft_id: Draft identifier

        Returns:
            DraftRecord or None if not found

        @ANCHOR: P4_GET_DRAFT_STATUS
        """
        draft = self._drafts.get(draft_id)
        if not draft:
            logger.warning(f"P4.get_draft_status: draft_id={draft_id} not found")
            return None

        # Check for expiration
        if draft.status == DraftStatus.PENDING and datetime.utcnow() > draft.expires_at:
            draft.status = DraftStatus.EXPIRED
            draft.updated_at = datetime.utcnow()
            self._notify_decision(draft_id, UserDecision(
                decision=UserDecisionType.TIMEOUT,
                draft_id=draft_id
            ))
            logger.info(f"P4.get_draft_status: draft_id={draft_id} EXPIRED")

        return draft

    def await_user_decision(self, draft_id: str, timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS) -> UserDecision:
        """
        Wait for user decision on a draft.

        Blocks until user responds, timeout occurs, or draft is cancelled.

        Args:
            draft_id: Draft identifier
            timeout_seconds: Maximum wait time

        Returns:
            UserDecision with decision type and optional edits

        Raises:
            TimeoutError: If timeout is reached before user responds

        @ANCHOR: P4_AWAIT_USER_DECISION
        """
        draft = self.get_draft_status(draft_id)
        if not draft:
            logger.warning(f"P4.await_user_decision: draft_id={draft_id} not found")
            return UserDecision(
                decision=UserDecisionType.TIMEOUT,
                draft_id=draft_id
            )

        # Check if already decided
        if draft.status != DraftStatus.PENDING:
            logger.info(f"P4.await_user_decision: draft_id={draft_id} already decided: {draft.status.value}")
            return UserDecision(
                decision=self._map_draft_status_to_decision(draft.status),
                edited_actions=draft.edited_actions,
                user_notes=draft.user_notes,
                draft_id=draft_id
            )

        logger.info(f"P4.await_user_decision: WAITING for draft_id={draft_id}, timeout={timeout_seconds}s")

        # Wait for decision event
        event = self._pending_decisions.get(draft_id)
        if not event:
            logger.error(f"P4.await_user_decision: No pending event for draft_id={draft_id}")
            return UserDecision(
                decision=UserDecisionType.TIMEOUT,
                draft_id=draft_id
            )

        # Wait with timeout
        triggered = event.wait(timeout=timeout_seconds)

        if not triggered:
            # Timeout reached
            draft.status = DraftStatus.EXPIRED
            draft.updated_at = datetime.utcnow()
            self._notify_decision(draft_id, UserDecision(
                decision=UserDecisionType.TIMEOUT,
                draft_id=draft_id
            ))
            logger.info(f"P4.await_user_decision: TIMEOUT for draft_id={draft_id}")
            return UserDecision(
                decision=UserDecisionType.TIMEOUT,
                draft_id=draft_id
            )

        # Get decision result
        result = self._decision_results.get(draft_id)
        if result:
            logger.info(f"P4.await_user_decision: DECISION for draft_id={draft_id}: {result.decision.value}")
            return result

        return UserDecision(
            decision=UserDecisionType.TIMEOUT,
            draft_id=draft_id
        )

    def submit_decision(
        self,
        draft_id: str,
        decision: UserDecisionType,
        edited_actions: Optional[List[Dict[str, Any]]] = None,
        user_notes: Optional[str] = None
    ) -> bool:
        """
        Submit a user decision for a draft.

        Called by the UI when user clicks CONFIRM/MODIFY/DISMISS.

        Args:
            draft_id: Draft identifier
            decision: User's decision
            edited_actions: Modified actions (for MODIFY decision)
            user_notes: Optional user notes

        Returns:
            True if decision was accepted, False otherwise

        @ANCHOR: P4_SUBMIT_DECISION
        """
        draft = self._drafts.get(draft_id)
        if not draft:
            logger.warning(f"P4.submit_decision: draft_id={draft_id} not found")
            return False

        if draft.status != DraftStatus.PENDING:
            logger.warning(f"P4.submit_decision: draft_id={draft_id} not pending, status={draft.status.value}")
            return False

        # Update draft
        draft.status = self._map_decision_to_draft_status(decision)
        draft.updated_at = datetime.utcnow()
        draft.user_decision = decision
        draft.edited_actions = edited_actions
        draft.user_notes = user_notes

        # Notify waiting thread
        self._notify_decision(draft_id, UserDecision(
            decision=decision,
            edited_actions=edited_actions,
            user_notes=user_notes,
            draft_id=draft_id
        ))

        logger.info(
            f"P4.submit_decision: draft_id={draft_id}, "
            f"decision={decision.value}, "
            f"has_edits={edited_actions is not None}"
        )

        return True

    def cancel_draft(self, draft_id: str, reason: str = "system_cancelled") -> bool:
        """
        Cancel a pending draft (system action).

        Args:
            draft_id: Draft identifier
            reason: Cancellation reason

        Returns:
            True if cancelled, False if not found or already decided
        """
        draft = self._drafts.get(draft_id)
        if not draft:
            return False

        if draft.status != DraftStatus.PENDING:
            return False

        draft.status = DraftStatus.CANCELLED
        draft.updated_at = datetime.utcnow()
        draft.user_notes = reason

        self._notify_decision(draft_id, UserDecision(
            decision=UserDecisionType.DISMISS,
            user_notes=reason,
            draft_id=draft_id
        ))

        logger.info(f"P4.cancel_draft: draft_id={draft_id}, reason={reason}")
        return True

    # -------------------------------------------------------------------------
    # Advisory Formatting Helpers
    # -------------------------------------------------------------------------

    def format_advisory_summary(self, draft_id: str) -> str:
        """
        Format an advisory summary for display.

        Uses advisory framing (non-directive language).

        Args:
            draft_id: Draft identifier

        Returns:
            Advisory-formatted summary string
        """
        draft = self.get_draft_status(draft_id)
        if not draft:
            return "Draft not found."

        summary = draft.action_summary
        confidence = draft.confidence

        # Advisory-formatted summary
        advisory_parts = [
            f"Based on the {', '.join(draft.sources)} context, the system suggests:",
            f"",
            f"Action: {summary.display_summary}",
            f"",
            f"Confidence: {confidence.display_confidence:.0%} (winning level: {confidence.winning_level})",
        ]

        if draft.safety_info.status == SafetyStatus.PASSED:
            advisory_parts.append("Safety Status: All checks passed")
        elif draft.safety_info.status == SafetyStatus.WARNING:
            advisory_parts.append(f"Safety Status: Warning - {', '.join(draft.safety_info.warnings)}")
        elif draft.safety_info.status == SafetyStatus.BLOCKED:
            advisory_parts.append(f"Safety Status: Blocked - {draft.safety_info.block_reason}")

        advisory_parts.extend([
            "",
            "You may consider:",
            "  - CONFIRM to proceed with this action",
            "  - MODIFY to adjust the parameters before proceeding",
            "  - DISMISS to decline this suggestion"
        ])

        return "\n".join(advisory_parts)

    def get_display_confidence(self, draft_id: str) -> Optional[float]:
        """Get display confidence for a draft."""
        draft = self.get_draft_status(draft_id)
        if not draft:
            return None
        return draft.confidence.display_confidence

    def get_safety_display_status(self, draft_id: str) -> Optional[str]:
        """
        Get safety status for UI display.

        Returns human-readable safety status string.
        """
        draft = self.get_draft_status(draft_id)
        if not draft:
            return None

        status = draft.safety_info.status
        if status == SafetyStatus.PASSED:
            return "passed"
        elif status == SafetyStatus.WARNING:
            return f"warning: {', '.join(draft.safety_info.warnings)}"
        elif status == SafetyStatus.BLOCKED:
            return f"blocked: {draft.safety_info.block_reason}"
        return "unknown"

    # -------------------------------------------------------------------------
    # Private Helpers
    # -------------------------------------------------------------------------

    def _notify_decision(self, draft_id: str, decision: UserDecision):
        """Notify waiting thread of decision."""
        self._decision_results[draft_id] = decision
        event = self._pending_decisions.get(draft_id)
        if event:
            event.set()

    def _map_draft_status_to_decision(self, status: DraftStatus) -> UserDecisionType:
        """Map draft status to user decision type."""
        mapping = {
            DraftStatus.CONFIRMED: UserDecisionType.CONFIRM,
            DraftStatus.MODIFIED: UserDecisionType.MODIFY,
            DraftStatus.DISMISSED: UserDecisionType.DISMISS,
            DraftStatus.EXPIRED: UserDecisionType.TIMEOUT,
            DraftStatus.CANCELLED: UserDecisionType.DISMISS,
        }
        return mapping.get(status, UserDecisionType.TIMEOUT)

    def _map_decision_to_draft_status(self, decision: UserDecisionType) -> DraftStatus:
        """Map user decision type to draft status."""
        mapping = {
            UserDecisionType.CONFIRM: DraftStatus.CONFIRMED,
            UserDecisionType.MODIFY: DraftStatus.MODIFIED,
            UserDecisionType.DISMISS: DraftStatus.DISMISSED,
            UserDecisionType.TIMEOUT: DraftStatus.EXPIRED,
        }
        return mapping.get(decision, DraftStatus.CANCELLED)


# Singleton instance for module-level access
_p4_panel_instance: Optional[P4ApprovalPanel] = None


def get_p4_approval_panel() -> P4ApprovalPanel:
    """
    Get the singleton P4ApprovalPanel instance.

    Returns:
        P4ApprovalPanel singleton instance
    """
    global _p4_panel_instance
    if _p4_panel_instance is None:
        _p4_panel_instance = P4ApprovalPanel()
    return _p4_panel_instance