# coding=utf-8
"""
Backward-Compatibility Shim — VirtualExecutionEngine → VEEModule.

Per 002_DESIGN.yaml Section 11: Shim Mappings.
Maps old import path to new VEEModule.

@deprecated Use VEEModule.validate()/evaluate()/explain() directly
@ANCHOR: VirtualExecutionEngine_SHIM
"""
import warnings
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=DeprecationWarning)

URGENCY_CRITICAL = "CRITICAL"
URGENCY_NORMAL = "NORMAL"


@dataclass
class SimulationRequest:
    """
    Input payload for VirtualExecutionEngine.simulate().
    Preserved for backward compatibility.
    """
    action_payload: Dict[str, Any]
    spatial_snapshot: Dict[str, Any]
    weather_forecast: Dict[str, Any]
    simulation_horizon_minutes: int = 30
    urgency_level: str = URGENCY_NORMAL
    device_profile: Optional[Any] = None


@dataclass
class SimulationResult:
    """
    Advisory output of VirtualExecutionEngine.simulate().
    Preserved for backward compatibility.
    """
    predicted_state_delta: Dict[str, Any] = field(default_factory=dict)
    conflict_flags: List[str] = field(default_factory=list)
    confidence_score: float = 0.0
    proceed_recommended: bool = True
    advisory_only: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "advisory_only", True)


class VirtualExecutionEngine:
    """
    Shim for backward compatibility.

    Old: from aot.ai.services.virtual_execution_engine import VirtualExecutionEngine
    New: from aot.ai.validation.vee_module import VEEModule

    Note:
        This is a compatibility shim. New code should use
        VEEModule.validate()/evaluate()/explain() directly for full v5.1 functionality.
    """

    @staticmethod
    def _build_cache_key(prefix: str, target_id: Optional[str]) -> str:
        """Shim for VirtualExecutionEngine._build_cache_key()"""
        safe_id = target_id or "global"
        return f"vee:{prefix}:{safe_id}"

    @staticmethod
    def _get_cached(key: str) -> Optional[Dict]:
        """Shim for VirtualExecutionEngine._get_cached()"""
        try:
            from aot.aot_flask.extensions import cache
            return cache.get(key)
        except Exception as exc:
            logger.debug("[VEE][CACHE_READ_ERROR] key=%s err=%s", key, exc)
            return None

    @staticmethod
    def _set_cached(key: str, data: Dict, ttl: int) -> None:
        """Shim for VirtualExecutionEngine._set_cached()"""
        try:
            from aot.aot_flask.extensions import cache
            cache.set(key, data, timeout=ttl)
        except Exception as exc:
            logger.debug("[VEE][CACHE_WRITE_ERROR] key=%s err=%s", key, exc)

    def simulate(self, request: SimulationRequest) -> SimulationResult:
        """
        Shim for VirtualExecutionEngine.simulate() → VEEModule validate()/evaluate().

        Args:
            request: SimulationRequest with action_payload, spatial_snapshot,
                    weather_forecast, simulation_horizon_minutes, urgency_level

        Returns:
            SimulationResult (advisory_only=True)
        """
        logger.warning(
            "VirtualExecutionEngine.simulate is deprecated. "
            "Use VEEModule.validate()/evaluate()/explain() directly."
        )

        from aot.ai.validation.vee_module import VEEModule

        vee = VEEModule()

        # URGENCY BYPASS — same logic as original VEE
        if request.urgency_level == URGENCY_CRITICAL:
            logger.warning(
                "[VEE][URGENCY_BYPASS] CRITICAL urgency — VEE skipped."
            )
            return SimulationResult(
                predicted_state_delta={},
                conflict_flags=[],
                confidence_score=1.0,
                proceed_recommended=True,
                advisory_only=True,
            )

        # Build context_data from request
        context_data = {
            'spatial_snapshot': request.spatial_snapshot,
            'weather_forecast': request.weather_forecast,
            'simulation_horizon_minutes': request.simulation_horizon_minutes,
            'device_profile': request.device_profile,
        }

        # Run VEE validation
        vee_result = vee.validate(request.action_payload, intent="")

        # Run VEE evaluation
        eval_result = vee.evaluate(request.action_payload, context_data)

        # Build conflict_flags from VEE results
        conflict_flags: List[str] = []
        if not vee_result.passed:
            conflict_flags.append("VEE_VALIDATION_FAILED")
        if vee_result.warnings:
            for w in vee_result.warnings:
                conflict_flags.append(f"VEE_WARNING:{w}")
        if eval_result.risk_level.value in ("HIGH", "CRITICAL"):
            conflict_flags.append(f"RISK:{eval_result.risk_level.value}")

        # Build predicted_state_delta
        predicted_state_delta = {
            "action": request.action_payload.get("action_type", ""),
            "estimated_duration_min": request.simulation_horizon_minutes,
            "expected_outcome": "nominal" if not conflict_flags else "degraded",
            "intent_match_score": vee_result.intent_match_score,
            "risk_level": eval_result.risk_level.value,
        }

        # Determine confidence_score
        confidence_score = vee_result.intent_match_score * eval_result.confidence_ceiling
        if conflict_flags:
            confidence_score = max(0.0, confidence_score - 0.2)

        # Determine proceed_recommended
        proceed_recommended = (
            vee_result.passed
            and eval_result.outcome_within_bounds
            and not conflict_flags
        )

        return SimulationResult(
            predicted_state_delta=predicted_state_delta,
            conflict_flags=conflict_flags,
            confidence_score=round(confidence_score, 3),
            proceed_recommended=proceed_recommended,
            advisory_only=True,
        )
