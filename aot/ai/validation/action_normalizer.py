# coding=utf-8
"""
ActionNormalizer — v5.1 GATE_2 Implementation.

Implements GATE_2 (ActionNormalizer) per 002_DESIGN.yaml Section 7.
Responsibilities:
- Parameter validation against device specs
- Device capability mapping
- Executor type determination (virtual/physical/MCP)

@ANCHOR: ACTION_NORMALIZER
@phase 2_gate_2
"""
import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ExecutorType(Enum):
    """Executor types for action execution."""
    VIRTUAL = "virtual"      # Software/simulation execution
    PHYSICAL = "physical"   # Direct hardware control
    MCP = "MCP"             # Model Context Protocol execution


@dataclass
class ValidationResult:
    """
    Schema: ValidationResult per 002_DESIGN.yaml Section 6.
    Output of ActionNormalizer.validate_parameters().
    """
    passed: bool
    violations: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    adjusted_parameters: Optional[Dict[str, Any]] = None


@dataclass
class NormalizedAction:
    """
    Schema: NormalizedAction per 002_DESIGN.yaml Section 6.
    Output of ActionNormalizer.normalize().
    """
    action_id: str
    parameters: Dict[str, Any]
    device_capabilities: List[str]
    executor_type: ExecutorType


@dataclass
class DeviceSpec:
    """
    Device specification for validation.
    Used internally for parameter bounds checking.
    """
    device_id: str
    device_type: str
    capabilities: List[str]
    parameter_bounds: Dict[str, Dict[str, Any]]  # e.g., {"temperature": {"min": 0, "max": 100}}


