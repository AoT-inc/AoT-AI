# coding=utf-8
"""
Backward-Compatibility Shim — AIAgentService → UnifiedOrchestrator.

Per 002_DESIGN.yaml Section 11: Shim Mappings.
Maps old import path to new UnifiedOrchestrator.

@deprecated Use UnifiedOrchestrator.plan() directly
@ANCHOR: AIAgentService_SHIM
"""
import warnings
import logging

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=DeprecationWarning)


class AIAgentService:
    """
    Shim for backward compatibility.

    Old: from aot.ai.ai_agent_service import AIAgentService
    New: from aot.ai.orchestration.unified_orchestrator import UnifiedOrchestrator

    Note:
        This is a compatibility shim. New code should use
        UnifiedOrchestrator directly for full v5.1 functionality.
    """

    def __init__(self, facility_id: str = "default"):
        logger.warning(
            "AIAgentService is deprecated. "
            "Use UnifiedOrchestrator from aot.ai.orchestration instead."
        )
        from aot.ai.orchestration.unified_orchestrator import UnifiedOrchestrator

        self._uoc = UnifiedOrchestrator(facility_id)

    def plan(self, routing_decision, query):
        """Shim for AIAgentService.plan() → UOC.plan()"""
        return self._uoc.plan(routing_decision, query)

    def get_context(self, facility_id, query):
        """Shim for AIAgentService.get_context() → KBG.get_merged_context()"""
        return self._uoc.kbg.get_merged_context(facility_id, query)
