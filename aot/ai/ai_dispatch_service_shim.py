# coding=utf-8
"""
Backward-Compatibility Shim — AIDispatchService → P4ApprovalPanel.

Per 002_DESIGN.yaml Section 11: Shim Mappings.
Maps old import path to new P4ApprovalPanel.

@deprecated Use P4ApprovalPanel.register_draft() directly
@ANCHOR: AIDispatchService_SHIM
"""
import warnings
import logging

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=DeprecationWarning)


class AIDispatchService:
    """
    Shim for backward compatibility.

    Old: from aot.ai.ai_dispatch_service import AIDispatchService
    New: from aot.ai.ui.p4_approval_panel import P4ApprovalPanel

    Note:
        This is a compatibility shim. New code should use
        P4ApprovalPanel.register_draft() directly for full v5.1 functionality.
    """

    @staticmethod
    def _dispatch_actions(agent_id, goal, insight, actions, thread_id=None, message_type='ai', metadata=None, user_id=None):
        """
        Shim for AIDispatchService._dispatch_actions() → P4ApprovalPanel flow.

        Dispatches actions: immediate actions run directly, proposed actions
        go to P4ApprovalPanel for user approval.

        Args:
            agent_id: Agent identifier
            goal: Goal/reason for the action
            insight: AI reasoning/insight
            actions: List of action dicts
            thread_id: Optional thread ID
            message_type: Message type (default 'ai')
            metadata: Optional metadata dict
            user_id: Optional user ID

        Returns:
            Dict with history_id, status, proposed, immediate_results, draft_ids
        """
        from aot.ai.ui.p4_approval_panel import P4ApprovalPanel

        logger.warning(
            "AIDispatchService._dispatch_actions is deprecated. "
            "Use P4ApprovalPanel.register_draft() directly."
        )

        # Use the actual AIDispatchService for dispatch logic
        # Shim exists only to redirect the import path
        from aot.ai.ai_dispatch_service import AIDispatchService as _Original
        return _Original._dispatch_actions(
            agent_id, goal, insight, actions,
            thread_id=thread_id,
            message_type=message_type,
            metadata=metadata,
            user_id=user_id
        )

    @staticmethod
    def _register_drafts(actions, reasoning, agent_name='AI'):
        """Shim for AIDispatchService._register_drafts() → P4ApprovalPanel.register_draft()"""
        from aot.ai.ai_dispatch_service import AIDispatchService as _Original
        return _Original._register_drafts(actions, reasoning, agent_name)

    @staticmethod
    def _register_drafts_no_commit(actions, reasoning, agent_name='AI'):
        """Shim for AIDispatchService._register_drafts_no_commit()"""
        from aot.ai.ai_dispatch_service import AIDispatchService as _Original
        return _Original._register_drafts_no_commit(actions, reasoning, agent_name)

    @staticmethod
    def _apply_p4_device_gate(actions, agent_id):
        """Shim for AIDispatchService._apply_p4_device_gate()"""
        from aot.ai.ai_dispatch_service import AIDispatchService as _Original
        return _Original._apply_p4_device_gate(actions, agent_id)

    @staticmethod
    def _check_approval_required(action_type, target_id, params):
        """Shim for AIDispatchService._check_approval_required()"""
        from aot.ai.ai_dispatch_service import AIDispatchService as _Original
        return _Original._check_approval_required(action_type, target_id, params)
