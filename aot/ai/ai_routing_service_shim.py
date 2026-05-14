# coding=utf-8
"""
Backward-Compatibility Shim — AIRoutingService → UnifiedOrchestrator.

Per 002_DESIGN.yaml Section 11: Shim Mappings.
Maps old import path to new UnifiedOrchestrator.route().

@deprecated Use UnifiedOrchestrator.route() directly
@ANCHOR: AIRoutingService_SHIM
"""
import warnings
import logging

logger = logging.getLogger(__name__)

# Suppress deprecation warnings during transition period
warnings.filterwarnings("ignore", category=DeprecationWarning)


def AIRoutingService(*args, **kwargs):
    """
    Shim for backward compatibility.

    Old: from aot.ai.airouting_service import AIRoutingService
    New: from aot.ai.orchestration.unified_orchestrator import UnifiedOrchestrator

    Usage:
        routing_service = AIRoutingService(facility_id)
        decision = routing_service.route(query)

    Note:
        This is a compatibility shim. New code should use
        UnifiedOrchestrator directly for full v5.1 functionality.
    """
    from aot.ai.orchestration.unified_orchestrator import UnifiedOrchestrator

    logger.warning(
        "AIRoutingService is deprecated. "
        "Use UnifiedOrchestrator from aot.ai.orchestration instead."
    )

    if args:
        facility_id = args[0]
    else:
        facility_id = kwargs.get("facility_id", "default")

    return UnifiedOrchestrator(facility_id)
