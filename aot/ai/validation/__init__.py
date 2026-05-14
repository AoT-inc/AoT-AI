# coding=utf-8
"""
AI Validation Layer — v5.1 Advisory Gates.

Exports:
- AdvisoryLanguageValidator (GATE_1)
- ActionNormalizer (GATE_2)
- SafetyVEEModule (GATE_4)
- VEEModule (VEE engine)
"""
from aot.ai.validation.advisory_language_validator import (
    AdvisoryLanguageValidator,
    ValidationResult as ALVValidationResult,
    AdvisoryCheckResult,
)
from aot.ai.validation.action_normalizer import (
    ActionNormalizer,
    NormalizedAction,
    ValidationResult,
    ExecutorType,
)
from aot.ai.validation.safety_vee_module import (
    SafetyVEEModule,
    SafetyValidationResult,
    SafetyCheckResult,
)
from aot.ai.validation.vee_module import (
    VEEModule,
    VEEResult,
    EvalResult,
    VEEExplanation,
    RiskLevel,
)
