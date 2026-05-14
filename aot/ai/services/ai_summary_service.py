# coding=utf-8
import logging
import json
from datetime import datetime, timedelta
from aot.utils.time_utils import get_local_now, utc_now
from typing import Optional, Dict, Any, List
from sqlalchemy import desc

from aot.aot_flask.extensions import db
from aot.databases.models.ai_summary import AISystemSummary
# @ANCHOR: DECOUPLED_VIA_AI_CALLER_INTERFACE (IMP-007)
# AIAgentService accessed via lazy imports inside each method to prevent
# circular dependency. Top-level import removed per SBS-002_V2.

logger = logging.getLogger(__name__)

class AISummaryService:
    """
    v26.0: Core service for generating hierarchical system summaries (Semantic Snapshots).
    Includes incremental update logic and AI coordination.

    @phase active
    @stability unstable
    @dependency AISystemSummary
    """

    @staticmethod
    def get_latest_summary(scope_type: str = 'system', scope_id: Optional[str] = None) -> Optional[AISystemSummary]:
        """Retrieve the most recent active summary for a given scope."""
        query = AISystemSummary.query.filter_by(
            scope_type=scope_type,
            scope_id=scope_id,
            is_active=True
        ).order_by(desc(AISystemSummary.timestamp))
        return query.first()

    @staticmethod
    def should_generate_new_summary(
        scope_type: str, 
        scope_id: Optional[str], 
        current_metrics: Dict[str, Any],
        threshold: float = 0.05
    ) -> bool:
        """
        Incremental Logic: Check if metrics have deviated enough to warrant a new summary.
        Default threshold is 5% deviation.
        """
        latest = AISummaryService.get_latest_summary(scope_type, scope_id)
        if not latest:
            return True # First run
        
        # Check time interval (minimum 1 hour unless forced)
        if utc_now().replace(tzinfo=None) - latest.timestamp < timedelta(hours=1):
            return False

        try:
            prev_metrics = json.loads(latest.metadata_json) if latest.metadata_json else {}
        except:
            return True

        # Simplified deviation check for key metrics (e.g., active devices, error rates)
        # Note: Detailed implementation will depend on gathered data structure
        for key in ['active_devices', 'error_rate', 'total_count']:
            if key in current_metrics and key in prev_metrics:
                prev_val = prev_metrics[key]
                curr_val = current_metrics[key]
                if prev_val == 0:
                    if curr_val > 0: return True
                    continue
                
                deviation = abs(curr_val - prev_val) / prev_val
                if deviation > threshold:
                    logger.info(f"Summary trigger: Metric '{key}' deviated by {deviation:.2%}")
                    return True
        
        return False

    @staticmethod
    def gather_scope_data(scope_type: str, scope_id: Optional[str]) -> Dict[str, Any]:
        """
        Collect system state data for the specified scope.
        Implement hierarchical data aggregation logic (System > Farm > Zone > Device).
        """
        from aot.databases.models import Input, GeoMap, GeoShape, DeviceMeasurements
        
        data = {
            'timestamp': utc_now().isoformat(),
            'scope_type': scope_type,
            'scope_id': scope_id,
            'metrics': {
                'total_devices': 0,
                'active_devices': 0,
                'total_measurements': 0,
                'active_measurements': 0,
                'error_rate': 0.0
            },
            'structure': {},
            'recent_events': []
        }

        # 1. Base Query for Inputs (Devices) based on scope
        query = Input.query
        if scope_type == 'farm' and scope_id:
            query = query.filter(Input.map_config_id == scope_id)
        elif scope_type == 'device_group' and scope_id:
            query = query.filter(Input.map_overlay_id == int(scope_id))
        elif scope_type == 'device' and scope_id:
            query = query.filter(Input.unique_id == scope_id)
        
        devices = query.all()
        data['metrics']['total_devices'] = len(devices)
        data['metrics']['active_devices'] = len([d for d in devices if d.is_activated])
        
        # 2. Gather measurements for these devices
        device_ids = [d.unique_id for d in devices]
        measurements = DeviceMeasurements.query.filter(DeviceMeasurements.device_id.in_(device_ids)).all()
        data['metrics']['total_measurements'] = len(measurements)
        data['metrics']['active_measurements'] = len([m for m in measurements if m.is_enabled])
        
        # 3. Structural Info (Site/Zone names)
        if scope_type == 'system':
            data['structure']['farms'] = [m.name for m in GeoMap.query.all()]
        elif scope_type == 'farm' and scope_id:
            farm = GeoMap.query.filter_by(unique_id=scope_id).first()
            data['structure']['farm_name'] = farm.name if farm else "Unknown"
            data['structure']['zones'] = [s.feature.get('properties', {}).get('name', 'Unnamed') 
                                        for s in GeoShape.query.filter_by(geo_id=scope_id, type='zone').all()]

        # 4. Error/Event Integration (Placeholder)
        # In a real scenario, we would query AITaskHistory or system logs
        
        return data

    @staticmethod
    def generate_system_summary(
        agent_id: str = 'auto',
        scope_type: str = 'system',
        scope_id: Optional[str] = None,
        force: bool = False
    ) -> Optional[AISystemSummary]:
        """
        Main entry point for generating a summary.
        Coordinates data gathering, incremental check, and AI generation via AIAgentService.
        """
        # Check if AI features are enabled
        from aot.databases.models import AIGlobalSettings
        ai_settings = AIGlobalSettings.query.first()
        if not ai_settings or not ai_settings.ai_enabled:
            logger.info("AI features are disabled. Skipping summary generation.")
            return None
        
        current_data = AISummaryService.gather_scope_data(scope_type, scope_id)
        
        # Incremental check using simplified metrics map
        check_metrics = {
            'active_devices': current_data['metrics']['active_devices'],
            'total_count': current_data['metrics']['total_devices'],
            'error_rate': current_data['metrics']['error_rate']
        }
        
        if not force and not AISummaryService.should_generate_new_summary(scope_type, scope_id, check_metrics):
            logger.info(f"Skipping summary generation for {scope_type}:{scope_id} - no significant change.")
            return AISummaryService.get_latest_summary(scope_type, scope_id)

        start_time = utc_now()
        
        # 1. Select Agent
        agent = None
        if agent_id == 'auto':
            # Prefer 'synthesizer' or 'supervisor' for summarization
            from aot.databases.models import AIAgent
            agent = (AIAgent.query.filter_by(pipeline_role='synthesizer', is_activated=True).first() or
                     AIAgent.query.filter_by(role='supervisor', is_activated=True).first())
        else:
            from aot.databases.models import AIAgent
            agent = AIAgent.query.filter_by(unique_id=agent_id).first()
        
        if not agent:
            logger.error("No suitable AI agent found for summary generation.")
            return None

        # 2. Prepare Context & Prompt
        latest_summary = AISummaryService.get_latest_summary(scope_type, scope_id)
        prev_text = latest_summary.summary_text if latest_summary else "No previous summary available."
        
        # Token-optimized data injection (Token Diet)
        # If detail data is too large, we could truncate here
        data_str = json.dumps(current_data, indent=2, ensure_ascii=False)
        if len(data_str) > 10000: # Simple threshold for POC
            logger.warning("Scope data too large, applying token diet (truncating details).")
            current_data['details'] = "[REMOVED FOR TOKEN SAVING]"
            data_str = json.dumps(current_data, indent=2, ensure_ascii=False)

        prompt = f"""
        당신은 AoT(AI of Things) 시스템의 상황 분석 전문가입니다.
        아래 데이터를 바탕으로 현재 시스템 상태에 대한 'Semantic Snapshot'(의미론적 요약)을 작성하세요.
        
        [범위]: {scope_type} ({scope_id if scope_id else '전체 시스템'})
        [이전 요약]: {prev_text}
        
        [현재 상태 데이터]:
        {data_str}
        
        [지시사항]:
        1. 현재 시스템의 전반적인 건강 상태와 연결성을 평가하세요.
        2. 이전 상태와 비교하여 발생한 주요 변화(증분 변화)를 기술하세요.
        3. 주의가 필요한 잠재적 위험 요소나 이상 징후를 식별하세요.
        4. 사용자가 시스템의 상황을 한눈에 파악할 수 있도록 명확하고 전문적인 한국어로 작성하세요.
        
        응답은 자연어 요약문만 포함하세요.
        """

        try:
            from aot.ai.services.ai_agent_service import AIAgentService  # lazy — avoids circular import
            engine = AIAgentService.get_engine(agent.unique_id)
            if not engine:
                raise ValueError(f"Failed to initialize engine for agent {agent.unique_id}")
            
            # Context is minimal for snapshots to save tokens
            ai_context = {
                "current_time": get_local_now().strftime("%Y-%m-%d %H:%M:%S"),
                "scope_info": {"type": scope_type, "id": scope_id}
            }
            
            result = engine.run_reasoning(ai_context, prompt)
            summary_text = result.get('insight', '요약을 생성할 수 없습니다.')
            
            # Anomaly Detection Integration (Phase 26.3)
            from aot.ai.services.ai_anomaly_detector import AIAnomalyDetector
            anomaly_result = AIAnomalyDetector.detect_anomalies(current_data, latest_summary)
            
            new_summary = AISystemSummary(
                summary_text=summary_text,
                scope_type=scope_type,
                scope_id=scope_id,
                version=(latest_summary.version + 1) if latest_summary else 1,
                previous_summary_id=latest_summary.unique_id if latest_summary else None,
                generation_time_ms=int((utc_now() - start_time).total_seconds() * 1000),
                token_count=len(prompt.split()) + len(summary_text.split()), # Rough estimation
                metadata_json=json.dumps(current_data, ensure_ascii=False),
                anomaly_detected=anomaly_result.get('anomaly_detected', False),
                alert_level=anomaly_result.get('alert_level', 'none'),
                change_summary=json.dumps(anomaly_result.get('anomalies', []), ensure_ascii=False)
            )
            new_summary.save()
            
            # Trigger Alerts if needed (Phase 26.3)
            if new_summary.anomaly_detected:
                scope_info = {
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "scope_name": current_data.get('name', scope_type)
                }
                AIAnomalyDetector.trigger_alerts(
                    anomaly_result,
                    scope_info,
                    summary_text=summary_text
                )
                # OI-02: trigger immediate context broadcast on warning/critical anomaly
                if anomaly_result.get('alert_level') in ('warning', 'critical'):
                    try:
                        from aot.ai.services.ai_scheduler_service import AISchedulerService
                        AISchedulerService.trigger_context_broadcast_now()
                    except Exception as _oi02_exc:
                        logger.warning("OI-02 context broadcast trigger failed: %s", _oi02_exc)

            # Redis Caching (Phase 26.4)
            from aot.ai.services.cache_manager import CacheManager
            CacheManager.set_latest_summary(scope_type, scope_id, new_summary)
            
            logger.info(f"Successfully generated summary v{new_summary.version} for {scope_type}")
            return new_summary
            
        except Exception as e:
            logger.error(f"Error during AI summary generation: {e}", exc_info=True)
            return None

    @staticmethod
    def get_summary_history(scope_type: str, scope_id: Optional[str], limit: int = 10) -> List[AISystemSummary]:
        """Retrieve recent summaries for a given scope."""
        return AISystemSummary.query.filter_by(
            scope_type=scope_type,
            scope_id=scope_id,
            is_active=True
        ).order_by(desc(AISystemSummary.timestamp)).limit(limit).all()

    @staticmethod
    def generate_comparison(summary_id_1: str, summary_id_2: str) -> Dict[str, Any]:
        """
        Use an AI agent to compare two snapshots and highlight critical changes.
        """
        # Check if AI features are enabled
        from aot.databases.models import AIGlobalSettings
        ai_settings = AIGlobalSettings.query.first()
        if not ai_settings or not ai_settings.ai_enabled:
            return {"error": "AI features are disabled"}
        
        s1 = AISystemSummary.query.filter_by(unique_id=summary_id_1).first()
        s2 = AISystemSummary.query.filter_by(unique_id=summary_id_2).first()
        
        if not s1 or not s2:
             return {"error": "One or both summaries not found."}

        # Select agent
        from aot.databases.models import AIAgent
        agent = (AIAgent.query.filter_by(pipeline_role='synthesizer', is_activated=True).first() or
                 AIAgent.query.filter_by(role='supervisor', is_activated=True).first())
        
        if not agent:
            return {"error": "No suitable agent for comparison found."}

        prompt = f"""
        당신은 AoT 시스템 분석 전문가입니다. 아래 두 시점의 시스템 스냅샷을 비교하여 주요 변화와 트렌드를 분석하세요.
        
        [스냅샷 1 ({s1.timestamp})]:
        {s1.summary_text}
        
        [스냅샷 2 ({s2.timestamp})]:
        {s2.summary_text}
        
        [지시사항]:
        1. 두 시점 사이의 가장 중요한 상태 변화 3가지를 꼽으세요.
        2. 시스템 건강 상태가 개선되었는지, 악화되었는지 평가하세요.
        3. 향후 주의 깊게 관찰해야 할 지표나 장치를 제안하세요.
        
        응답은 자연어 분석문만 포함하세요.
        """

        try:
            from aot.ai.services.ai_agent_service import AIAgentService  # lazy — avoids circular import
            engine = AIAgentService.get_engine(agent.unique_id)
            if not engine:
                raise ValueError("Engine initialization failed.")

            result = engine.run_reasoning({}, prompt)
            return {
                "comparison": result.get('insight', '비교 결과 생성 실패'),
                "s1": {"id": s1.unique_id, "timestamp": s1.timestamp.isoformat()},
                "s2": {"id": s2.unique_id, "timestamp": s2.timestamp.isoformat()}
            }
        except Exception as e:
            logger.error(f"Comparison error: {e}")
            return {"error": str(e)}

    @staticmethod
    def analyze_trends(scope_type: str, scope_id: Optional[str], limit: int = 7) -> Dict[str, Any]:
        """
        v26.9: AI-driven longitudinal analysis of system health.
        """
        # Check if AI features are enabled
        from aot.databases.models import AIGlobalSettings
        ai_settings = AIGlobalSettings.query.first()
        if not ai_settings or not ai_settings.ai_enabled:
            return {"error": "AI features are disabled"}
        
        history = AISummaryService.get_summary_history(scope_type, scope_id, limit=limit)
        if not history:
            return {"error": "No history found for trend analysis."}
            
        # Select agent
        from aot.databases.models import AIAgent
        agent = (AIAgent.query.filter_by(pipeline_role='synthesizer', is_activated=True).first() or
                 AIAgent.query.filter_by(role='supervisor', is_activated=True).first())
        
        if not agent:
            return {"error": "No suitable agent for trend analysis found."}

        history_texts = [f"[{s.timestamp}]: {s.summary_text}" for s in history]
        history_combined = "\n\n".join(history_texts)

        prompt = f"""
        당신은 AoT 시스템의 데이터 분석 전문가입니다. 최근 {len(history)}개의 스냅샷을 분석하여 중장기 트렌드를 보고하세요.
        
        [이력 데이터]:
        {history_combined}
        
        [지시사항]:
        1. 시스템의 전반적인 건강 상태가 어떤 방향(개선/악화/현상유지)으로 이동하고 있는지 진단하세요.
        2. 이 기간 동안 관찰된 가장 뚜렷한 패턴이나 반복되는 이슈를 식별하세요.
        3. 향후 1주간의 시스템 상태를 예측하고 권장 조치를 제안하세요.
        
        응답은 자연어 분석문만 포함하세요.
        """

        try:
            from aot.ai.services.ai_agent_service import AIAgentService
            engine = AIAgentService.get_engine(agent.unique_id)
            if not engine:
                raise ValueError("Engine initialization failed.")
                
            result = engine.run_reasoning({}, prompt)
            return {
                "trends": result.get('insight', '트렌드 분석 실패'),
                "sample_size": len(history),
                "scope": {"type": scope_type, "id": scope_id}
            }
        except Exception as e:
            logger.error(f"Trend analysis error: {e}")
            return {"error": str(e)}

    @staticmethod
    def archive_old_summaries(days: int = 30) -> int:
        """
        Deactivate summaries older than X days to keep context retrieval efficient.
        """
        cutoff = utc_now().replace(tzinfo=None) - timedelta(days=days)
        old_summaries = AISystemSummary.query.filter(
            AISystemSummary.timestamp < cutoff,
            AISystemSummary.is_active == True
        ).all()
        
        count = 0
        for s in old_summaries:
            s.is_active = False
            count += 1
        
        if count > 0:
            db.session.commit()
            logger.info(f"Archived {count} old AI summaries.")
        return count
