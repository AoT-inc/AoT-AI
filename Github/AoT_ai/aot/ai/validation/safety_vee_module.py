# coding=utf-8
"""
SafetyVEEModule — v5.1 GATE_4 Implementation.

Implements GATE_4 (SafetyVEEModule) per 002_DESIGN.yaml Section 7.
Responsibilities:
- Hardware bounds validation
- Operational limits check
- Emergency stop detection
- VEE Validation/Evaluation/Explanation (via VEEModule)

@ANCHOR: SAFETY_VEE_MODULE
@phase 2_gate_4
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

from aot.ai.validation.vee_module import (
    VEEModule,
    VEEResult,
    EvalResult,
    VEEExplanation,
    RiskLevel,
)

logger = logging.getLogger(__name__)


@dataclass
class SafetyCheckResult:
    """
    Result of safety checks (hardware bounds, operational limits, emergency stop).
    """
    passed: bool
    check_type: str
    details: str
    blocked: bool = False
    block_reason: Optional[str] = None


@dataclass
class SafetyValidationResult:
    """
    Combined result of all GATE_4 safety validations.
    """
    vee_result: VEEResult
    hardware_passed: bool
    operational_passed: bool
    emergency_stop_passed: bool
    overall_passed: bool
    warnings: List[str] = field(default_factory=list)
    blocked: bool = False
    block_reason: Optional[str] = None


class SafetyVEEModule:
    """
    SafetyVEEModule — GATE_4 Implementation.

    Responsibilities (per DESIGN Section 7):
    - Hardware bounds verification
    - Operational limits confirmation
    - Emergency stop condition detection
    - VEE Validation: intent match check
    - VEE Evaluation: outcome bounds check
    - VEE Explanation: traceable explanation generation

    @phase 2_gate_4
    @stability beta
    """

    # Emergency stop conditions (critical patterns that should block action)
    EMERGENCY_STOP_PATTERNS = [
        "emergency",
        "stop",
        "halt",
        "shutdown",
        "critical",
        "danger",
        "fire",
        "flood",
        "gas_leak",
        "power_failure",
    ]

    # Hardware safety limits per device type
    HARDWARE_LIMITS = {
        "temperature_control": {
            "min_temp": 0.0,
            "max_temp": 100.0,
            "max_rate": 5.0,  # degrees per minute
        },
        "humidity_control": {
            "min_humidity": 0.0,
            "max_humidity": 100.0,
            "max_rate": 10.0,  # percent per minute
        },
        "lighting": {
            "min_intensity": 0.0,
            "max_intensity": 100.0,
            "max_transition_rate": 20.0,
        },
        "generic": {
            "max_duration": 86400,  # 24 hours
            "max_retries": 3,
        },
    }

    # Operational limits (policy-based)
    OPERATIONAL_LIMITS = {
        "max_concurrent_actions": 5,
        "max_action_duration_seconds": 7200,  # 2 hours
        "require_user_confirm_duration": 3600,  # 1 hour+
        "maintenance_window_start": 22,  # 10 PM
        "maintenance_window_end": 6,  # 6 AM
    }

    def __init__(self):
        """Initialize SafetyVEEModule."""
        self._vee = VEEModule()
        self._facility_safety_config: Dict[str, Any] = {}
        logger.info("SafetyVEEModule: INITIALIZED")

    # -------------------------------------------------------------------------
    # GATE_4 Entry Point — Full Safety Validation
    # -------------------------------------------------------------------------

    def validate_action(
        self,
        action_id: str,
        parameters: Dict[str, Any],
        intent: str,
        context_data: Dict[str, Any],
    ) -> SafetyValidationResult:
        """
        GATE_4 Primary Entry Point: Full safety validation.

        Executes in sequence:
        1. Hardware bounds check
        2. Operational limits check
        3. Emergency stop check
        4. VEE Validation (via VEEModule)
        5. VEE Evaluation (via VEEModule)

        Only proceeds to VEE if hardware/operational/emergency checks pass.

        Args:
            action_id: Action identifier
            parameters: Normalized action parameters
            intent: User intent string
            context_data: Current context data

        Returns:
            SafetyValidationResult with all check results
        """
        logger.info(f"SVM.validate_action: START action_id={action_id}")

        all_warnings = []
        blocked = False
        block_reason = None

        # Step 1: Hardware bounds check
        hardware_result = self.check_hardware_bounds(action_id, parameters)
        if not hardware_result.passed:
            blocked = True
            block_reason = f"HARDWARE BOUNDS: {hardware_result.details}"
            all_warnings.extend(hardware_result.details.split("; "))

        # Step 2: Operational limits check
        operational_result = self.check_operational_limits(action_id, parameters)
        if not operational_result.passed:
            blocked = True
            block_reason = f"OPERATIONAL LIMITS: {operational_result.details}"
            all_warnings.extend(operational_result.details.split("; "))

        # Step 3: Emergency stop check
        emergency_result = self.check_emergency_stop(action_id, parameters)
        if not emergency_result.passed:
            blocked = True
            block_reason = f"EMERGENCY STOP: {emergency_result.details}"
            all_warnings.append(emergency_result.details)

        # Step 4-5: VEE Validation and Evaluation (only if safety checks pass)
        vee_result: Optional[VEEResult] = None
        eval_result: Optional[EvalResult] = None

        if not blocked:
            # VEE Validation
            vee_result = self._vee.validate(parameters, intent)

            # VEE Evaluation
            eval_result = self._vee.evaluate(parameters, context_data)

            # Add warnings
            if vee_result.warnings:
                all_warnings.extend(vee_result.warnings)

            # Check if VEE blocked
            if vee_result.blocked:
                blocked = True
                block_reason = vee_result.block_reason

        # Determine overall pass
        overall_passed = (
            hardware_result.passed
            and operational_result.passed
            and emergency_result.passed
            and (not vee_result or vee_result.passed)
            and (not eval_result or eval_result.outcome_within_bounds)
        )

        result = SafetyValidationResult(
            vee_result=vee_result or VEEResult(
                intent_match_score=0.0,
                passed=False,
                blocked=blocked,
                block_reason=block_reason,
            ),
            hardware_passed=hardware_result.passed,
            operational_passed=operational_result.passed,
            emergency_stop_passed=emergency_result.passed,
            overall_passed=overall_passed,
            warnings=all_warnings,
            blocked=blocked,
            block_reason=block_reason,
        )

        logger.info(
            f"SVM.validate_action: END overall_passed={overall_passed}, "
            f"blocked={blocked}"
        )

        return result

    # -------------------------------------------------------------------------
    # VEE Interface Delegation
    # -------------------------------------------------------------------------

    def validate(self, parameters: Dict[str, Any], intent: str) -> VEEResult:
        """
        VEE Validation: Check if action matches user intent.

        Delegates to VEEModule.validate().

        Args:
            parameters: Action parameters
            intent: User intent string

        Returns:
            VEEResult with intent match score
        """
        return self._vee.validate(parameters, intent)

    def evaluate(
        self, parameters: Dict[str, Any], context_data: Dict[str, Any]
    ) -> EvalResult:
        """
        VEE Evaluation: Check if predicted outcome is within safe bounds.

        Delegates to VEEModule.evaluate().

        Args:
            parameters: Action parameters
            context_data: Current context

        Returns:
            EvalResult with risk assessment
        """
        return self._vee.evaluate(parameters, context_data)

    def explain(
        self,
        parameters: Dict[str, Any],
        context_data: Dict[str, Any],
        vee_result: Optional[VEEResult] = None,
        eval_result: Optional[EvalResult] = None,
    ) -> VEEExplanation:
        """
        VEE Explanation: Generate traceable human-readable explanation.

        Delegates to VEEModule.explain().

        Args:
            parameters: Action parameters
            context_data: Current context
            vee_result: Optional VEE validation result
            eval_result: Optional VEE evaluation result

        Returns:
            VEEExplanation with summary and details
        """
        return self._vee.explain(parameters, context_data, vee_result, eval_result)

    # -------------------------------------------------------------------------
    # Safety Check Implementations
    # -------------------------------------------------------------------------

    def check_hardware_bounds(self, action_id: str, parameters: Dict[str, Any]) -> SafetyCheckResult:
        """
        Hardware bounds verification.

        Checks if action parameters are within hardware safety limits.

        Args:
            action_id: Action identifier
            parameters: Action parameters

        Returns:
            SafetyCheckResult
        """
        logger.debug(f"SVM.check_hardware_bounds: action_id={action_id}")

        # Determine device type from action_id
        device_type = self._infer_device_type(action_id)
        limits = self.HARDWARE_LIMITS.get(device_type, self.HARDWARE_LIMITS["generic"])

        violations = []

        # Check temperature bounds
        if "temperature" in parameters:
            temp = parameters["temperature"]
            if temp < limits.get("min_temp", 0):
                violations.append(
                    f"Temperature {temp} below minimum {limits['min_temp']}"
                )
            if temp > limits.get("max_temp", 100):
                violations.append(
                    f"Temperature {temp} exceeds maximum {limits['max_temp']}"
                )

        # Check humidity bounds
        if "humidity" in parameters:
            humid = parameters["humidity"]
            if humid < limits.get("min_humidity", 0):
                violations.append(
                    f"Humidity {humid} below minimum {limits['min_humidity']}"
                )
            if humid > limits.get("max_humidity", 100):
                violations.append(
                    f"Humidity {humid} exceeds maximum {limits['max_humidity']}"
                )

        # Check light intensity bounds
        if "light_intensity" in parameters:
            intensity = parameters["light_intensity"]
            if intensity < limits.get("min_intensity", 0):
                violations.append(
                    f"Light intensity {intensity} below minimum {limits['min_intensity']}"
                )
            if intensity > limits.get("max_intensity", 100):
                violations.append(
                    f"Light intensity {intensity} exceeds maximum {limits['max_intensity']}"
                )

        # Check duration bounds
        if "duration" in parameters:
            duration = parameters["duration"]
            max_duration = limits.get("max_duration", 86400)
            if duration > max_duration:
                violations.append(
                    f"Duration {duration}s exceeds maximum {max_duration}s"
                )

        passed = len(violations) == 0
        details = "; ".join(violations) if violations else "All bounds OK"

        return SafetyCheckResult(
            passed=passed,
            check_type="hardware_bounds",
            details=details,
            blocked=not passed,
            block_reason=None if passed else details,
        )

    def check_operational_limits(self, action_id: str, parameters: Dict[str, Any]) -> SafetyCheckResult:
        """
        Operational limits verification.

        Checks if action conforms to operational policies.

        Args:
            action_id: Action identifier
            parameters: Action parameters

        Returns:
            SafetyCheckResult
        """
        logger.debug(f"SVM.check_operational_limits: action_id={action_id}")

        violations = []
        limits = self.OPERATIONAL_LIMITS

        # Check duration limits
        if "duration" in parameters:
            duration = parameters["duration"]
            max_duration = limits["max_action_duration_seconds"]
            if duration > max_duration:
                violations.append(
                    f"Duration {duration}s exceeds operational limit {max_duration}s"
                )

            # Flag for user confirmation if very long
            if duration > limits["require_user_confirm_duration"]:
                violations.append(
                    f"Long duration ({duration}s) requires explicit user confirmation"
                )

        # Check maintenance window (warning only, not blocking)
        from datetime import datetime
        current_hour = datetime.now().hour
        if limits["maintenance_window_start"] <= current_hour or current_hour < limits["maintenance_window_end"]:
            # During maintenance window - add warning but don't block
            logger.debug(f"SVM: Action during maintenance window (hour={current_hour})")

        # Check retry limits
        if "retries" in parameters:
            retries = parameters["retries"]
            max_retries = limits.get("max_retries", 3)
            if retries > max_retries:
                violations.append(
                    f"Retries {retries} exceeds limit {max_retries}"
                )

        passed = len(violations) == 0
        details = "; ".join(violations) if violations else "All limits OK"

        return SafetyCheckResult(
            passed=passed,
            check_type="operational_limits",
            details=details,
            blocked=not passed,
            block_reason=None if passed else details,
        )

    def check_emergency_stop(self, action_id: str, parameters: Dict[str, Any]) -> SafetyCheckResult:
        """
        Emergency stop condition detection.

        Checks if action or parameters indicate emergency conditions
        that should be blocked.

        Args:
            action_id: Action identifier
            parameters: Action parameters

        Returns:
            SafetyCheckResult
        """
        logger.debug(f"SVM.check_emergency_stop: action_id={action_id}")

        # Check action_id for emergency patterns
        action_lower = action_id.lower()
        for pattern in self.EMERGENCY_STOP_PATTERNS:
            if pattern in action_lower:
                return SafetyCheckResult(
                    passed=False,
                    check_type="emergency_stop",
                    details=f"Emergency stop pattern detected: '{pattern}' in action_id",
                    blocked=True,
                    block_reason=f"Emergency pattern: {pattern}",
                )

        # Check parameters for emergency indicators
        emergency_param_keys = ["emergency", "stop", "halt", "critical"]
        for key in emergency_param_keys:
            if key in parameters:
                value = parameters[key]
                if isinstance(value, bool) and value:
                    return SafetyCheckResult(
                        passed=False,
                        check_type="emergency_stop",
                        details=f"Emergency flag set: {key}={value}",
                        blocked=True,
                        block_reason=f"Emergency flag: {key}",
                    )
                if isinstance(value, str) and value.lower() in self.EMERGENCY_STOP_PATTERNS:
                    return SafetyCheckResult(
                        passed=False,
                        check_type="emergency_stop",
                        details=f"Emergency value detected: {key}={value}",
                        blocked=True,
                        block_reason=f"Emergency value: {key}={value}",
                    )

        # Check for dangerous action combinations
        if self._is_dangerous_combination(parameters):
            return SafetyCheckResult(
                passed=False,
                check_type="emergency_stop",
                details="Dangerous parameter combination detected",
                blocked=True,
                block_reason="Dangerous parameter combination",
            )

        return SafetyCheckResult(
            passed=True,
            check_type="emergency_stop",
            details="No emergency conditions detected",
            blocked=False,
            block_reason=None,
        )

    def _infer_device_type(self, action_id: str) -> str:
        """
        Infer device type from action identifier.

        Args:
            action_id: Action identifier

        Returns:
            Device type string
        """
        action_lower = action_id.lower()

        if "temperature" in action_lower or "temp" in action_lower:
            return "temperature_control"
        elif "humidity" in action_lower or "humid" in action_lower:
            return "humidity_control"
        elif "light" in action_lower or "lamp" in action_lower:
            return "lighting"
        else:
            return "generic"

    def _is_dangerous_combination(self, parameters: Dict[str, Any]) -> bool:
        """
        Check for dangerous parameter combinations.

        Args:
            parameters: Action parameters

        Returns:
            True if combination is dangerous
        """
        # Check for conflicting extreme values
        has_extreme_temp = parameters.get("temperature", 50) < 10 or parameters.get("temperature", 50) > 90
        has_extreme_humidity = parameters.get("humidity", 50) < 10 or parameters.get("humidity", 50) > 90

        if has_extreme_temp and has_extreme_humidity:
            # Both extreme - could indicate sensor error or dangerous conditions
            return True

        return False
