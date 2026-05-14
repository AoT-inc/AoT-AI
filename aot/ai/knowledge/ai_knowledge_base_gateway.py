# coding=utf-8
"""
KnowledgeBaseGateway — v5.1 L3 Veto/Override Implementation.

Implements the KnowledgeBaseGateway component per 002_DESIGN.yaml Section 7.
L3 Veto/Override Algorithm: Temporal/Situational context dominates when valid and relevant.

@ANCHOR: KNOWLEDGE_BASE_GATEWAY
@phase 1_ai_kbg
"""
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class ContextLevel(Enum):
    """Context precedence levels per L3 Veto/Override algorithm."""
    L1_DOMAIN = "L1"
    L2_FACILITY = "L2"
    L3_TEMPORAL = "L3"


class ContextState(Enum):
    """State of a context entry for confidence calculation."""
    SYSTEM_GENERATED = "system_generated"
    PENDING = "pending"
    USER_CONFIRMED = "user_confirmed"


@dataclass
class ConfidenceMetadata:
    """Schema: ConfidenceMetadata per 002_DESIGN.yaml Section 6."""
    display_confidence: float  # 0.0-1.0, UI display only
    winning_level: ContextLevel
    confidence_sources: List[ContextLevel]
    override_chain: List[str]
    winning_level_confidence: float = 1.0


@dataclass
class MergedContext:
    """
    Output of KBG.get_merged_context().
    Contains merged context + confidence metadata.
    """
    context_data: Dict[str, Any]
    confidence_metadata: ConfidenceMetadata
    winning_level: ContextLevel


@dataclass
class KnowledgeEntry:
    """A single knowledge entry from search results."""
    content: str
    source_level: ContextLevel
    source_id: Optional[str] = None
    relevance_score: float = 1.0


# L3 Veto/Override trust weights per DESIGN Section 4
TRUST_WEIGHTS = {
    ContextLevel.L3_TEMPORAL: 1.0,
    ContextLevel.L2_FACILITY: 0.7,
    ContextLevel.L1_DOMAIN: 0.4,
}

# State confidence modifiers per DESIGN Section 4
STATE_CONFIDENCE_MODIFIERS = {
    ContextState.SYSTEM_GENERATED: 0.3,
    ContextState.PENDING: 0.0,
    ContextState.USER_CONFIRMED: 1.0,
}


