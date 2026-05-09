# coding=utf-8
# @ANCHOR: VIRTUAL_TOOL_RESOLVER
"""
VirtualToolResolver — routes virtual_tool_call to AoTDataToolService.
No subprocess — internal Python dispatch only.
Ref: SBS-002_V2_STRATEGY (pluggable_resolver.resolvers[VirtualToolResolver])
"""
import logging
from typing import Any, Dict, Optional

from aot.ai.services.resolvers.base_resolver import BaseActionResolver

logger = logging.getLogger(__name__)


class VirtualToolResolver(BaseActionResolver):
    """
    Routes virtual_tool_call to AoTDataToolService.

    @phase active
    @stability stable
    @dependency AoTDataToolService
    """

    def execute(
        self,
        action_type: str,
        target_id: Optional[str],
        params: Dict[str, Any],
        context: Optional[Dict[str, Any]],
        approved: bool = False,
    ) -> Dict[str, Any]:
        from aot.ai.services.aot_data_tool_service import AoTDataToolService

        # [TASK_37] LLM sometimes puts tool_name in target_id — fallback
        tool_name = params.get('tool_name') or target_id
        arguments = params.get('arguments') or params.get('params') or {}

        # Flattened params fallback: LLM sometimes puts args directly in params
        if not arguments:
            # Exclude internal framework keys that are NOT tool arguments
            _meta_keys = {'tool_name', 'server_id', 'agent_unique_id', 'context'}
            _flat = {k: v for k, v in params.items() if k not in _meta_keys}
            if _flat:
                arguments = _flat
                logger.debug(
                    f"[VirtualToolResolver] Flattened params fallback for '{tool_name}': "
                    f"{list(arguments.keys())}"
                )

        if not tool_name:
            return {"status": "error", "message": "Missing tool_name for virtual_tool_call"}

        tool_map = {
            'get_sensor_detail': AoTDataToolService.get_sensor_detail,
            'get_spatial_tree': AoTDataToolService.get_spatial_tree,
            'search_devices': AoTDataToolService.search_devices,
            'get_device_list': AoTDataToolService.get_device_list_tool,
            'search_notes': AoTDataToolService.search_notes_tool,
            'get_energy_report': AoTDataToolService.get_energy_report,
            'operate_device': AoTDataToolService.operate_device_tool,
            'add_schedule': AoTDataToolService.add_schedule_tool,
            'schedule_device_control': AoTDataToolService.schedule_device_control_tool,
            'get_weather': AoTDataToolService.get_weather_tool,
            # @ANCHOR: FUNCTION_MANAGEMENT_TOOLS
            'get_function_list': AoTDataToolService.get_function_list,
            'get_function_detail': AoTDataToolService.get_function_detail,
            'activate_function': AoTDataToolService.activate_function_tool,
            'deactivate_function': AoTDataToolService.deactivate_function_tool,
            'get_active_functions_summary': AoTDataToolService.get_active_functions_summary,
            # @ANCHOR: FUNCTION_CREATE_TOOLS
            'create_function': AoTDataToolService.create_function_tool,
            'modify_function_options': AoTDataToolService.modify_function_options,
            'get_device_measurements': AoTDataToolService.get_device_measurements,
        }
        handler = tool_map.get(tool_name)
        if not handler:
            return {"status": "error", "message": f"Unknown virtual tool: {tool_name}"}

        # @ANCHOR: ARGUMENT_ALIAS_NORMALIZERS
        # LLM sometimes generates parameter names that differ from the actual
        # function signature.  Normalize them here before dispatch so the handler
        # never receives an unexpected keyword argument.
        # Pattern: { tool_name: { llm_key: real_key, ... } }
        _alias_maps: Dict[str, Dict[str, str]] = {
            'get_sensor_detail': {
                'device_id': 'loc_id',
                'unique_id': 'loc_id',
                'sensor_id': 'loc_id',
                'location_id': 'loc_id',
                'id':          'loc_id',
            },
        }
        if tool_name in _alias_maps:
            _am = _alias_maps[tool_name]
            _before = list(arguments.keys())
            arguments = {_am.get(k, k): v for k, v in arguments.items()}
            _after = list(arguments.keys())
            if _before != _after:
                logger.debug(
                    f"[VirtualToolResolver] alias-normalized '{tool_name}': "
                    f"{_before} → {_after}"
                )

        try:
            result = handler(**arguments)
            # @ANCHOR: VIRTUAL_TOOL_ERROR_PROPAGATION
            # If tool returns {"error": "..."} dict, propagate as error status
            # so execute_logged_action marks history as 'failed' and frontend shows ✗.
            if isinstance(result, dict) and result.get('error'):
                logger.warning(f"[VirtualToolResolver] {tool_name} returned error: {result['error']}")
                return {"status": "error", "message": result['error'], "result": result}
            return {"status": "success", "result": result}
        except Exception as e:
            logger.error(f"[VirtualToolResolver] {tool_name} failed: {e}")
            return {"status": "error", "message": str(e)}