class ActionNormalizer:
    """
    ActionNormalizer — GATE_2 Implementation.

    Responsibilities (per DESIGN Section 7):
    - Parameter validation against device specs
    - Device capability mapping
    - Executor type determination (virtual/physical/MCP)

    @phase 2_gate_2
    @stability beta
    """

    # Default parameter bounds for common device types
    DEFAULT_BOUNDS = {
        "temperature": {"min": 0.0, "max": 100.0, "unit": "celsius"},
        "humidity": {"min": 0.0, "max": 100.0, "unit": "percent"},
        "light_intensity": {"min": 0.0, "max": 100.0, "unit": "percent"},
        "duration": {"min": 0, "max": 86400, "unit": "seconds"},
        "threshold": {"min": 0.0, "max": 1.0, "unit": "ratio"},
    }

    def __init__(self):
        """Initialize ActionNormalizer."""
        self._device_registry: Dict[str, DeviceSpec] = {}
        logger.info("ActionNormalizer: INITIALIZED")

    # -------------------------------------------------------------------------
    # Public API — Normalization
    # -------------------------------------------------------------------------

    def normalize(
        self, action_id: str, parameters: Dict[str, Any], device_id: Optional[str] = None
    ) -> NormalizedAction:
        """
        Normalize an action for execution.

        GATE_2 Primary Entry Point:
        1. Validate parameters against device specs
        2. Map device capabilities
        3. Determine executor type

        Args:
            action_id: Unique action identifier
            parameters: Action parameters dict
            device_id: Optional target device identifier

        Returns:
            NormalizedAction ready for execution

        Raises:
            ValueError: If validation fails
        """
        logger.info(f"AN.normalize: START action_id={action_id}, device_id={device_id}")

        # Get device spec (from registry or build default)
        device_spec = self._get_device_spec(device_id, action_id)

        # Validate parameters
        validation_result = self.validate_parameters(parameters, device_spec)
        if not validation_result.passed:
            logger.warning(
                f"AN.normalize: VALIDATION FAILED violations={validation_result.violations}"
            )
            raise ValueError(
                f"Parameter validation failed: {validation_result.violations}. "
                f"Suggestions: {validation_result.suggestions}"
            )

        # Use adjusted parameters if provided
        final_parameters = validation_result.adjusted_parameters or parameters

        # Determine executor type
        executor_type = self._determine_executor_type(device_spec, action_id)

        # Map device capabilities
        capabilities = device_spec.capabilities if device_spec else []

        normalized = NormalizedAction(
            action_id=action_id,
            parameters=final_parameters,
            device_capabilities=capabilities,
            executor_type=executor_type,
        )

        logger.info(
            f"AN.normalize: END executor_type={executor_type.value}, "
            f"capabilities={len(capabilities)}"
        )

        return normalized

    def validate_parameters(
        self, parameters: Dict[str, Any], device_spec: Optional[DeviceSpec] = None
    ) -> ValidationResult:
        """
        Validate action parameters against device specifications.

        Args:
            parameters: Action parameters to validate
            device_spec: Device specification for bounds checking

        Returns:
            ValidationResult with passed/violations/suggestions
        """
        violations = []
        suggestions = []
        adjusted_parameters = {}

        # Check each parameter against bounds
        bounds = self.DEFAULT_BOUNDS.copy()
        if device_spec and device_spec.parameter_bounds:
            # Device-specific bounds override defaults
            bounds.update(device_spec.parameter_bounds)

        for param_name, param_value in parameters.items():
            if param_name in bounds:
                bounds_spec = bounds[param_name]
                min_val = bounds_spec.get("min")
                max_val = bounds_spec.get("max")

                # Numeric validation
                if isinstance(param_value, (int, float)):
                    if min_val is not None and param_value < min_val:
                        violations.append(
                            f"Parameter '{param_name}' value {param_value} below minimum {min_val}"
                        )
                        suggestions.append(
                            f"Adjust '{param_name}' to minimum allowed value: {min_val}"
                        )
                        adjusted_parameters[param_name] = min_val
                    elif max_val is not None and param_value > max_val:
                        violations.append(
                            f"Parameter '{param_name}' value {param_value} exceeds maximum {max_val}"
                        )
                        suggestions.append(
                            f"Adjust '{param_name}' to maximum allowed value: {max_val}"
                        )
                        adjusted_parameters[param_name] = max_val
                    else:
                        adjusted_parameters[param_name] = param_value
                else:
                    # Non-numeric parameter, pass through
                    adjusted_parameters[param_name] = param_value
            else:
                # Unknown parameter, pass through with warning
                adjusted_parameters[param_name] = param_value
                logger.debug(f"AN.validate_parameters: unknown parameter '{param_name}'")

        passed = len(violations) == 0

        # If violations were adjusted, include the adjusted parameters
        if violations and not adjusted_parameters:
            adjusted_parameters = None

        return ValidationResult(
            passed=passed,
            violations=violations,
            suggestions=suggestions,
            adjusted_parameters=adjusted_parameters if violations else None,
        )

    # -------------------------------------------------------------------------
    # Device Registry Management
    # -------------------------------------------------------------------------

    def register_device(self, device_spec: DeviceSpec) -> None:
        """
        Register a device specification for validation.

        Args:
            device_spec: Device specification to register
        """
        self._device_registry[device_spec.device_id] = device_spec
        logger.debug(f"AN.register_device: registered device_id={device_spec.device_id}")

    def _get_device_spec(
        self, device_id: Optional[str], action_id: str
    ) -> Optional[DeviceSpec]:
        """
        Get device specification from registry or build default.

        Args:
            device_id: Device identifier
            action_id: Action identifier (used to infer device type)

        Returns:
            DeviceSpec or None if not found
        """
        if device_id and device_id in self._device_registry:
            return self._device_registry[device_id]

        # Build default spec based on action_id prefix
        default_spec = self._build_default_spec(action_id)
        return default_spec

    def _build_default_spec(self, action_id: str) -> DeviceSpec:
        """
        Build a default device specification based on action type.

        Args:
            action_id: Action identifier

        Returns:
            Default DeviceSpec
        """
        # Infer device type from action_id patterns
        action_lower = action_id.lower()

        if "temperature" in action_lower or "temp" in action_lower:
            return DeviceSpec(
                device_id="default_temp",
                device_type="temperature_control",
                capabilities=["read_temperature", "write_temperature"],
                parameter_bounds={"temperature": self.DEFAULT_BOUNDS["temperature"]},
            )
        elif "humidity" in action_lower or "humid" in action_lower:
            return DeviceSpec(
                device_id="default_humid",
                device_type="humidity_control",
                capabilities=["read_humidity", "write_humidity"],
                parameter_bounds={"humidity": self.DEFAULT_BOUNDS["humidity"]},
            )
        elif "light" in action_lower or "lamp" in action_lower:
            return DeviceSpec(
                device_id="default_light",
                device_type="lighting",
                capabilities=["read_light", "write_light"],
                parameter_bounds={"light_intensity": self.DEFAULT_BOUNDS["light_intensity"]},
            )
        elif "mcp" in action_lower:
            return DeviceSpec(
                device_id="default_mcp",
                device_type="mcp_device",
                capabilities=["mcp_execute"],
                parameter_bounds={},
            )
        else:
            # Generic virtual device
            return DeviceSpec(
                device_id="default_virtual",
                device_type="virtual",
                capabilities=["virtual_execute"],
                parameter_bounds={},
            )

    # -------------------------------------------------------------------------
    # Executor Type Determination
    # -------------------------------------------------------------------------

    def _determine_executor_type(
        self, device_spec: Optional[DeviceSpec], action_id: str
    ) -> ExecutorType:
        """
        Determine the appropriate executor type for an action.

        Logic (per DESIGN Section 7):
        - MCP: If device has MCP capability or action_id contains "mcp"
        - PHYSICAL: If device has physical hardware capabilities
        - VIRTUAL: Default for software/simulation

        Args:
            device_spec: Device specification
            action_id: Action identifier

        Returns:
            ExecutorType enum value
        """
        action_lower = action_id.lower()

        # Check for MCP indicators
        if device_spec:
            if "mcp_execute" in device_spec.capabilities:
                return ExecutorType.MCP
            if device_spec.device_type in ["physical", "hardware", "controller"]:
                return ExecutorType.PHYSICAL

        # Check action_id patterns
        if "mcp" in action_lower:
            return ExecutorType.MCP
        if "physical" in action_lower or "hardware" in action_lower:
            return ExecutorType.PHYSICAL
        if "virtual" in action_lower or "simulate" in action_lower:
            return ExecutorType.VIRTUAL

        # Default to virtual
        return ExecutorType.VIRTUAL
