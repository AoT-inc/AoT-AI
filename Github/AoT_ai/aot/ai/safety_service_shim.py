# coding=utf-8
"""
Backward-Compatibility Shim — SafetyService → SafetyVEEModule.

Per 002_DESIGN.yaml Section 11: Shim Mappings.
Maps old import path to new SafetyVEEModule.

@deprecated Use SafetyVEEModule.validate_action() directly
@ANCHOR: SafetyService_SHIM
"""
import warnings
import logging

logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore", category=DeprecationWarning)


class SafetyService:
    """
    Shim for backward compatibility.

    Old: from aot.ai.services.safety_service import SafetyService
    New: from aot.ai.validation.safety_vee_module import SafetyVEEModule

    Note:
        This is a compatibility shim. New code should use
        SafetyVEEModule.validate_action() directly for full v5.1 functionality.
    """

    # Preserve SAFETY_DEFAULTS from original SafetyService
    SAFETY_DEFAULTS = {
        'max_temperature': 60.0,
        'max_duration_sec': 3600,
        'max_pwm_duty': 100.0,
        'daily_execution_limit': 200,
    }

    @staticmethod
    def validate(action_type, target_id, params):
        """
        Shim for SafetyService.validate() → SafetyVEEModule.validate_action().

        Args:
            action_type: 'output', 'pid', 'function'
            target_id: device unique_id
            params: action parameters dict

        Returns:
            None (raises SafetyViolation on failure)

        Raises:
            SafetyViolation: if any safety check fails
        """
        logger.warning(
            "SafetyService.validate is deprecated. "
            "Use SafetyVEEModule.validate_action() directly."
        )

        from aot.ai.validation.safety_vee_module import SafetyVEEModule
        from aot.ai.services.safety_service import SafetyViolation

        svm = SafetyVEEModule()

        # Build action_id and context_data from legacy parameters
        action_id = f"{action_type}:{target_id}"
        intent = params.get('intent', '')
        context_data = {
            'action_type': action_type,
            'target_id': target_id,
            'params': params
        }

        result = svm.validate_action(action_id, params, intent, context_data)

        if not result.overall_passed:
            violations = []
            if result.block_reason:
                violations.append(result.block_reason)
            violations.extend(result.warnings)
            if violations:
                raise SafetyViolation(violations)

    @staticmethod
    def _check_output_params(target_id, params):
        """Shim for SafetyService._check_output_params() — delegates to SafetyVEEModule"""
        from aot.ai.validation.safety_vee_module import SafetyVEEModule

        svm = SafetyVEEModule()
        result = svm.check_hardware_bounds(f"output:{target_id}", params)

        violations = []
        if not result.passed:
            violations.append(result.details)
        return violations

    @staticmethod
    def _check_pid_params(target_id, params):
        """Shim for SafetyService._check_pid_params() — delegates to SafetyVEEModule"""
        from aot.ai.validation.safety_vee_module import SafetyVEEModule

        svm = SafetyVEEModule()
        result = svm.check_hardware_bounds(f"pid:{target_id}", params)

        violations = []
        if not result.passed:
            violations.append(result.details)
        return violations

    @staticmethod
    def _check_daily_limit(action_type, target_id):
        """Shim for SafetyService._check_daily_limit() — delegates to SafetyVEEModule"""
        from aot.ai.validation.safety_vee_module import SafetyVEEModule

        svm = SafetyVEEModule()
        result = svm.check_operational_limits(f"{action_type}:{target_id}", {})

        violations = []
        if not result.passed:
            violations.append(result.details)
        return violations

    @staticmethod
    def _check_spatial_conflicts(action_type, target_id):
        """Shim for SafetyService._check_spatial_conflicts()"""
        # Spatial conflict check is now part of SafetyVEEModule.validate_action()
        # This method kept for backward compatibility with callers that invoke it directly
        return []
