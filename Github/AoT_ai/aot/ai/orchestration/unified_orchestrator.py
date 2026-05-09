# coding=utf-8
"""
UnifiedOrchestrator — v5.1 Core Orchestration Engine.

Implements the UnifiedOrchestrator component per 002_DESIGN.yaml Section 7.
Coordinates the 5-step lifecycle: ROUTING → PLANNING → RESOLUTION_VALIDATION
→ P4_HUMAN_GATE → DISPATCH.

@ANCHOR: UNIFIED_ORCHESTRATOR
@phase 1_ai_uoc
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

from aot.ai.knowledge.ai_knowledge_base_gateway import (
    KnowledgeBaseGateway,
    MergedContext,
    ConfidenceMetadata,
    ContextLevel,
)
from aot.ai.validation.action_normalizer import ActionNormalizer, NormalizedAction
from aot.ai.validation.advisory_language_validator import AdvisoryLanguageValidator
from aot.ai.validation.safety_vee_module import SafetyVEEModule
from aot.ai.services.ai_action_service import AIActionService
from aot.ai.ui.p4_approval_panel import (
    get_p4_approval_panel,
    ActionSummary as P4ActionSummary,
    SafetyStatus,
    SafetyInfo,
    ConfidenceMetadata as P4ConfidenceMetadata,
    UserDecisionType,
)

logger = logging.getLogger(__name__)


class LifecycleState(Enum):
    """State machine states per DESIGN Section 2."""
    INITIAL = "INITIAL"
    ROUTED = "ROUTED"
    PLANNED = "PLANNED"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    DISPATCHED = "DISPATCHED"


class Tier(Enum):
    """Routing tiers per DESIGN Section 3, Step 1."""
    TIER0 = "Tier0"  # Cached simple response
    TIER1 = "Tier1"  # LLM processable
    TIER2 = "Tier2"  # Requires planner (complex)


@dataclass
class RoutingDecision:
    """
    Schema: RoutingDecision per 002_DESIGN.yaml Section 6.
    Output of UOC.route() — GATE_1.
    """
    tier: Tier
    confidence_score: float  # 0.0-1.0
    reasoning: str
    alternative_tiers_considered: List[Tier] = field(default_factory=list)
    fallback_strategy: Optional[str] = None


@dataclass
class Action:
    """A single action in an action chain."""
    action_id: str
    parameters: Dict[str, Any]
    description: str


@dataclass
class ActionChain:
    """
    Schema: ActionChain per 002_DESIGN.yaml Section 6.
    Output of UOC.plan().
    """
    actions: List[Action]
    estimated_duration: Optional[int] = None  # seconds
    rollback_plan: List[Action] = field(default_factory=list)
    confidence_metadata: Optional[ConfidenceMetadata] = None
    context_sources_used: List[ContextLevel] = field(default_factory=list)


@dataclass
class UserDecision:
    """
    Schema: UserDecision per 002_DESIGN.yaml Section 6.
    Output of P4ApprovalPanel (GATE_3).
    """
    decision: str  # CONFIRM | MODIFY | DISMISS | TIMEOUT
    edited_actions: Optional[List[Action]] = None
    user_notes: Optional[str] = None


class UnifiedOrchestrator:
    """
    UnifiedOrchestrator — v5.1 Core Orchestration Engine.

    Responsibilities (per DESIGN Section 7):
    - Tier 0/1/2 routing
    - KnowledgeBaseGateway context assembly
    - Action chain generation
    - GATE_1 coordination

    Lifecycle Coordination (per DESIGN Section 7):
    - Step 1: route() via GATE_1
    - Step 2: plan() via KBG
    - Step 3: resolve_actions() via GATE_2, GATE_4
    - Step 4: delegate to P4ApprovalPanel
    - Step 5: delegate to DAEMON

    @phase active
    @stability stable
    """

    def __init__(self, facility_id: str):
        """
        Initialize UnifiedOrchestrator for a facility.

        Args:
            facility_id: Target facility identifier
        """
        self.facility_id = facility_id
        self.state = LifecycleState.INITIAL
        self.kbg = KnowledgeBaseGateway(facility_id)
        self._advisory_validator = AdvisoryLanguageValidator()  # GATE_1
        self._action_normalizer = ActionNormalizer()  # GATE_2
        self._safety_vee = SafetyVEEModule()  # GATE_4
        self._current_routing: Optional[RoutingDecision] = None
        self._current_context: Optional[MergedContext] = None
        self._current_action_chain: Optional[ActionChain] = None

        logger.info(
            f"UnifiedOrchestrator: INITIALIZED for facility={facility_id}"
        )

    # -------------------------------------------------------------------------
    # Step 1: ROUTING — GATE_1 (AdvisoryLanguageValidator)
    # -------------------------------------------------------------------------

    def route(self, query: str) -> RoutingDecision:
        """
        Step 1: Route query to appropriate Tier.

        GATE_1: AdvisoryLanguageValidator
        - Classifies query as Tier 0/1/2
        - Validates advisory framing
        - Assigns routing confidence score

        Args:
            query: User query string

        Returns:
            RoutingDecision with tier classification

        Raises:
            ValueError: If query fails advisory language validation
        """
        logger.info(f"UOC.route: START query={query[:50]}...")

        # Validate advisory framing (GATE_1)
        validation_result = self._validate_advisory_framing(query)
        if not validation_result.passed:
            logger.warning(
                f"UOC.route: GATE_1 FAILED — violations: {validation_result.violations}"
            )
            raise ValueError(
                f"Advisory language validation failed: {validation_result.violations}. "
                f"Suggestions: {validation_result.suggestions}"
            )

        # Classify tier
        tier = self._classify_tier(query)
        confidence = self._calculate_routing_confidence(query, tier)

        # Build alternative tiers considered
        alternatives = [t for t in Tier if t != tier]

        routing = RoutingDecision(
            tier=tier,
            confidence_score=confidence,
            reasoning=self._build_routing_reasoning(query, tier),
            alternative_tiers_considered=alternatives,
            fallback_strategy=self._get_fallback_strategy(tier),
        )

        self._current_routing = routing
        self.state = LifecycleState.ROUTED

        logger.info(
            f"UOC.route: END tier={tier.value}, confidence={confidence:.3f}"
        )

        return routing

    # -------------------------------------------------------------------------
    # Step 2: PLANNING — KBG Context Assembly
    # -------------------------------------------------------------------------

    def plan(self, routing_decision: RoutingDecision, query: str) -> ActionChain:
        """
        Step 2: Assemble context and generate action chain.

        Uses KnowledgeBaseGateway.get_merged_context() to apply
        L3 Veto/Override algorithm.

        Args:
            routing_decision: Output from route()
            query: User query string

        Returns:
            ActionChain with merged context and confidence metadata
        """
        logger.info(f"UOC.plan: START")

        if self.state != LifecycleState.ROUTED:
            raise RuntimeError(
                f"UOC.plan: Invalid state {self.state.value}, expected ROUTED. "
                "Call route() first."
            )

        # Get merged context via KBG (L3 Veto/Override applied)
        merged_context = self.kbg.get_merged_context(self.facility_id, query)
        self._current_context = merged_context

        # Generate action chain (placeholder — actual implementation
        # will integrate with existing action service)
        action_chain = self._generate_action_chain(
            routing_decision, merged_context, query
        )

        self._current_action_chain = action_chain
        self.state = LifecycleState.PLANNED

        logger.info(
            f"UOC.plan: END actions={len(action_chain.actions)}, "
            f"winning_level={merged_context.winning_level.value}"
        )

        return action_chain

    # -------------------------------------------------------------------------
    # Step 3: RESOLUTION_VALIDATION — GATE_2 (ActionNormalizer) + GATE_4 (SafetyVEEModule)
    # -------------------------------------------------------------------------

    def resolve_actions(self, action_chain: ActionChain) -> List[NormalizedAction]:
        """
        Step 3: Validate and normalize actions.

        GATE_2: ActionNormalizer
        - Validates action parameters against device specs
        - Maps to executor type (virtual/physical/MCP)

        GATE_4: SafetyVEEModule
        - Hardware bounds verification
        - Operational limits confirmation
        - Emergency stop detection
        - VEE Validation/Evaluation

        Both gates must pass for action to proceed.

        Args:
            action_chain: Output from plan()

        Returns:
            List of NormalizedAction objects

        Raises:
            ValueError: If GATE_2 or GATE_4 validation fails
        """
        logger.info(f"UOC.resolve_actions: START")

        if self.state != LifecycleState.PLANNED:
            raise RuntimeError(
                f"UOC.resolve_actions: Invalid state {self.state.value}, "
                "expected PLANNED. Call plan() first."
            )

        # Get user intent from context for VEE validation
        user_intent = self._current_context.context_data.get("original_query", "") if self._current_context else ""

        normalized = []
        for action in action_chain.actions:
            logger.info(f"UOC.resolve_actions: Processing action={action.action_id}")

            # GATE_2: ActionNormalizer — parameter validation + executor mapping
            try:
                normalized_action = self._action_normalizer.normalize(
                    action_id=action.action_id,
                    parameters=action.parameters,
                    device_id=self._current_context.context_data.get("device_id") if self._current_context else None,
                )
            except ValueError as e:
                logger.warning(f"UOC.resolve_actions: GATE_2 FAILED for {action.action_id}: {e}")
                raise ValueError(
                    f"GATE_2 (ActionNormalizer) failed for action '{action.action_id}': {e}. "
                    "Returning to PLANNING for parameter adjustment."
                )

            # GATE_4: SafetyVEEModule — safety + VEE validation
            # Only proceed if GATE_2 passed
            safety_result = self._safety_vee.validate_action(
                action_id=action.action_id,
                parameters=normalized_action.parameters,
                intent=user_intent,
                context_data=self._current_context.context_data if self._current_context else {},
            )

            if not safety_result.overall_passed:
                logger.warning(
                    f"UOC.resolve_actions: GATE_4 FAILED for {action.action_id}: "
                    f"blocked={safety_result.blocked}, reason={safety_result.block_reason}"
                )
                raise ValueError(
                    f"GATE_4 (SafetyVEEModule) blocked action '{action.action_id}': "
                    f"{safety_result.block_reason}. "
                    "Returning to PLANNING for review."
                )

            # Log warnings if any (but don't block)
            if safety_result.warnings:
                logger.warning(
                    f"UOC.resolve_actions: Warnings for {action.action_id}: "
                    f"{safety_result.warnings}"
                )

            logger.info(
                f"UOC.resolve_actions: Action {action.action_id} passed GATE_2 and GATE_4, "
                f"executor_type={normalized_action.executor_type.value}"
            )

            normalized.append(normalized_action)

        self.state = LifecycleState.VALIDATED

        logger.info(
            f"UOC.resolve_actions: END normalized={len(normalized)}, all passed"
        )

        return normalized

    # -------------------------------------------------------------------------
    # Step 4: P4_HUMAN_GATE — Delegate to P4ApprovalPanel
    # -------------------------------------------------------------------------

    def await_approval(
        self, normalized_actions: List[NormalizedAction]
    ) -> UserDecision:
        """
        Step 4: Await user approval via P4ApprovalPanel.

        GATE_3: P4ApprovalPanel
        - Displays action summary with confidence
        - User chooses CONFIRM / MODIFY / DISMISS

        Args:
            normalized_actions: Output from resolve_actions()

        Returns:
            UserDecision from P4 panel
        """
        logger.info(f"UOC.await_approval: START")

        if self.state != LifecycleState.VALIDATED:
            raise RuntimeError(
                f"UOC.await_approval: Invalid state {self.state.value}, "
                "expected VALIDATED. Call resolve_actions() first."
            )

        # Integrate P4ApprovalPanel
        panel = get_p4_approval_panel()

        # Build ActionSummary from normalized actions
        if normalized_actions:
            first_action = normalized_actions[0]
            action_summary = P4ActionSummary(
                action_id=first_action.action_id,
                action_type=first_action.executor_type.name,
                tool_name=first_action.action_id.split('_')[0] if '_' in first_action.action_id else first_action.action_id,
                target_id=first_action.parameters.get('device_id', first_action.action_id),
                parameters={a.action_id: a.parameters for a in normalized_actions},
                display_summary=f"Action: {first_action.action_id} with {len(normalized_actions)} parameter set(s)",
                description=f"Composite action: {', '.join(a.action_id for a in normalized_actions)}",
            )
        else:
            action_summary = P4ActionSummary(
                action_id="composite",
                action_type="UNKNOWN",
                tool_name="unknown",
                target_id="unknown",
                parameters={},
                display_summary="No actions to approve",
                description="",
            )

        # Build ConfidenceMetadata from UOC context
        if self._current_context and self._current_context.confidence_metadata:
            uoc_conf = self._current_context.confidence_metadata
            p4_confidence = P4ConfidenceMetadata(
                display_confidence=uoc_conf.display_confidence,
                winning_level=uoc_conf.winning_level.value if isinstance(uoc_conf.winning_level, ContextLevel) else str(uoc_conf.winning_level),
                confidence_sources=[lvl.value if isinstance(lvl, ContextLevel) else str(lvl) for lvl in uoc_conf.confidence_sources],
                override_chain=uoc_conf.override_chain,
            )
        else:
            p4_confidence = P4ConfidenceMetadata(
                display_confidence=0.5,
                winning_level="L1",
                confidence_sources=[],
                override_chain=[],
            )

        # Build SafetyInfo
        safety_info = SafetyInfo(
            status=SafetyStatus.PASSED,
            vee_validation_score=None,
            vee_evaluation_risk=None,
            warnings=[],
            block_reason=None,
        )

        # Register draft and await user decision
        draft_id = panel.register_draft(
            action_summary=action_summary,
            confidence=p4_confidence,
            sources=[],
            safety_info=safety_info,
        )
        p4_decision = panel.await_user_decision(draft_id=draft_id, timeout_seconds=300)

        # Convert P4 UserDecision to UOC UserDecision
        self.state = LifecycleState.APPROVED

        return UserDecision(
            decision=p4_decision.decision.value,
            edited_actions=p4_decision.edited_actions,
            user_notes=p4_decision.user_notes,
        )

    # -------------------------------------------------------------------------
    # Step 5: DAEMON_DISPATCH — Delegate to DAEMON
    # -------------------------------------------------------------------------

    def dispatch(self, user_decision: UserDecision) -> Dict[str, Any]:
        """
        Step 5: Dispatch approved actions to DAEMON.

        Args:
            user_decision: Output from await_approval()

        Returns:
            Execution result dict
        """
        logger.info(f"UOC.dispatch: START decision={user_decision.decision}")

        if self.state != LifecycleState.APPROVED:
            raise RuntimeError(
                f"UOC.dispatch: Invalid state {self.state.value}, "
                "expected APPROVED. Call await_approval() first."
            )

        if user_decision.decision != "CONFIRM":
            logger.info("UOC.dispatch: User did not CONFIRM — aborting")
            self.state = LifecycleState.INITIAL
            return {"status": "aborted", "reason": user_decision.decision}

        # Step 5: DAEMON dispatch via Pyro5 RPC
        actions_to_dispatch = user_decision.edited_actions or (
            self._current_action_chain.actions if self._current_action_chain else []
        )

        results = []
        errors = []
        for action in actions_to_dispatch:
            # Map Action to daemon's execute_action format
            action_dict = {
                "action_type": action.action_id,
                "target_id": action.parameters.get("target_id") or action.parameters.get("device_id"),
                "params": action.parameters,
                "context": action.parameters.get("context"),
            }
            try:
                from aot.aot_client import DaemonControl
                daemon_client = DaemonControl()
                result = daemon_client.proxy().execute_action(action_dict)
                results.append({"action_id": action.action_id, "result": result})
                logger.info(f"UOC.dispatch: action={action.action_id} dispatched OK")
            except Exception as e:
                logger.error(f"UOC.dispatch: action={action.action_id} FAILED: {e}")
                errors.append({"action_id": action.action_id, "error": str(e)})

        self.state = LifecycleState.DISPATCHED

        logger.info(f"UOC.dispatch: END dispatched {len(results)} actions, {len(errors)} errors")

        return {
            "status": "dispatched" if not errors else "partial",
            "actions": len(results),
            "results": results,
            "errors": errors,
        }

    # -------------------------------------------------------------------------
    # Internal Helper Methods
    # -------------------------------------------------------------------------

    def _validate_advisory_framing(self, query: str):
        """
        GATE_1: Validate advisory language patterns.

        Delegates to AdvisoryLanguageValidator for pattern detection.

        Returns:
            ValidationResult with passed/violations/suggestions
        """
        return self._advisory_validator.validate(query)

    def _is_trivial_query(self, query: str) -> bool:
        """Check if query is trivially answerable (Tier 0)."""
        trivial_patterns = [
            "hello", "hi", "good morning", "good afternoon",
            "what time is it", "who are you", "help",
            "안녕", "안녕하세요", "시간", "whoami",
        ]
        query_lower = query.lower().strip()
        return any(pattern in query_lower for pattern in trivial_patterns)

    def _classify_tier(self, query: str) -> Tier:
        """
        Classify query into Tier 0/1/2.

        Logic:
        - Tier 0: Trivial/cached queries (greetings, time, identity)
        - Tier 1: Standard LLM-processable queries
        - Tier 2: Complex queries requiring planner
        """
        if self._is_trivial_query(query):
            return Tier.TIER0

        # Simple heuristic for Tier 2: multi-part or explicit planning keywords
        complex_indicators = [
            "and then", "after that", "first",
            "schedule", "automation", "if then",
            "그리고", "그런 다음", "먼저", "자동화",
        ]
        query_lower = query.lower()

        if any(indicator in query_lower for indicator in complex_indicators):
            return Tier.TIER2

        return Tier.TIER1

    def _calculate_routing_confidence(self, query: str, tier: Tier) -> float:
        """
        Calculate routing confidence score.

        Returns:
            Float between 0.0 and 1.0
        """
        # Base confidence by tier
        tier_confidence = {
            Tier.TIER0: 0.95,  # High confidence for trivial queries
            Tier.TIER1: 0.80,  # Good confidence for standard queries
            Tier.TIER2: 0.60,  # Lower confidence for complex queries
        }

        base = tier_confidence.get(tier, 0.5)

        # Adjust for query length (very short or very long queries are less certain)
        length = len(query)
        if length < 10:
            base *= 0.9
        elif length > 200:
            base *= 0.85

        return round(base, 3)

    def _build_routing_reasoning(self, query: str, tier: Tier) -> str:
        """Build human-readable routing reasoning."""
        tier_descriptions = {
            Tier.TIER0: "cached/simple response",
            Tier.TIER1: "LLM-processable",
            Tier.TIER2: "requires planner (complex)",
        }
        return f"Query classified as {tier.value}: {tier_descriptions[tier]}"

    def _get_fallback_strategy(self, tier: Tier) -> str:
        """Get fallback strategy for each tier."""
        strategies = {
            Tier.TIER0: "Return cached response directly",
            Tier.TIER1: "Process with LLM via ai_agent_service",
            Tier.TIER2: "Delegate to ai_planning_service for action decomposition",
        }
        return strategies.get(tier, "Unknown tier")

    def _generate_action_chain(
        self,
        routing: RoutingDecision,
        context: MergedContext,
        query: str,
    ) -> ActionChain:
        """
        Generate action chain based on routing and context.

        Intent-based action mapping using AIActionService.get_action_manifest()
        for action registry lookups. Falls back to keyword-based routing when
        the planner service is unavailable.

        Args:
            routing: RoutingDecision from route()
            context: MergedContext from KBG
            query: User query string

        Returns:
            ActionChain with resolved actions
        """
        # Determine intent from tier and query keywords
        intent = self._resolve_intent(query, routing.tier)

        # Get action manifest for available actions
        try:
            manifest = AIActionService.get_action_manifest(is_slim=True)
            available_tools = self._extract_tool_names(manifest)
        except Exception:
            available_tools = []

        # Build action chain based on intent
        actions = self._build_actions_for_intent(intent, query, context, available_tools)

        # Fallback if no actions generated
        if not actions:
            actions = [
                Action(
                    action_id="query_info",
                    parameters={"query": query},
                    description=f"Answer query: {query[:80]}",
                )
            ]

        confidence_meta = context.confidence_metadata
        return ActionChain(
            actions=actions,
            estimated_duration=30 * len(actions),
            rollback_plan=[],
            confidence_metadata=confidence_meta,
            context_sources_used=confidence_meta.confidence_sources if confidence_meta else [],
        )

    def _resolve_intent(self, query: str, tier: Tier) -> str:
        """
        Resolve query intent from keywords and tier.

        Returns:
            Intent string: DATA_QUERY | CONTROL | SCHEDULE | FUNCTION_CREATE | ADVICE
        """
        query_lower = query.lower()

        # Tier0: trivial/cached
        if tier == Tier.TIER0:
            return "DATA_QUERY"

        # FUNCTION_CREATE keywords
        func_create_kw = (
            '함수 생성', '함수 만들', '함수를 생성', '함수를 만들',
            '컨트롤러 생성', '컨트롤러 만들', '자동화 생성', '자동화 만들',
            'create function', 'add function', 'create controller',
            'vpd 함수', 'pid 함수', 'conditional 함수',
        )
        if any(kw in query_lower for kw in func_create_kw):
            return "FUNCTION_CREATE"

        # CONTROL keywords
        control_kw = (
            '켜', '끄', 'on', 'off', '작동', '제어', '조작',
            'turn on', 'turn off', 'activate', 'deactivate',
            '밸브', '펌프', '팬', '가습기', '온도', '습도',
        )
        if any(kw in query_lower for kw in control_kw):
            return "CONTROL"

        # SCHEDULE keywords
        schedule_kw = (
            '예약', '스케줄', '자동', 'schedule', 'timed',
            '그리고', '그런 다음', '차례로', '순서대로',
        )
        if any(kw in query_lower for kw in schedule_kw):
            return "SCHEDULE"

        # ADVICE keywords
        advice_kw = (
            '조언', '방법', '설명', '가이드', '안내', '어떻게', '알려',
            '설정 방법', '사용법', '사용 방법', 'advice', 'guide', 'how to',
        )
        if any(kw in query_lower for kw in advice_kw):
            return "ADVICE"

        # Default to DATA_QUERY
        return "DATA_QUERY"

    def _extract_tool_names(self, manifest: Dict[str, Any]) -> List[str]:
        """Extract available tool/action names from manifest."""
        tools = []
        if not manifest:
            return tools

        # System tools have action_type
        for tool in manifest.get("system_tools", []):
            if "action_type" in tool:
                tools.append(tool["action_type"])
            if "tool_name" in tool:
                tools.append(tool["tool_name"])

        # Other manifest sections may have action types
        for section in ["outputs", "pid_controllers", "predefined_functions"]:
            for item in manifest.get(section, []):
                if "action_type" in item:
                    tools.append(item["action_type"])

        return tools

    def _build_actions_for_intent(
        self,
        intent: str,
        query: str,
        context: MergedContext,
        available_tools: List[str],
    ) -> List[Action]:
        """
        Build action list for given intent.

        Args:
            intent: Resolved intent string
            query: User query
            context: MergedContext with context data
            available_tools: List of available tool names

        Returns:
            List of Action objects
        """
        actions = []
        context_data = context.context_data if context else {}

        if intent == "DATA_QUERY":
            # Data/information query — search + read pattern
            device_kw = self._extract_device_keywords(query)
            if device_kw:
                actions.append(Action(
                    action_id="search_devices",
                    parameters={"query": device_kw},
                    description=f"Search for device: {device_kw}",
                ))
                actions.append(Action(
                    action_id="get_sensor_detail",
                    parameters={
                        "loc_id": "$device_info.results[0].id",
                        "sensor_type": "weather",
                        "limit": 1,
                    },
                    description=f"Read sensor data for: {device_kw}",
                ))
            else:
                # Generic info query
                actions.append(Action(
                    action_id="abstract_plan",
                    parameters={"query": query},
                    description=f"Answer query: {query[:80]}",
                ))

        elif intent == "CONTROL":
            # Device control — search + operate pattern
            device_kw = self._extract_device_keywords(query)
            state = "on" if any(k in query.lower() for k in ['켜', 'on', '작동', 'activate']) else "off"

            if device_kw:
                actions.append(Action(
                    action_id="search_devices",
                    parameters={"query": device_kw},
                    description=f"Find device to control: {device_kw}",
                ))
                actions.append(Action(
                    action_id="operate_device",
                    parameters={
                        "device_id": "$device_info.results[0].id",
                        "state": state,
                    },
                    description=f"Control {device_kw}: {state}",
                ))

        elif intent == "SCHEDULE":
            # Scheduling — search + schedule pattern
            device_kw = self._extract_device_keywords(query)
            if device_kw:
                actions.append(Action(
                    action_id="search_devices",
                    parameters={"query": device_kw},
                    description=f"Find device for scheduling: {device_kw}",
                ))
                actions.append(Action(
                    action_id="schedule_device_control",
                    parameters={
                        "device_id": "$device_info.results[0].id",
                        "state": "on",
                        "scheduled_time": "now",
                        "duration_minutes": 1,
                    },
                    description=f"Schedule {device_kw}",
                ))

        elif intent == "FUNCTION_CREATE":
            # Function creation — requires search + get_measurements + create
            func_type = self._detect_function_type(query)
            zone_name = self._extract_device_keywords(query) or "default"

            actions.append(Action(
                action_id="search_devices",
                parameters={"query": zone_name},
                description=f"Find zone device: {zone_name}",
            ))
            actions.append(Action(
                action_id="get_device_measurements",
                parameters={
                    "device_id": "$device_info.results[0].id",
                },
                description=f"Get measurements for {func_type} function",
            ))
            actions.append(Action(
                action_id="create_function",
                parameters={
                    "function_type": func_type,
                    "name": f"{zone_name} {func_type}",
                    "params": {
                        "period": 60,
                    },
                },
                description=f"Create {func_type} function for {zone_name}",
            ))

        elif intent == "ADVICE":
            # Advice/guide query — doc lookup
            topic = self._detect_advice_topic(query)
            actions.append(Action(
                action_id="get_function_doc",
                parameters={"function_type": topic},
                description=f"Get documentation for: {topic}",
            ))

        return actions

    def _extract_device_keywords(self, query: str) -> str:
        """Extract device/zone name from query."""
        import re
        # Remove common stop words and extract meaningful keywords
        stop_words = {
            '날씨', '기상', '기온', '강수', '풍속', '온도', '습도', '정보',
            '알려줘', '조회', '켜', '끄', 'on', 'off', '작동', '제어',
            'weather', 'temperature', 'humidity', 'turn', '조언', '방법',
        }
        cleaned = query
        for sw in stop_words:
            cleaned = cleaned.lower().replace(sw, ' ')
        keywords = re.findall(r'[가-힣a-zA-Z0-9]+', cleaned)
        return ' '.join(keywords[:3]) if keywords else ""

    def _detect_function_type(self, query: str) -> str:
        """Detect function type from query."""
        query_lower = query.lower()
        if 'vpd' in query_lower:
            return "AoT_VPD"
        elif 'pid' in query_lower:
            return "AoT_PID"
        elif 'conditional' in query_lower:
            return "AoT_conditional"
        return "AoT_VPD"  # Default

    def _detect_advice_topic(self, query: str) -> str:
        """Detect advice topic from query."""
        query_lower = query.lower()
        if 'pid' in query_lower:
            return "pid"
        elif 'vpd' in query_lower:
            return "vpd"
        elif any(k in query_lower for k in ['input', '입력', '센서']):
            return "input"
        elif any(k in query_lower for k in ['output', '출력', '릴레이']):
            return "output"
        return "function"

    # -------------------------------------------------------------------------
    # State Machine Control
    # -------------------------------------------------------------------------

    def reset(self):
        """Reset orchestrator to INITIAL state."""
        self.state = LifecycleState.INITIAL
        self._current_routing = None
        self._current_context = None
        self._current_action_chain = None
        logger.info("UOC.reset: Returned to INITIAL state")

    def get_state(self) -> LifecycleState:
        """Return current lifecycle state."""
        return self.state
