# coding=utf-8
"""
AdvisoryLanguageValidator — v5.1 GATE_1 Implementation.

Implements GATE_1 (AdvisoryLanguageValidator) per 002_DESIGN.yaml Section 7.
Responsibilities:
- Detect prohibited directive/imperative language patterns
- Verify advisory framing in AI-generated routing decisions
- Attach confidence level to routing decisions
- Block routing progression if advisory language validation fails

@ANCHOR: ADVISORY_LANGUAGE_VALIDATOR
@phase 2_gate_1
"""
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """
    Schema: ValidationResult per 002_DESIGN.yaml Section 6.
    Output of AdvisoryLanguageValidator.validate().

    Attributes:
        passed: True if validation passed, False otherwise
        violations: List of violation descriptions
        suggestions: List of rephrasing suggestions
        confidence_score: Optional confidence level (0.0-1.0) for the validation
    """
    passed: bool
    violations: List[str] = field(default_factory=list)
    suggestions: List[str] = field(default_factory=list)
    confidence_score: Optional[float] = None


@dataclass
class AdvisoryCheckResult:
    """
    Detailed advisory language check result.
    Provides granular information about advisory pattern detection.
    """
    has_prohibited_patterns: bool
    has_advisory_framing: bool
    is_trivial_query: bool
    detected_prohibited: List[str] = field(default_factory=list)
    detected_advisory: List[str] = field(default_factory=list)


