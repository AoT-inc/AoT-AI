# coding=utf-8
"""
VEEModule — v5.1 VEE (Validation/Evaluation/Explanation) Engine.

Standalone VEE submodule per 002_DESIGN.yaml Section 7.
Implements:
- VEE Validation: intent match score calculation
- VEE Evaluation: outcome bounds checking
- VEE Explanation: traceable human-readable explanations

SVM (SafetyVEEModule) imports this module for VEE operations.

@ANCHOR: VEE_MODULE
@phase 2_gate_4_vee
"""
import logging
import hashlib
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class RiskLevel(Enum):
    """Risk evaluation levels per DESIGN Section 7."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass
class VEEResult:
    """
    Schema: VEEResult per 002_DESIGN.yaml Section 6.
    Output of VEE.validate().
    """
    intent_match_score: float  # 0.0-1.0
    passed: bool
    warnings: List[str] = field(default_factory=list)
    blocked: bool = False
    block_reason: Optional[str] = None


@dataclass
class EvalResult:
    """
    Schema: EvalResult per 002_DESIGN.yaml Section 6.
    Output of VEE.evaluate().
    """
    outcome_within_bounds: bool
    predicted_deviation: float  # percentage
    risk_level: RiskLevel
    confidence_ceiling: float  # 0.0-1.0


@dataclass
class VEEExplanation:
    """
    Schema: VEEExplanation per DESIGN Section 7.
    Output of VEE.explain().
    """
    summary: str
    validation_detail: str
    evaluation_detail: str
    source_trace: List[str]
    recommendation: str


# VEE Thresholds per DESIGN Section 7
INTENT_MATCH_MINIMUM = 0.75

RISK_EVALUATION_BOUNDS = {
    RiskLevel.LOW: 5.0,        # < 5%
    RiskLevel.MEDIUM: 15.0,    # 5% - 15%
    RiskLevel.HIGH: 25.0,      # 15% - 25%
    RiskLevel.CRITICAL: 100.0, # >= 25%
}


class VEEModule:
    """
    VEEModule — v5.1 VEE Engine.

    Responsibilities (per DESIGN Section 7):
    - VEE Validation: Check if action matches user intent (match_score > threshold)
    - VEE Evaluation: Check if predicted outcome is within safety/production bounds
    - VEE Explanation: Generate traceable human-readable explanations

    @phase 2_gate_4_vee
    @stability beta
    """

    def __init__(self):
        """Initialize VEE Module."""
        self._intent_threshold = INTENT_MATCH_MINIMUM
        logger.info("VEEModule: INITIALIZED")

    # -------------------------------------------------------------------------
    # VEE Validation — Intent Match Check
    # -------------------------------------------------------------------------

    def validate(
        self, action_parameters: Dict[str, Any], user_intent: str
    ) -> VEEResult:
        """
        VEE Validation: Check if action matches user intent.

        Algorithm:
        1. Extract key parameters from action
        2. Compare against user intent keywords
        3. Calculate intent_match_score (0.0-1.0)
        4. Return VEEResult with passed/failed/blocked status

        Args:
            action_parameters: Normalized action parameters
            user_intent: Original user query/intent string

        Returns:
            VEEResult with intent_match_score and status
        """
        logger.info(
            f"VEE.validate: START intent={user_intent[:50]}..., "
            f"params={action_parameters}"
        )

        # Calculate intent match score
        match_score = self._calculate_intent_match(action_parameters, user_intent)

        # Determine pass/fail
        passed = match_score >= self._intent_threshold

        # Check for warnings
        warnings = []
        blocked = False
        block_reason = None

        if match_score < 0.5:
            warnings.append(
                f"Low intent match ({match_score:.2f}). "
                f"Action may not align with user intent."
            )

        if match_score < self._intent_threshold:
            blocked = True
            block_reason = (
                f"Intent match score {match_score:.2f} below threshold "
                f"{self._intent_threshold}"
            )

        result = VEEResult(
            intent_match_score=round(match_score, 3),
            passed=passed,
            warnings=warnings,
            blocked=blocked,
            block_reason=block_reason,
        )

        logger.info(
            f"VEE.validate: END match_score={match_score:.3f}, "
            f"passed={passed}, blocked={blocked}"
        )

        return result

    def _calculate_intent_match(
        self, action_parameters: Dict[str, Any], user_intent: str
    ) -> float:
        """
        Calculate intent match score between action and user intent.

        Algorithm:
        1. Extract keywords from user intent
        2. Match against action parameters
        3. Score based on overlap ratio

        Args:
            action_parameters: Action parameters dict
            user_intent: User intent string

        Returns:
            Float score 0.0-1.0
        """
        if not user_intent:
            return 0.0

        # Normalize intent
        intent_lower = user_intent.lower()
        intent_words = set(
            w.strip() for w in intent_lower.split()
            if len(w.strip()) > 2
        )

        # Remove common stop words
        stop_words = {
            "the", "and", "for", "are", "but", "not", "you", "all",
            "can", "had", "her", "was", "one", "our", "out", "what",
            "have", "this", "that", "with", "from", "would", "there",
            "could", "other", "more", "some", "such", "than", "them",
            "would", "could", "should", "may", "might", "must",
            "consider", "suggest", "recommend", "based", "because",
        }
        intent_keywords = intent_words - stop_words

        if not intent_keywords:
            return 0.5  # Neutral score for empty intent

        # Check parameter keys against intent
        param_keys = set(k.lower() for k in action_parameters.keys())

        # Calculate overlap
        matches = intent_keywords & param_keys
        max_possible = max(len(intent_keywords), len(param_keys))

        if max_possible == 0:
            return 0.5

        # Base score from keyword overlap
        base_score = len(matches) / max_possible

        # Boost if parameter values appear in intent
        value_matches = 0
        for value in action_parameters.values():
            if isinstance(value, (int, float)):
                value_str = str(value)
                if value_str in intent_lower or value_str in intent_words:
                    value_matches += 0.1
            elif isinstance(value, str):
                if value.lower() in intent_lower:
                    value_matches += 0.1

        score = min(1.0, base_score + value_matches)

        return score

    # -------------------------------------------------------------------------
    # VEE Evaluation — Outcome Bounds Check
    # -------------------------------------------------------------------------

    def evaluate(
        self,
        action_parameters: Dict[str, Any],
        context_data: Dict[str, Any],
    ) -> EvalResult:
        """
        VEE Evaluation: Check if predicted outcome is within safe bounds.

        Algorithm:
        1. Predict outcome deviation based on parameters
        2. Calculate risk level based on deviation thresholds
        3. Determine if outcome is within acceptable bounds

        Args:
            action_parameters: Normalized action parameters
            context_data: Current context data for prediction

        Returns:
            EvalResult with risk assessment
        """
        logger.info(f"VEE.evaluate: START params={action_parameters}")

        # Calculate predicted deviation
        deviation = self._predict_deviation(action_parameters, context_data)

        # Determine risk level
        risk_level = self._calculate_risk_level(deviation)

        # Check if within bounds
        outcome_within_bounds = risk_level in [RiskLevel.LOW, RiskLevel.MEDIUM]

        # Calculate confidence ceiling
        confidence_ceiling = self._calculate_confidence_ceiling(
            action_parameters, context_data
        )

        result = EvalResult(
            outcome_within_bounds=outcome_within_bounds,
            predicted_deviation=round(deviation, 2),
            risk_level=risk_level,
            confidence_ceiling=round(confidence_ceiling, 3),
        )

        logger.info(
            f"VEE.evaluate: END deviation={deviation:.2f}%, "
            f"risk={risk_level.value}, within_bounds={outcome_within_bounds}"
        )

        return result

    def _predict_deviation(
        self,
        action_parameters: Dict[str, Any],
        context_data: Dict[str, Any],
    ) -> float:
        """
        Predict outcome deviation percentage.

        Placeholder implementation — actual would use ML model or
        historical data for prediction.

        Args:
            action_parameters: Action parameters
            context_data: Current context

        Returns:
            Predicted deviation percentage
        """
        # Simple heuristic: check for extreme values
        deviation = 0.0

        for key, value in action_parameters.items():
            if isinstance(value, (int, float)):
                # Check if value is at bounds (indicates potential deviation)
                if key in ["temperature", "humidity", "light_intensity"]:
                    # Values near 0 or 100% have higher deviation risk
                    if value < 10 or value > 90:
                        deviation += 2.0
                    elif value < 20 or value > 80:
                        deviation += 1.0
                elif key == "duration":
                    # Long durations have higher deviation
                    if value > 3600:  # > 1 hour
                        deviation += 3.0
                    elif value > 7200:  # > 2 hours
                        deviation += 5.0

        # Context risk factor
        context_risk = context_data.get("risk_factor", 0.0)
        deviation += context_risk

        # Cap at reasonable maximum
        return min(deviation, 50.0)

    def _calculate_risk_level(self, deviation: float) -> RiskLevel:
        """
        Calculate risk level based on deviation percentage.

        Per DESIGN Section 7:
        - LOW: deviation < 5%
        - MEDIUM: 5% <= deviation < 15%
        - HIGH: 15% <= deviation < 25%
        - CRITICAL: deviation >= 25%
        """
        if deviation < RISK_EVALUATION_BOUNDS[RiskLevel.LOW]:
            return RiskLevel.LOW
        elif deviation < RISK_EVALUATION_BOUNDS[RiskLevel.MEDIUM]:
            return RiskLevel.MEDIUM
        elif deviation < RISK_EVALUATION_BOUNDS[RiskLevel.HIGH]:
            return RiskLevel.HIGH
        else:
            return RiskLevel.CRITICAL

    def _calculate_confidence_ceiling(
        self,
        action_parameters: Dict[str, Any],
        context_data: Dict[str, Any],
    ) -> float:
        """
        Calculate confidence ceiling for evaluation.

        Lower confidence if:
        - Context data is sparse
        - Parameters are at extreme values
        - High deviation risk
        """
        confidence = 0.9  # Base confidence

        # Reduce if context is sparse
        if not context_data or len(context_data) < 3:
            confidence *= 0.8

        # Reduce for extreme parameter values
        for key, value in action_parameters.items():
            if isinstance(value, (int, float)):
                if key in ["temperature", "humidity", "light_intensity"]:
                    if value < 10 or value > 90:
                        confidence *= 0.85
                        break

        return confidence

    # -------------------------------------------------------------------------
    # VEE Explanation — Human-Readable Trace
    # -------------------------------------------------------------------------

    def explain(
        self,
        action_parameters: Dict[str, Any],
        context_data: Dict[str, Any],
        vee_result: Optional[VEEResult] = None,
        eval_result: Optional[EvalResult] = None,
    ) -> VEEExplanation:
        """
        VEE Explanation: Generate traceable human-readable explanation.

        Args:
            action_parameters: Action parameters
            context_data: Current context
            vee_result: Optional VEE validation result
            eval_result: Optional VEE evaluation result

        Returns:
            VEEExplanation with summary, details, and recommendation
        """
        logger.info("VEE.explain: START")

        # Build validation detail
        validation_detail = ""
        if vee_result:
            validation_detail = (
                f"Intent match score: {vee_result.intent_match_score:.2f} "
                f"(threshold: {self._intent_threshold}). "
                f"{'PASSED' if vee_result.passed else 'FAILED'}."
            )
            if vee_result.warnings:
                validation_detail += f" Warnings: {'; '.join(vee_result.warnings)}"
        else:
            validation_detail = "Validation not performed."

        # Build evaluation detail
        evaluation_detail = ""
        if eval_result:
            evaluation_detail = (
                f"Predicted deviation: {eval_result.predicted_deviation}%. "
                f"Risk level: {eval_result.risk_level.value}. "
                f"Outcome within bounds: {eval_result.outcome_within_bounds}."
            )
        else:
            evaluation_detail = "Evaluation not performed."

        # Build source trace
        source_trace = self._generate_source_trace(context_data)

        # Build summary and recommendation
        if vee_result and eval_result:
            if vee_result.passed and eval_result.outcome_within_bounds:
                summary = "Action passes VEE checks."
                recommendation = "Proceed with action as planned."
            elif vee_result.blocked:
                summary = "Action blocked due to low intent match."
                recommendation = (
                    f"Review action parameters against user intent. "
                    f"Suggested: clarify intent or adjust parameters."
                )
            else:
                summary = "Action requires review."
                recommendation = (
                    f"Review {eval_result.risk_level.value} risk level. "
                    f"Consider reducing parameter extremes."
                )
        else:
            summary = "VEE checks incomplete."
            recommendation = "Complete validation and evaluation before proceeding."

        explanation = VEEExplanation(
            summary=summary,
            validation_detail=validation_detail,
            evaluation_detail=evaluation_detail,
            source_trace=source_trace,
            recommendation=recommendation,
        )

        logger.info("VEE.explain: END")

        return explanation

    def _generate_source_trace(self, context_data: Dict[str, Any]) -> List[str]:
        """
        Generate source trace for explanation.

        Args:
            context_data: Context data used

        Returns:
            List of trace strings
        """
        trace = []

        # Add context level information
        if "level" in context_data:
            trace.append(f"Context level: {context_data['level']}")

        if "facility_id" in context_data:
            trace.append(f"Facility: {context_data['facility_id']}")

        if "entries" in context_data:
            entries = context_data["entries"]
            if isinstance(entries, list):
                trace.append(f"Context entries: {len(entries)} sources")

        # Generate trace ID
        if context_data:
            data_hash = hashlib.md5(
                str(sorted(context_data.items())).encode()
            ).hexdigest()[:8]
            trace.append(f"Trace ID: {data_hash}")

        return trace
