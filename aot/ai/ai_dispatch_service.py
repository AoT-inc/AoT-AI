# coding=utf-8
"""
AIDispatchService — Extracted dispatch and draft registration logic from AIAgentService.

@ANCHOR: AI_DISPATCH_SERVICE
"""
import json
import logging
from aot.aot_flask.extensions import db
from aot.databases.models.ai import AIAgent
from aot.databases.models.ai import AIHistory
from aot.databases.models.ai_task import AITask
from aot.utils.time_utils import utc_now
from datetime import timedelta

logger = logging.getLogger(__name__)

IMMEDIATE_ACTIONS = {'mcp_tool_call', 'virtual_tool_call', 'read_manual', 'get_detailed_manifest'}

# Virtual tools that require human approval even though action_type='virtual_tool_call'
# Keep in sync with _APPROVAL_REQUIRED_TOOLS in ai_planning_service.py
_VIRTUAL_APPROVAL_TOOLS = frozenset({
    'create_function', 'modify_function_options',
    'activate_function', 'deactivate_function',
})

class AIDispatchService:
    """Extracted dispatch logic from Phase 3 God Object decoupling."""

    # @ANCHOR: P4_OPERATE_DEVICE_HARD_GATE
    # Philosophy P4 (User Agency) — architectural hard gate.
    # User-facing pipeline roles are NEVER allowed to execute operate_device directly.
    # The preamble remains the first line of defense; this is the second (hard) line.
    _P4_GATED_ROLES = frozenset({'synthesizer', 'worker', 'chat'})
    _P4_GATED_ACTION_TYPES = frozenset({'operate_device', 'output_on', 'output_off'})
    _P4_GATED_TOOL_NAMES = frozenset({'operate_device', 'set_output_state'})

    @staticmethod
    def _apply_p4_device_gate(actions, agent_id):
        """
        Hard gate: If the calling agent has a user-facing pipeline_role
        (synthesizer, worker, chat), any operate_device action is forced to
        'proposed' status with gate metadata.  Internal roles (executor,
        planner, router) are exempt.

        Returns (gated_actions, ungated_actions) where gated_actions have been
        annotated and must go to proposed_to_draft.
        """
        from aot.databases.models.ai import AIAgent

        agent_cfg = AIAgent.query.filter_by(unique_id=agent_id).first()
        pipeline_role = (agent_cfg.pipeline_role if agent_cfg else 'worker') or 'worker'

        if pipeline_role not in AIDispatchService._P4_GATED_ROLES:
            # Executor / planner / router — exempt from gate
            return [], actions

        gated = []
        ungated = []
        for a in actions:
            a_type = (a.get('action_type') or '').lower()
            tool_name = (a.get('params') or {}).get('tool_name') or a.get('tool_name', '')

            is_device_action = (
                a_type in AIDispatchService._P4_GATED_ACTION_TYPES
                or tool_name in AIDispatchService._P4_GATED_TOOL_NAMES
            )

            if is_device_action:
                # Force to proposed — never execute
                a['status'] = 'proposed'
                a['gate_reason'] = 'philosophy_p4_user_agency'
                a['gate_applied_by'] = 'ai_dispatch_service'
                a['requires_human_approval'] = True
                gated.append(a)
            else:
                ungated.append(a)

        return gated, ungated

    @staticmethod
    def _dispatch_actions(agent_id, goal, insight, actions, thread_id=None, message_type='ai', metadata=None, user_id=None):
        from aot.ai.services.ai_action_service import AIActionService
        immediate_to_run = []
        proposed_to_draft = []

        # Phase 6: Apply P4 hard gate BEFORE routing logic.
        # Gated actions are forced to proposed_to_draft regardless of action_type.
        p4_gated, actions = AIDispatchService._apply_p4_device_gate(actions, agent_id)
        proposed_to_draft.extend(p4_gated)

        from aot.ai.services.resolvers.constants import PHYSICAL_TOOLS as _PHYS_DISPATCH
        # @ANCHOR: DISPATCH_NORMALIZE_ACTION_TYPE
        # [OPTION_D] LLM emits only tool_name (no action_type). Normalize each action
        # BEFORE routing so data tools (virtual_tool_call) go to immediate_to_run,
        # not proposed_to_draft (approval gate).
        from aot.ai.ai_routing_service import AIRoutingService as _ARS
        for a in actions:
            if not a.get('action_type'):
                _valid, _err = _ARS._validate_and_normalize_action(a)
                if not _valid:
                    logger.warning(
                        "[dispatch] Skipping unresolvable action tool=%r: %s",
                        (a.get('params') or {}).get('tool_name') or a.get('tool_name'),
                        _err
                    )
                    continue
            a_type = a.get('action_type', '').lower()
            if a_type in IMMEDIATE_ACTIONS:
                if a_type == 'virtual_tool_call':
                    tool_name = a.get('params', {}).get('tool_name') or a.get('tool_name', '')
                    if (tool_name in ['add_schedule', 'schedule_device_control']
                            or tool_name in _PHYS_DISPATCH
                            or tool_name in _VIRTUAL_APPROVAL_TOOLS):
                        proposed_to_draft.append(a)
                        continue
                # [DISPATCH-FIX] mcp_tool_call with a physical or scheduling tool must be proposed,
                # not executed immediately — it requires the same human-approval gate.
                # schedule_device_control / add_schedule are NOT in PHYSICAL_TOOLS but still need approval.
                if a_type == 'mcp_tool_call':
                    tool_name = a.get('params', {}).get('tool_name') or a.get('tool_name', '')
                    if tool_name in _PHYS_DISPATCH or tool_name in {'schedule_device_control', 'add_schedule'}:
                        proposed_to_draft.append(a)
                        continue
                immediate_to_run.append(a)
            else:
                proposed_to_draft.append(a)

        # Phase 3: Attach reasoning_trace to each action (optional, non-breaking).
        # Uses ReasoningTraceBuilder to derive confidence from context_metadata
        # and facility learning state. Fails gracefully — no trace if unavailable.
        try:
            from aot.ai.reasoning_trace_builder import ReasoningTraceBuilder
            # Extract context_metadata and facility learning state from metadata
            _ctx_meta = (metadata or {}).get('context_metadata')
            _facility_learning = (metadata or {}).get('facility_learning_state')
            for a in actions:
                try:
                    trace = ReasoningTraceBuilder.build(
                        a, _ctx_meta, _facility_learning
                    )
                    if trace:
                        a['reasoning_trace'] = trace
                except Exception as _t_exc:
                    logger.debug(
                        "[dispatch] reasoning_trace failed for action %s: %s",
                        a.get('action_type', 'unknown'), _t_exc
                    )
        except Exception as _rt_exc:
            logger.warning(
                "[dispatch] ReasoningTraceBuilder unavailable: %s", _rt_exc
            )

        immediate_results = []
        for a in immediate_to_run:
            try:
                res = AIActionService.execute_action(a['action_type'], a.get('target_id'), a.get('params'))
                immediate_results.append(f"Immediate Action '{a['action_type']}' Result: {json.dumps(res, ensure_ascii=False)}")
            except Exception as e:
                logger.error(f"Failed to execute immediate action {a['action_type']}: {e}")
                immediate_results.append(f"Immediate Action '{a['action_type']}' Failed: {str(e)}")

        status = 'executed' if not proposed_to_draft else 'proposed'
        
        # Resolve user_id: prefer explicit parameter, fall back to Flask-Login current_user
        _user_id = user_id
        if _user_id is None:
            try:
                import flask_login
                cu = flask_login.current_user
                if cu and cu.is_authenticated:
                    _user_id = cu.id
            except Exception:
                pass  # Outside request context (e.g. daemon/batch) — leave as None

        history_entry = AIHistory(
            agent_id=agent_id,
            goal=goal,
            insight=insight,
            actions_json=json.dumps(actions),
            status=status,
            execution_result="\n".join(immediate_results) if immediate_results else None,
            metadata_json=json.dumps(metadata) if metadata else '{}',
            thread_id=thread_id,
            message_type=message_type,
            user_id=_user_id
        )
        history_entry.save()

        draft_ids = []
        if proposed_to_draft:
            agent_name = 'AI'
            agent_cfg = AIAgent.query.filter_by(unique_id=agent_id).first()
            if agent_cfg:
                agent_name = agent_cfg.name

            draft_ids = AIDispatchService._register_drafts(
                proposed_to_draft,
                reasoning=insight,
                agent_name=agent_name
            )

        return {
            "history_id": history_entry.unique_id,
            "status": status,
            "proposed": proposed_to_draft,
            "immediate_results": immediate_results,
            "draft_ids": draft_ids
        }

    @staticmethod
    def _register_drafts(actions, reasoning, agent_name='AI'):
        draft_ids = AIDispatchService._register_drafts_no_commit(actions, reasoning, agent_name)
        db.session.commit()
        return draft_ids

    @staticmethod
    def _register_drafts_no_commit(actions, reasoning, agent_name='AI'):
        draft_ids = []
        if not actions:
            return draft_ids

        for action in actions:
            action_type = action.get('action_type')
            target_id = action.get('target_id')
            if not action_type:
                continue

            existing_task = AITask.query.filter(
                AITask.action_type == action_type,
                AITask.target_id == target_id,
                AITask.status.in_(['proposed', 'cancelled'])
            ).first()

            if existing_task:
                logger.info(f"[Collaboration] Skipping duplicate proposal: {action_type} for {target_id} (Status: {existing_task.status})")
                continue

            params = action.get('params', {})
            priority = action.get('priority', 3)
            now = utc_now()
            proposed_start = now + timedelta(minutes=10)
            proposed_end = now + timedelta(minutes=70)
            
            try:
                task = AITask(
                    title=f"[{agent_name}] {action_type} {target_id}",
                    description=f"{reasoning[:500] if reasoning else ''}\n\nParams: {json.dumps(params)}",
                    task_type='task',
                    status='proposed',
                    priority=priority,
                    action_type=action_type,
                    target_id=target_id,
                    action_params=json.dumps(params),
                    proposed_start=proposed_start,
                    proposed_end=proposed_end,
                    change_reason=reasoning[:500] if reasoning else "AI Proposed Action"
                )
                db.session.add(task)
                db.session.flush()
                draft_ids.append(task.unique_id)
            except Exception as e:
                logger.exception(f"Failed to register AITask draft for {action_type}/{target_id}")

        return draft_ids

    @staticmethod
    def _check_approval_required(action_type, target_id, params):
        return True