class AdvisoryLanguageValidator:
    """
    AdvisoryLanguageValidator — GATE_1 Implementation.

    Responsibilities (per DESIGN Section 7, GATE_1):
    - Detect prohibited directive/imperative language patterns
    - Verify advisory framing in AI-generated routing decisions
    - Attach confidence level to routing decisions
    - Block routing progression if advisory language validation fails

    Prohibited Patterns (imperative/directive language):
    - "Activate...", "Set temperature to...", "Turn on...", "Must change..."
    - Chinese: "你应该", "你必须"

    Required Patterns (advisory language):
    - "You may consider...", "Based on...", "Would you like me to...", "I suggest..."
    - Chinese: "可以考虑", "建议"

    Validation Rules (per DESIGN Section 7, GATE_1):
    - Prohibited patterns: MUST NOT be present (hard block)
    - Advisory framing: MUST be present for Tier 1+ queries (soft suggestion for Tier 0)
    - Trivial queries (Tier 0): Exempt from advisory framing requirement

    @phase 2_gate_1
    @stability stable
    """

    # Prohibited patterns — directive/imperative language that must be blocked
    PROHIBITED_PATTERNS = [
        # English imperative commands
        r"\bActivate\b",
        r"\bTurn on\b",
        r"\bTurn off\b",
        r"\bSet temperature to\b",
        r"\bSet\s+\w+\s+to\b",  # Generic "Set X to Y"
        r"\bMust change\b",
        r"\bYou must\b",
        r"\bYou should\b",
        r"\bDo it now\b",
        r"\bImmediately\b",
        # Chinese directive patterns
        r"你应该",
        r"你必须",
        r"马上",
    ]

    # Required patterns — advisory language that should be present
    REQUIRED_PATTERNS = [
        # English advisory phrases
        r"You may consider",
        r"Based on",
        r"Would you like me to",
        r"I suggest",
        r"I recommend",
        r"It appears that",
        r"You might want to",
        r"You could",
        # Chinese advisory phrases
        r"可以考虑",
        r"建议",
        r"我认为",
        r"或许可以",
    ]

    # Trivial query patterns — exempt from advisory framing requirement
    TRIVIAL_QUERY_PATTERNS = [
        # English greetings/short queries
        r"^hello$",
        r"^hi$",
        r"^hey$",
        r"good morning",
        r"good afternoon",
        r"good evening",
        r"what time is it",
        r"who are you",
        r"^help$",
        r"^help me$",
        r"what can you do",
        r"how are you",
        # Korean greetings/short queries
        r"^안녕",
        r"^안녕하세요",
        r"시간",
        r"whoami",
        r"^도움$",
        # Chinese greetings/short queries
        r"你好",
        r"几点",
        r"你是谁",
    ]

    def __init__(self, strict_mode: bool = True):
        """
        Initialize AdvisoryLanguageValidator.

        Args:
            strict_mode: If True, blocks on prohibited patterns.
                        If False, only warns (for testing/debugging).
        """
        self._strict_mode = strict_mode
        self._prohibited_regex = [re.compile(p, re.IGNORECASE) for p in self.PROHIBITED_PATTERNS]
        self._required_regex = [re.compile(p, re.IGNORECASE) for p in self.REQUIRED_PATTERNS]
        self._trivial_regex = [re.compile(p, re.IGNORECASE) for p in self.TRIVIAL_QUERY_PATTERNS]
        logger.info(f"AdvisoryLanguageValidator: INITIALIZED (strict_mode={strict_mode})")

    # -------------------------------------------------------------------------
    # Public API — Validation
    # -------------------------------------------------------------------------

    def validate(self, text: str) -> ValidationResult:
        """
        Validate text for advisory language compliance.

        GATE_1 Primary Entry Point:
        1. Check for prohibited directive patterns
        2. Check for advisory framing patterns
        3. Determine if trivial query (Tier 0 exempt)
        4. Calculate confidence score
        5. Return ValidationResult with violations/suggestions

        Args:
            text: Text to validate (user query or AI response)

        Returns:
            ValidationResult with passed/violations/suggestions/confidence_score
        """
        logger.info(f"ALV.validate: START text={text[:50]}...")

        violations = []
        suggestions = []
        detected_prohibited = []
        detected_advisory = []

        text_lower = text.lower()

        # Step 1: Check prohibited patterns
        for regex in self._prohibited_regex:
            match = regex.search(text)
            if match:
                pattern_str = match.group(0)
                detected_prohibited.append(pattern_str)
                violations.append(f"Prohibited directive pattern detected: '{pattern_str}'")
                suggestions.append(
                    "Consider rephrasing with advisory language like "
                    "'Would you like me to...' or 'I suggest...'"
                )

        # Step 2: Check for advisory framing
        is_trivial = self._is_trivial_query(text)
        has_advisory = any(regex.search(text) for regex in self._required_regex)

        if has_advisory:
            for regex in self._required_regex:
                match = regex.search(text)
                if match:
                    detected_advisory.append(match.group(0))

        # Step 3: Advisory framing required for non-trivial queries
        if not is_trivial and not has_advisory:
            suggestions.append(
                "Consider using advisory framing: 'You may consider...', "
                "'Based on...', 'I suggest...'"
            )

        # Step 4: Calculate confidence score
        confidence_score = self._calculate_confidence(
            has_prohibited=len(detected_prohibited) > 0,
            has_advisory=has_advisory,
            is_trivial=is_trivial,
        )

        passed = len(violations) == 0

        # In strict mode, prohibited patterns always fail
        if self._strict_mode and violations:
            passed = False

        result = ValidationResult(
            passed=passed,
            violations=violations,
            suggestions=suggestions,
            confidence_score=confidence_score,
        )

        logger.info(
            f"ALV.validate: END passed={passed}, violations={len(violations)}, "
            f"confidence={confidence_score:.3f}"
        )

        return result

    def check(self, text: str) -> AdvisoryCheckResult:
        """
        Perform detailed advisory language check without blocking.

        Use this for detailed analysis and debugging.

        Args:
            text: Text to check

        Returns:
            AdvisoryCheckResult with granular pattern detection results
        """
        detected_prohibited = []
        detected_advisory = []

        for regex in self._prohibited_regex:
            match = regex.search(text)
            if match:
                detected_prohibited.append(match.group(0))

        for regex in self._required_regex:
            match = regex.search(text)
            if match:
                detected_advisory.append(match.group(0))

        is_trivial = self._is_trivial_query(text)

        return AdvisoryCheckResult(
            has_prohibited_patterns=len(detected_prohibited) > 0,
            has_advisory_framing=len(detected_advisory) > 0,
            is_trivial_query=is_trivial,
            detected_prohibited=detected_prohibited,
            detected_advisory=detected_advisory,
        )

    def is_compliant(self, text: str) -> bool:
        """
        Quick compliance check (pass/fail only).

        Args:
            text: Text to check

        Returns:
            True if text is advisory language compliant, False otherwise
        """
        return self.validate(text).passed

    # -------------------------------------------------------------------------
    # Internal Helper Methods
    # -------------------------------------------------------------------------

    def _is_trivial_query(self, text: str) -> bool:
        """
        Check if text represents a trivial query (Tier 0 exempt).

        Trivial queries include:
        - Greetings
        - Time queries
        - Identity questions
        - Simple help requests

        Args:
            text: Text to check

        Returns:
            True if text is trivial, False otherwise
        """
        text_stripped = text.strip().lower()

        for regex in self._trivial_regex:
            if regex.search(text_stripped):
                return True

        return False

    def _calculate_confidence(
        self,
        has_prohibited: bool,
        has_advisory: bool,
        is_trivial: bool,
    ) -> float:
        """
        Calculate confidence score for the validation result.

        Logic:
        - No violations + advisory framing = high confidence (0.9)
        - No violations + trivial = medium-high confidence (0.85)
        - No violations + no advisory (non-trivial) = medium confidence (0.7)
        - Has prohibited patterns = low confidence (0.3)

        Args:
            has_prohibited: Whether prohibited patterns were detected
            has_advisory: Whether advisory patterns were detected
            is_trivial: Whether query is trivial (Tier 0)

        Returns:
            Confidence score between 0.0 and 1.0
        """
        if has_prohibited:
            return 0.3

        if has_advisory:
            return 0.9

        if is_trivial:
            return 0.85

        return 0.7

    # -------------------------------------------------------------------------
    # Pattern Management (for runtime configuration)
    # -------------------------------------------------------------------------

    def add_prohibited_pattern(self, pattern: str) -> None:
        """
        Add a prohibited pattern at runtime.

        Args:
            pattern: Regex pattern to add to prohibited list
        """
        self._prohibited_regex.append(re.compile(pattern, re.IGNORECASE))
        logger.debug(f"ALV.add_prohibited_pattern: added '{pattern}'")

    def add_required_pattern(self, pattern: str) -> None:
        """
        Add a required advisory pattern at runtime.

        Args:
            pattern: Regex pattern to add to required list
        """
        self._required_regex.append(re.compile(pattern, re.IGNORECASE))
        logger.debug(f"ALV.add_required_pattern: added '{pattern}'")

    def remove_prohibited_pattern(self, pattern: str) -> bool:
        """
        Remove a prohibited pattern at runtime.

        Args:
            pattern: Regex pattern to remove

        Returns:
            True if pattern was found and removed, False otherwise
        """
        for i, regex in enumerate(self._prohibited_regex):
            if regex.pattern == pattern:
                del self._prohibited_regex[i]
                logger.debug(f"ALV.remove_prohibited_pattern: removed '{pattern}'")
                return True
        return False

    def get_prohibited_patterns(self) -> List[str]:
        """
        Get list of current prohibited patterns.

        Returns:
            List of prohibited pattern strings
        """
        return [r.pattern for r in self._prohibited_regex]

    def get_required_patterns(self) -> List[str]:
        """
        Get list of current required advisory patterns.

        Returns:
            List of required pattern strings
        """
        return [r.pattern for r in self._required_regex]