class KnowledgeBaseGateway:
    """
    KnowledgeBaseGateway — v5.1 L3 Veto/Override Implementation.

    Responsibilities (per DESIGN Section 7):
    - L1/L2/L3 context retrieval
    - L3 Veto/Override cascade application
    - Conflict resolution
    - Confidence metadata attachment

    @phase active
    @stability stable
    """

    def __init__(self, facility_id: str):
        """
        Initialize KBG for a specific facility.

        Args:
            facility_id: Target facility identifier
        """
        self.facility_id = facility_id
        self._l1_cache: Optional[Dict] = None
        self._l2_cache: Optional[Dict] = None
        self._l3_cache: Optional[Dict] = None

    # -------------------------------------------------------------------------
    # Public API — L1/L2/L3 Context Retrieval
    # -------------------------------------------------------------------------

    def get_domain_context(self, domain_id: str) -> Dict[str, Any]:
        """
        Retrieve L1 Domain context (general knowledge base).

        Args:
            domain_id: Domain identifier

        Returns:
            DomainContext dict with general agricultural domain knowledge entries
        """
        logger.debug(f"KBG.get_domain_context: domain_id={domain_id}")

        try:
            from aot.ai.services.domain_context_loader import DomainContextLoader

            # Get all active facilities to build L1 domain knowledge
            active_facilities = DomainContextLoader.get_all_active_facilities()

            entries = []
            # Aggregate domain knowledge from all active facilities' modules
            for facility_id in active_facilities:
                module = DomainContextLoader.load_active_module(facility_id)
                if module:
                    # Extract domain-relevant entries (crop_type, config, operational_state)
                    domain_entry = {
                        "facility_id": facility_id,
                        "crop_type": module.get("crop_type"),
                        "config": module.get("config", {}),
                        "operational_state": module.get("operational_state", {}),
                    }
                    entries.append(domain_entry)

            return {
                "level": ContextLevel.L1_DOMAIN.value,
                "domain_id": domain_id,
                "entries": entries,
            }
        except Exception as exc:
            logger.warning(f"KBG.get_domain_context: failed to load domain context: {exc}")
            return {
                "level": ContextLevel.L1_DOMAIN.value,
                "domain_id": domain_id,
                "entries": [],
                "state": ContextState.SYSTEM_GENERATED.value,
            }

    def get_facility_context(self, facility_id: str) -> Dict[str, Any]:
        """
        Retrieve L2 Facility context (facility-specific parameters).

        Args:
            facility_id: Facility identifier

        Returns:
            FacilityContext dict with facility-specific operational data
        """
        logger.debug(f"KBG.get_facility_context: facility_id={facility_id}")

        try:
            from aot.ai.services.domain_context_loader import DomainContextLoader

            # Load facility-specific module via DomainContextLoader
            module = DomainContextLoader.load_active_module(facility_id)

            if module is None:
                logger.warning(f"KBG.get_facility_context: no active module for facility_id={facility_id}")
                return {
                    "level": ContextLevel.L2_FACILITY.value,
                    "facility_id": facility_id,
                    "entries": [],
                    "state": ContextState.PENDING.value,
                }

            # Extract facility-specific entries
            entries = [
                {
                    "crop_type": module.get("crop_type"),
                    "planting_date": module.get("planting_date"),
                    "config": module.get("config", {}),
                    "operational_state": module.get("operational_state", {}),
                }
            ]

            return {
                "level": ContextLevel.L2_FACILITY.value,
                "facility_id": facility_id,
                "entries": entries,
                "state": ContextState.SYSTEM_GENERATED.value,
            }
        except Exception as exc:
            logger.warning(f"KBG.get_facility_context: failed to load facility context: {exc}")
            return {
                "level": ContextLevel.L2_FACILITY.value,
                "facility_id": facility_id,
                "entries": [],
                "state": ContextState.SYSTEM_GENERATED.value,
            }

    def get_temporal_context(
        self, facility_id: str, time_range: Tuple[str, str]
    ) -> Dict[str, Any]:
        """
        Retrieve L3 Temporal/Situational context (time-sensitive data).

        Args:
            facility_id: Facility identifier
            time_range: Tuple of (start_iso, end_iso) timestamps

        Returns:
            TemporalContext dict with recent sensor readings from InfluxDB
        """
        logger.debug(
            f"KBG.get_temporal_context: facility_id={facility_id}, "
            f"time_range={time_range}"
        )

        try:
            from aot.utils.influx import read_influxdb_list
            from aot.databases.models import DeviceMeasurements
            from aot.utils.database import db_retrieve_table_daemon
            from aot.utils.system_pi import return_measurement_info

            # Get device measurements for this facility
            devices = db_retrieve_table_daemon(DeviceMeasurements).filter(
                DeviceMeasurements.device_id == facility_id
            ).all() if facility_id else []

            entries = []
            start_iso, end_iso = time_range

            # Convert ISO timestamps to influx query format
            start_str = start_iso.replace("+00:00", "Z") if "Z" not in start_iso else start_iso
            end_str = end_iso.replace("+00:00", "Z") if "Z" not in end_iso else end_iso

            for device in devices:
                try:
                    # Get measurement info
                    channel, unit, measurement = return_measurement_info(device, None)

                    if unit and device.unique_id:
                        # Query InfluxDB for time range
                        data = read_influxdb_list(
                            unique_id=device.unique_id,
                            unit=unit,
                            channel=channel,
                            measure=measurement,
                            start_str=start_str,
                            end_str=end_str,
                        )

                        if data:
                            entry = {
                                "device_id": device.unique_id,
                                "unit": unit,
                                "measurement": measurement,
                                "channel": channel,
                                "readings": [
                                    {"timestamp": ts, "value": val} for ts, val in data[-10:]  # Last 10 readings
                                ],
                            }
                            entries.append(entry)
                except Exception as exc:
                    logger.debug(f"KBG.get_temporal_context: error reading device {device.unique_id}: {exc}")
                    continue

            return {
                "level": ContextLevel.L3_TEMPORAL.value,
                "facility_id": facility_id,
                "time_range": time_range,
                "entries": entries,
                "state": ContextState.SYSTEM_GENERATED.value,
            }
        except Exception as exc:
            logger.warning(f"KBG.get_temporal_context: failed to load temporal context: {exc}")
            return {
                "level": ContextLevel.L3_TEMPORAL.value,
                "facility_id": facility_id,
                "time_range": time_range,
                "entries": [],
                "state": ContextState.SYSTEM_GENERATED.value,
            }

    def search_with_confidence(
        self, query: str, facility_id: str, top_k: int = 5
    ) -> List[KnowledgeEntry]:
        """
        Search knowledge base with confidence ranking.

        Args:
            query: Search query string
            facility_id: Facility identifier
            top_k: Number of top results to return

        Returns:
            List[KnowledgeEntry] ranked by relevance
        """
        logger.debug(
            f"KBG.search_with_confidence: query={query}, "
            f"facility_id={facility_id}, top_k={top_k}"
        )

        try:
            # Fetch all three context levels
            l1_ctx = self.get_domain_context(facility_id)
            l2_ctx = self.get_facility_context(facility_id)
            l3_ctx = self.get_temporal_context(facility_id, self._get_default_time_range())

            query_lower = query.lower()
            results: List[KnowledgeEntry] = []

            # Search L1 Domain Context
            for entry in l1_ctx.get("entries", []):
                content = self._extract_content_from_entry(entry)
                if query_lower in content.lower():
                    results.append(KnowledgeEntry(
                        content=content,
                        source_level=ContextLevel.L1_DOMAIN,
                        source_id=entry.get("facility_id"),
                        relevance_score=TRUST_WEIGHTS[ContextLevel.L1_DOMAIN],
                    ))

            # Search L2 Facility Context
            for entry in l2_ctx.get("entries", []):
                content = self._extract_content_from_entry(entry)
                if query_lower in content.lower():
                    results.append(KnowledgeEntry(
                        content=content,
                        source_level=ContextLevel.L2_FACILITY,
                        source_id=facility_id,
                        relevance_score=TRUST_WEIGHTS[ContextLevel.L2_FACILITY],
                    ))

            # Search L3 Temporal Context
            for entry in l3_ctx.get("entries", []):
                content = self._extract_content_from_entry(entry)
                if query_lower in content.lower():
                    results.append(KnowledgeEntry(
                        content=content,
                        source_level=ContextLevel.L3_TEMPORAL,
                        source_id=entry.get("device_id"),
                        relevance_score=TRUST_WEIGHTS[ContextLevel.L3_TEMPORAL],
                    ))

            # Sort by relevance_score descending and return top_k
            results.sort(key=lambda x: x.relevance_score, reverse=True)
            return results[:top_k]

        except Exception as exc:
            logger.warning(f"KBG.search_with_confidence: search failed: {exc}")
            return []

    def _extract_content_from_entry(self, entry: Dict[str, Any]) -> str:
        """
        Extract searchable content string from a context entry.

        Args:
            entry: Context entry dictionary

        Returns:
            String content for search indexing
        """
        parts = []
        for key, value in entry.items():
            if isinstance(value, (str, int, float)):
                parts.append(f"{key}: {value}")
            elif isinstance(value, dict):
                # Flatten nested dicts
                for k, v in value.items():
                    if isinstance(v, (str, int, float)):
                        parts.append(f"{k}: {v}")
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        parts.append(self._extract_content_from_entry(item))
                    else:
                        parts.append(str(item))
        return " | ".join(parts)

    # -------------------------------------------------------------------------
    # Core Method: L3 Veto/Override Merged Context
    # -------------------------------------------------------------------------

    def get_merged_context(self, facility_id: str, query: str) -> MergedContext:
        """
        Core method implementing L3 Veto/Override algorithm.

        Algorithm Steps (per DESIGN Section 4):
        1. Fetch L1, L2, L3 contexts in parallel
        2. Evaluate validity and relevance for each level
        3. Apply L3 Veto/Override cascade:
           - L3 valid + relevant → L3 wins (complete override)
           - L3 invalid/irrelevant → check L2
           - L2 valid + relevant → L2 wins (facility override)
           - Otherwise → L1 wins (default baseline)
        4. Calculate display_confidence = winning_level.trust_weight × confidence
        5. Attach override_chain for traceability

        Args:
            facility_id: Facility identifier
            query: User query for relevance evaluation

        Returns:
            MergedContext with context_data and confidence_metadata
        """
        logger.info(
            f"KBG.get_merged_context: START for facility={facility_id}, "
            f"query={query[:50]}..."
        )

        # Step 1: Fetch L1, L2, L3 in parallel (placeholder for async)
        l1_ctx = self.get_domain_context(facility_id)
        l2_ctx = self.get_facility_context(facility_id)
        l3_ctx = self.get_temporal_context(facility_id, self._get_default_time_range())

        # Step 2: Evaluate validity and relevance
        l1_valid, l1_relevant = self._evaluate_context(l1_ctx, query)
        l2_valid, l2_relevant = self._evaluate_context(l2_ctx, query)
        l3_valid, l3_relevant = self._evaluate_context(l3_ctx, query)

        # Step 3: Apply L3 Veto/Override algorithm
        override_chain = []
        winning_level: ContextLevel
        winning_context: Dict[str, Any]

        # L3 Veto Check
        if l3_valid and l3_relevant:
            winning_level = ContextLevel.L3_TEMPORAL
            winning_context = l3_ctx
            override_chain.append(
                "L3 VETO: L3 valid and relevant → complete override"
            )
            logger.info("KBG.get_merged_context: L3 VETO APPLIED")
        # L2 Override Check
        elif l2_valid and l2_relevant:
            winning_level = ContextLevel.L2_FACILITY
            winning_context = l2_ctx
            override_chain.append(
                "L2 OVERRIDE: L3 absent/invalid/irrelevant, L2 valid and relevant"
            )
            logger.info("KBG.get_merged_context: L2 OVERRIDE APPLIED")
        # L1 Default
        else:
            winning_level = ContextLevel.L1_DOMAIN
            winning_context = l1_ctx
            override_chain.append(
                "L1 DEFAULT: L3 and L2 absent/invalid/irrelevant"
            )
            logger.info("KBG.get_merged_context: L1 DEFAULT APPLIED")

        # Step 4: Calculate display confidence
        base_confidence = self._get_base_confidence(winning_context)
        display_confidence = TRUST_WEIGHTS[winning_level] * base_confidence

        # Step 5: Build confidence metadata
        confidence_sources = self._get_contributing_levels(
            l1_valid, l2_valid, l3_valid
        )

        confidence_metadata = ConfidenceMetadata(
            display_confidence=round(display_confidence, 3),
            winning_level=winning_level,
            confidence_sources=confidence_sources,
            override_chain=override_chain,
            winning_level_confidence=base_confidence,
        )

        result = MergedContext(
            context_data=winning_context,
            confidence_metadata=confidence_metadata,
            winning_level=winning_level,
        )

        logger.info(
            f"KBG.get_merged_context: END winning_level={winning_level.value}, "
            f"display_confidence={display_confidence:.3f}"
        )

        return result

    # -------------------------------------------------------------------------
    # Internal Helper Methods
    # -------------------------------------------------------------------------

    def _get_default_time_range(self) -> Tuple[str, str]:
        """Return default time range for L3 context (last 24 hours)."""
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        start = now - timedelta(hours=24)
        return (start.isoformat(), now.isoformat())

    def _evaluate_context(
        self, context: Dict[str, Any], query: str
    ) -> Tuple[bool, bool]:
        """
        Evaluate if a context is valid and relevant.

        Args:
            context: Context dictionary
            query: User query for relevance check

        Returns:
            Tuple of (is_valid, is_relevant)
        """
        if not context:
            return False, False

        # Check validity: context has entries and required fields
        is_valid = (
            "entries" in context
            and context.get("entries") is not None
        )

        # Check relevance: entries exist and context level matches query
        is_relevant = False
        if is_valid and context.get("entries"):
            # Simple relevance: query terms appear in context
            # TODO: Implement proper semantic relevance check
            query_lower = query.lower()
            for entry in context.get("entries", []):
                if isinstance(entry, dict):
                    content = str(entry.get("content", "")).lower()
                    if query_lower in content:
                        is_relevant = True
                        break
                elif isinstance(entry, str):
                    if query_lower in entry.lower():
                        is_relevant = True
                        break

        return is_valid, is_relevant

    def _get_base_confidence(self, context: Dict[str, Any]) -> float:
        """
        Calculate base confidence from context state.

        Per DESIGN Section 4:
        - user_confirmed: 1.0 (full weight)
        - system_generated: 0.3 (flagged as unconfirmed)
        - pending: 0.0 (blocked until confirmed)
        """
        state_str = context.get("state", ContextState.SYSTEM_GENERATED.value)

        try:
            state = ContextState(state_str)
        except ValueError:
            state = ContextState.SYSTEM_GENERATED

        return STATE_CONFIDENCE_MODIFIERS.get(state, 0.3)

    def _get_contributing_levels(
        self, l1_valid: bool, l2_valid: bool, l3_valid: bool
    ) -> List[ContextLevel]:
        """Return list of levels that contributed valid data."""
        sources = []
        if l1_valid:
            sources.append(ContextLevel.L1_DOMAIN)
        if l2_valid:
            sources.append(ContextLevel.L2_FACILITY)
        if l3_valid:
            sources.append(ContextLevel.L3_TEMPORAL)
        return sources
