import logging
from aot.utils.time_utils import utc_now
from aot.utils.tz_utils import now_utc, to_utc
from datetime import datetime, timedelta
from sqlalchemy import or_

from aot.aot_flask.extensions import db
from aot.databases.models import Input, Output, Camera, GeoShape, GeoLayer, DeviceMeasurements, Conversion, EnergyUsage, Misc, Notes
from aot.ai.services.ai_context_service import AIContextService
from aot.ai.services.ai_action_service import AIActionService
from aot.utils.influx import read_influxdb_list
from aot.utils.tools import return_energy_usage
from aot.utils.system_pi import return_measurement_info

logger = logging.getLogger(__name__)

class AoTDataToolService:
    """
    AoT 내부 데이터를 AI 도구 규격에 맞게 제공하는 서비스 레이어.
    가상 MCP 워커(mcp_aot)가 이를 호출합니다.

    @phase active
    @stability stable
    """

    @staticmethod
    def _check_influxdb_available():
        """InfluxDB 연결 가능 여부를 사전 점검합니다."""
        try:
            settings = Misc.query.first()
            if not settings:
                return False, "시스템 설정(Misc)을 찾을 수 없습니다."
            if settings.measurement_db_name != 'influxdb':
                return False, f"측정 DB가 InfluxDB가 아닙니다: {settings.measurement_db_name}"
            if not settings.measurement_db_version:
                return False, "InfluxDB 버전이 설정되지 않았습니다. 시스템 설정에서 측정 DB를 확인하세요."
            if not settings.measurement_db_host or settings.measurement_db_port in (None, 0, '0', ''):
                return False, "InfluxDB 호스트/포트가 설정되지 않았습니다."

            # 실제 연결 테스트 (Docker 컨테이너 내에서 localhost → host.docker.internal 변환)
            import requests as req
            from aot.config import DOCKER_CONTAINER
            _host = settings.measurement_db_host
            if DOCKER_CONTAINER and _host in ('localhost', '127.0.0.1'):
                _host = 'host.docker.internal'
            url = f"http://{_host}:{settings.measurement_db_port}/health"
            resp = req.get(url, timeout=3)
            if resp.status_code != 200:
                return False, f"InfluxDB 서버 응답 오류 (HTTP {resp.status_code})"
            return True, "OK"
        except req.exceptions.ConnectionError:
            return False, f"InfluxDB 서버에 연결할 수 없습니다 ({settings.measurement_db_host}:{settings.measurement_db_port}). 서버가 실행 중인지 확인하세요."
        except Exception as e:
            return False, f"InfluxDB 점검 중 오류: {str(e)}"

    @staticmethod
    def _get_last_values_fallback(target_input, device_measurements):
        """InfluxDB 사용 불가 시 read_influxdb_single(LAST)로 최신 값만 시도합니다."""
        from aot.utils.influx import read_influxdb_single
        results = []
        for m in device_measurements:
            conversion = Conversion.query.filter(Conversion.unique_id == m.conversion_id).first() if m.conversion_id else None
            channel, unit, measurement = return_measurement_info(m, conversion)
            try:
                last = read_influxdb_single(
                    target_input.unique_id, unit, channel,
                    measure=measurement, duration_sec=86400, value='LAST', datetime_obj=True
                )
                if last and last[0] is not None and last[1] is not None:
                    results.append({
                        "device_name": target_input.name or target_input.unique_id,
                        "measurement": measurement or m.measurement,
                        "last_value": round(last[1], 2),
                        "last_time": last[0].isoformat() if hasattr(last[0], 'isoformat') else str(last[0]),
                        "unit": unit,
                        "note": "시계열 조회 실패 - 최신 값만 제공"
                    })
            except Exception:
                pass
        return results

    @staticmethod
    def get_sensor_detail(loc_id, sensor_type=None, time_range="24h", limit=None):
        """
        특정 위치/장치의 상세 센서 이력을 조회합니다.
        :param loc_id: 장치(Input) 또는 구역(GeoShape)의 unique_id
        :param sensor_type: 필터링할 센서 타입 (예: temperature, humidity)
        :param time_range: 조회 범위 ("1h", "24h", "7d" 등)
        :param limit: 반환할 최근 readings 수 (기본: 20, 현재 날씨 조회 시 1 권장)
        """
        try:
            # 1. 대상 식별 (Input 우선: unique_id 또는 map_config_id/geo_id 지원)
            target_input = Input.query.filter(
                or_(Input.unique_id == loc_id, Input.map_config_id == loc_id)
            ).first()

            if not target_input:
                # 구역인 경우 (unique_id 또는 geo_id 지원)
                target_zone = GeoShape.query.filter(
                    or_(GeoShape.unique_id == loc_id, GeoShape.geo_id == loc_id)
                ).first()
                # [WEATHER_TOOL_UNIFICATION] Name-based fallback: loc_id may be a zone name (e.g. '1포장')
                # not a UUID. Match by feature.properties.name so both get_sensor_detail and
                # get_weather behave consistently regardless of which tool the AI selects.
                if not target_zone and loc_id:
                    import json as _json_sd
                    _loc_lower = str(loc_id).strip().lower()
                    for _shape in GeoShape.query.all():
                        try:
                            _feat = _shape.feature if isinstance(_shape.feature, dict) else _json_sd.loads(_shape.feature or '{}')
                            _props = _feat.get('properties') or {}
                            _sname = str(_props.get('name') or _props.get('label') or _props.get('title') or '').lower()
                            if _sname and (_loc_lower in _sname or _sname in _loc_lower):
                                target_zone = _shape
                                break
                        except Exception:
                            continue
                if target_zone:
                    # In Mycodo/AoT, Input is linked to GeoShape via map_overlay_id (Integer ID)
                    target_input = Input.query.filter(Input.map_overlay_id == target_zone.id).first()

            if not target_input:
                # If no sensor is directly linked to the zone, return the zone's coordinates 
                # so the caller (AI) can use an external weather tool if needed.
                if target_zone and target_zone.feature:
                    props = target_zone.feature.get('properties', {})
                    geom = target_zone.feature.get('geometry', {})
                    return {
                        "message": f"구역 '{props.get('name', 'Unknown')}'에 직접 연결된 센서가 없습니다.",
                        "zone_name": props.get('name'),
                        "zone_id": target_zone.unique_id,
                        "location": geom.get('coordinates'),
                        "suggestion": "이 좌표를 사용하여 기상 정보를 조회할 수 있습니다."
                    }
                return {"error": f"장치 또는 구역을 찾을 수 없습니다: {loc_id}"}

            # 2. 측정값 정보 획득
            device_measurements = DeviceMeasurements.query.filter(DeviceMeasurements.device_id == target_input.unique_id).all()
            if not device_measurements:
                return {"error": f"이 장치({target_input.name})에 정의된 측정값이 없습니다."}

            # 필터링 적용 (Sensory Keyword Normalization)
            if sensor_type:
                s_type_map = {
                    '온도': 'temperature', 'temp': 'temperature',
                    '습도': 'humidity', 'hum': 'humidity',
                    '조도': 'light', 'lux': 'light',
                    '수분': 'moisture', '토양': 'moisture',
                    '기상': 'weather', '날씨': 'weather', 'atmosphere': 'weather',
                    '배터리': 'battery', 'vbat': 'battery'
                }
                # Normalize search term
                search_term = sensor_type.lower()
                for ko, en in s_type_map.items():
                    if ko in search_term:
                        search_term = en
                        break

                if search_term == 'weather':
                    # Special Case: 'weather' maps to multiple common atmospheric metrics
                    weather_metrics = ['temperature', 'humidity', 'pressure', 'wind', 'rain', 'solar', 'uv', 'dewpoint', 'speed', 'direction']
                    device_measurements = [m for m in device_measurements if any(wm in (m.measurement or "").lower() for wm in weather_metrics)]
                else:
                    device_measurements = [m for m in device_measurements if search_term in (m.measurement or "").lower()]

            if not device_measurements:
                return {"error": f"'{sensor_type}' 타입에 해당하는 측정값이 없습니다."}

            # 3. InfluxDB 연결 사전 점검
            influx_ok, influx_msg = AoTDataToolService._check_influxdb_available()
            if not influx_ok:
                logger.warning(f"[AoTDataTool] InfluxDB 사용 불가: {influx_msg}")
                # 폴백: 최신 값이라도 반환 시도
                fallback = AoTDataToolService._get_last_values_fallback(target_input, device_measurements)
                if fallback:
                    return {
                        "warning": f"InfluxDB 사용 불가 ({influx_msg}). 최신 값만 제공합니다.",
                        "data": fallback
                    }
                # 폴백도 실패 시 장치 메타데이터라도 반환
                meta = []
                for m in device_measurements:
                    conversion = Conversion.query.filter(Conversion.unique_id == m.conversion_id).first() if m.conversion_id else None
                    channel, unit, measurement = return_measurement_info(m, conversion)
                    meta.append({"measurement": measurement or m.measurement, "unit": unit})
                return {
                    "error": f"InfluxDB 사용 불가: {influx_msg}",
                    "device_name": target_input.name or target_input.unique_id,
                    "device_id": target_input.unique_id,
                    "available_measurements": meta,
                    "suggestion": "InfluxDB 서버 상태를 확인하거나, 시스템 설정에서 측정 DB 설정을 점검하세요."
                }

            # 4. InfluxDB 시계열 조회
            offset_sec = AoTDataToolService._parse_range(time_range)
            results = []

            for m in device_measurements:
                conversion = Conversion.query.filter(Conversion.unique_id == m.conversion_id).first() if m.conversion_id else None
                channel, unit, measurement = return_measurement_info(m, conversion)

                data = read_influxdb_list(
                    target_input.unique_id,
                    unit,
                    channel,
                    measure=measurement,
                    duration_sec=offset_sec,
                    datetime_obj=True
                )

                if data:
                    readings = [{"t": row[0].isoformat(), "v": round(row[1], 2), "u": unit} for row in data]
                    values = [row[1] for row in data]
                    _keep = int(limit) if limit else 20
                    results.append({
                        "device_name": target_input.name or target_input.unique_id,
                        "measurement": measurement or m.measurement,
                        "readings": readings[-_keep:],  # limit 파라미터로 조절 (기본 20건)
                        "total_readings": len(readings),
                        "stats": {
                            "min": round(min(values), 2),
                            "max": round(max(values), 2),
                            "avg": round(sum(values) / len(values), 2),
                            "count": len(values)
                        }
                    })

            if results:
                return results

            # InfluxDB는 접속됐지만 데이터가 없는 경우
            return {
                "message": f"'{target_input.name}' 장치의 최근 {time_range} 데이터가 없습니다.",
                "device_id": target_input.unique_id,
                "time_range": time_range
            }

        except Exception as e:
            logger.exception("Error in get_sensor_detail")
            return {"error": f"센서 데이터 조회 중 오류 발생: {str(e)}"}

    @staticmethod
    def get_spatial_tree(depth=2, filter_type=None):
        """
        시스템의 공간 계층 구조를 트리 형태로 반환합니다.
        """
        try:
            full_tree = AIContextService.get_spatial_hierarchy()
            # depth 및 filter_type에 따른 가지치기는 추후 복잡도에 따라 구현 가능
            # 현재는 전체 트리를 반환하거나 기본적인 필터링만 수행
            if filter_type:
                # 간단한 타입 필터링 예시
                def filter_node(node):
                    if 'children' in node:
                        node['children'] = [filter_node(c) for c in node['children'] if c.get('type') == filter_type or 'children' in c]
                    return node
                full_tree = [filter_node(n) for n in full_tree]
                
            return {"hierarchy": full_tree}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def search_devices(query):
        """
        이름 또는 타입으로 장치를 검색합니다.
        v2: Multi-token query expansion.
          - Splits query by whitespace and searches each token independently
            (e.g. "1구역 밸브" → searches "1구역" AND "밸브" separately).
          - Loads term aliases from AIDomainGlossary (category='term_alias')
            to handle user-specific terms (e.g. "1포장" → "1구역").
          - Deduplicates results by unique_id.
        """
        if not query:
            return {"error": "Query string is empty"}

        try:
            import re

            def _normalize_variants(term):
                """Generate search variants for a term to handle spacing differences.
                e.g. '밸브3' → ['밸브3', '밸브 3']
                     '밸브 3' → ['밸브 3', '밸브3']
                """
                variants = [term]
                # Collapse all whitespace → no-space variant
                no_space = re.sub(r'\s+', '', term)
                if no_space != term:
                    variants.append(no_space)
                # Insert space between Korean (Hangul) block and digit (or vice versa)
                spaced = re.sub(r'([\uAC00-\uD7A3])(\d)', r'\1 \2', term)
                spaced = re.sub(r'(\d)([\uAC00-\uD7A3])', r'\1 \2', spaced)
                if spaced != term:
                    variants.append(spaced)
                return variants

            # Build search token list: individual tokens + full query
            tokens = [t.strip() for t in query.split() if t.strip()]
            _base_terms = [query] + tokens
            # Expand each base term with normalization variants
            _expanded = []
            for t in _base_terms:
                for v in _normalize_variants(t):
                    if v not in _expanded:
                        _expanded.append(v)
            search_terms = _expanded

            # Load term aliases from AIDomainGlossary
            try:
                from aot.databases.models.ai_domain_glossary import AIDomainGlossary
                alias_rows = AIDomainGlossary.query.filter_by(category='term_alias', is_active=True).all()
                alias_map = {a.term.lower(): a.definition for a in alias_rows}
            except Exception:
                alias_map = {}

            # Expand each token with its alias (if any), including normalization variants
            for token in list(tokens):
                canonical = alias_map.get(token.lower())
                if canonical:
                    for v in _normalize_variants(canonical):
                        if v not in search_terms:
                            search_terms.append(v)

            seen_ids = set()
            results = []

            for term in search_terms:
                q = f"%{term}%"
                for item in Input.query.filter(
                    or_(Input.name.like(q), Input.device.like(q))
                ).all():
                    if item.unique_id not in seen_ids:
                        seen_ids.add(item.unique_id)
                        results.append({"id": item.unique_id, "name": item.name, "type": "input", "device": item.device})

                for item in Output.query.filter(
                    or_(Output.name.like(q), Output.output_type.like(q))
                ).all():
                    if item.unique_id not in seen_ids:
                        seen_ids.add(item.unique_id)
                        results.append({"id": item.unique_id, "name": item.name, "type": "output", "device": item.output_type})

                for item in Camera.query.filter(
                    or_(Camera.name.like(q), Camera.camera_type.like(q))
                ).all():
                    if item.unique_id not in seen_ids:
                        seen_ids.add(item.unique_id)
                        results.append({"id": item.unique_id, "name": item.name, "type": "camera", "device": item.camera_type})

                # v26.10: Include GeoShapes (Sites/Zones) in search results
                # v26.11: Also check feature.properties.name (GeoJSON standard field)
                for item in GeoShape.query.all():
                    feat = item.feature or {}
                    feat_props = feat.get('properties', {})
                    meta = item.meta_json or {}
                    meta_props = meta.get('properties', {})
                    name = (feat_props.get('name') or feat_props.get('label')
                            or meta_props.get('name') or meta_props.get('label')
                            or item.geo_id)
                    if term.lower() in name.lower() or term.lower() in item.geo_id.lower():
                        if item.unique_id not in seen_ids:
                            seen_ids.add(item.unique_id)
                            results.append({
                                "id": item.unique_id,
                                "geo_id": item.geo_id,
                                "name": name,
                                "type": "zone",
                                "device": item.type
                            })

            return {"results": results, "count": len(results)}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def get_device_list_tool(**kwargs):
        """
        Returns all registered devices (inputs, outputs, cameras) with id/name/type.
        Used for full device listing queries (no keyword filter).

        @ANCHOR: GET_DEVICE_LIST_TOOL
        """
        try:
            results = []
            seen_ids = set()
            for item in Input.query.all():
                if item.unique_id not in seen_ids:
                    seen_ids.add(item.unique_id)
                    results.append({"id": item.unique_id, "name": item.name, "type": "input", "device": item.device})
            for item in Output.query.all():
                if item.unique_id not in seen_ids:
                    seen_ids.add(item.unique_id)
                    results.append({"id": item.unique_id, "name": item.name, "type": "output", "device": item.output_type})
            for item in Camera.query.all():
                if item.unique_id not in seen_ids:
                    seen_ids.add(item.unique_id)
                    results.append({"id": item.unique_id, "name": item.name, "type": "camera", "device": item.camera_type})
            return {"results": results, "count": len(results)}
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def get_energy_report(period="daily", zone_id=None):
        """
        에너지 사용량 분석 리포트를 생성합니다.
        """
        try:
            device_measurements_all = DeviceMeasurements.query.all()
            conversion_all = Conversion.query.all()
            
            if zone_id:
                energy_usage = EnergyUsage.query.join(Input, EnergyUsage.device_id == Input.unique_id).filter(Input.parent_id == zone_id).all()
            else:
                energy_usage = EnergyUsage.query.all()

            if not energy_usage:
                return {"message": "No energy sensors found for this zone/period"}

            stats, graph = return_energy_usage(energy_usage, device_measurements_all, conversion_all)
            
            # 리포트 가공
            report_data = []
            for uid, val in stats.items():
                target_usage = next((e for e in energy_usage if e.unique_id == uid), None)
                if target_usage:
                    report_data.append({
                        "sensor_id": uid,
                        "device_id": target_usage.device_id,
                        "usage": val
                    })

            summary = f"Energy analysis for {period}."
            if zone_id:
                summary += f" Filtering by Zone: {zone_id}."

            return {
                "summary": summary,
                "data": report_data,
                "insights": ["Usage is within normal parameters."] # Placeholder for AI logic
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def operate_device_tool(device_id, state, **kwargs):
        """
        [분류 A - 물리 제어 전용 도구]
        장치를 직접 제어합니다. (on, off, open, close, set_value 등)
        """
        try:
            if not device_id or not state:
                return {"error": "device_id 또는 state 누락"}

            # 1. 상태값 검증
            ALLOWED_STATES = ['on', 'off', 'open', 'close', 'set_value']
            state = state.lower()
            if state not in ALLOWED_STATES:
                return {"error": f"유효하지 않은 상태값입니다: {state}. 허용된 값: {ALLOWED_STATES}"}

            # 2. 장치 존재 여부 확인 (UUID 또는 이름)
            target = Output.query.filter(or_(Output.unique_id == device_id, Output.name == device_id)).first()
            if not target:
                return {"error": f"제어할 장치(output)를 찾을 수 없습니다: {device_id}"}

            # 3. 시간/값 파라미터 정규화 (Deep Discovery)
            # duration_seconds, duration_minutes, duration, value 등 다양한 variant 대응
            d_sec = kwargs.get('duration_seconds')
            d_min = kwargs.get('duration_minutes') or kwargs.get('duration')
            val = kwargs.get('value')
            
            # 우선순위: duration_seconds > duration_minutes/duration (*60) > value > 0
            if d_sec is not None:
                duration = float(d_sec)
            elif d_min is not None:
                duration = float(d_min) * 60.0
            else:
                duration = float(val or 0)

            # 4. @ANCHOR: OPERATE_DEVICE_CHANNEL_INJECTION (TASK_17)
            # Resolve physical output_channel from OutputChannel table before daemon call.
            # Eliminates 'output channel doesn't exist: None' — channel=0 is a valid integer.
            resolved_uid = target.unique_id
            output_channel = None
            try:
                from aot.databases.models.output import OutputChannel as _OC
                oc_row = _OC.query.filter_by(output_id=resolved_uid).first()
                if oc_row is not None and oc_row.channel is not None:
                    output_channel = int(oc_row.channel)
                    logger.info(
                        f"[operate_device_tool][CHANNEL_RESOLVED] "
                        f"device='{resolved_uid}' → output_channel={output_channel}"
                    )
                else:
                    # [PC-099-ERROR] DB diagnostic: row exists but channel is NULL, or no row at all
                    _diag = (
                        f"oc_row={oc_row!r}, "
                        f"channel={oc_row.channel if oc_row else 'NO_ROW'}, "
                        f"output_type='{target.output_type}'"
                    )
                    logger.error(
                        f"[PC-099-ERROR][CHANNEL_NULL] output_channel is None for "
                        f"device='{resolved_uid}'. DB diagnostic: {_diag}. "
                        f"Daemon call will proceed with channel=None — expect hardware error."
                    )
            except Exception as _ch_err:
                logger.error(
                    f"[PC-099-ERROR][CHANNEL_LOOKUP_FAILED] OutputChannel query failed "
                    f"for device='{resolved_uid}': {_ch_err}"
                )

            from aot.aot_client import DaemonControl
            daemon = DaemonControl()

            if state in ('on', 'open'):
                out_err, out_msg = daemon.output_on_off(
                    resolved_uid, 'on', output_type='sec', amount=duration,
                    output_channel=output_channel
                )
            elif state in ('off', 'close'):
                out_err, out_msg = daemon.output_on_off(
                    resolved_uid, 'off', output_type='sec', amount=0,
                    output_channel=output_channel
                )
            elif state == 'set_value':
                out_err, out_msg = daemon.output_on_off(
                    resolved_uid, 'on', output_type='value', amount=duration,
                    output_channel=output_channel
                )
            else:
                return {"error": f"미지원 상태: {state}"}

            if out_err:
                logger.error(f"[operate_device_tool] Daemon error: {out_msg}")
                return {"error": f"장치 제어 실패: {out_msg}"}
            
            logger.info(f"[operate_device_tool] OK: device={resolved_uid}({target.name}), state={state}, duration={duration}s")
            return {"status": "success", "execution_result": out_msg, "resolved_duration": duration}
        except Exception as e:
            logger.error(f"Error in operate_device_tool: {e}")
            return {"error": f"장치 제어 중 오류 발생: {str(e)}"}

    @staticmethod
    def _extract_spatial_tags(content):
        """내용에서 공간(장소/장치) 이름을 추출하여 태그 형태로 반환합니다."""
        if not content:
            return ""
        
        try:
            # 1. 공간 계층 구조 가져오기
            hierarchy = AIContextService.get_spatial_hierarchy()
            
            # 2. 모든 장소 이름 수집 (재귀적)
            all_names = set()
            def collect_names(nodes):
                for node in nodes:
                    if 'name' in node:
                        all_names.add(node['name'])
                    if 'children' in node:
                        collect_names(node['children'])
            
            collect_names(hierarchy)
            
            # 3. 매칭되는 이름 찾기
            found_tags = []
            for name in all_names:
                if name in content:
                    # 중복 방지를 위해 #를 붙여서 추가
                    tag = f"#{name.replace(' ', '_')}"
                    if tag not in found_tags:
                        found_tags.append(tag)
            
            return ", ".join(found_tags) if found_tags else ""
        except Exception as e:
            logger.error(f"Error in _extract_spatial_tags: {e}")
            return ""

    @staticmethod
    def add_schedule_tool(date, content, worker=None, time="09:00", tags=None):
        """
        [분류 B - 일정/계획 전용 도구]
        사람의 작업 일정이나 메모를 등록합니다. (SchedulerJobMeta 기반)
        제초작업, 점검, 청소 등 수동 작업에 사용.
        Routing: propose_job(action_type='human') -> approve_job(decided_by='AI')
        No APScheduler trigger is created for human-type schedules.
        """
        try:
            from aot.ai.services.ai_scheduler_service import AISchedulerService
            from datetime import datetime

            # 1. Parse run_at datetime (AI-provided time is treated as-is; stored in UTC column)
            dt_str = f"{date} {time}"
            run_at = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")

            # 2. Build job description and reasoning text
            job_name = content
            if worker:
                job_name = f"{content} (작업자: {worker})"

            # 3. Extract spatial tags for reasoning metadata
            spatial_tags = tags or AoTDataToolService._extract_spatial_tags(content)
            tag_label = f"ai_scheduled, human_work"
            if spatial_tags:
                tag_label += f", {spatial_tags}"

            reasoning = f"[human_schedule] {job_name} | tags: {tag_label}"

            # 4. Propose job as DRAFT (source_type='human' marks it as a human work item)
            meta = AISchedulerService.propose_job(
                action_type='human',
                target_id='none',
                params={'content': content, 'worker': worker or '', 'tags': tag_label},
                reasoning=reasoning,
                schedule_time=run_at,
                proposed_by='AI',
                approval_required=False,
                source_type='human',
            )

            # 5. Immediately approve — no APScheduler trigger for human schedules
            AISchedulerService.approve_job(meta.id, decided_by='AI')

            return {
                "status": "success",
                "message": f"일정이 등록되었습니다: {date} {time} - {content}",
                "job_id": meta.unique_id,
                "tags": tag_label,
            }
        except Exception as e:
            logger.error(f"Error in add_schedule_tool: {e}")
            return {"error": f"일정 등록 중 오류 발생: {str(e)}"}

    @staticmethod
    def search_notes_tool(query, category=None, limit=10):
        """
        [분류 C - 노트/일정 검색 전용 도구]
        키워드로 노트(메모, 일정, 작업 기록)를 검색합니다.
        name, tags, note 필드를 대상으로 LIKE 검색을 수행합니다.

        Args:
            query (str): 검색 키워드 (예: '콩밭', '제초', '1구역')
            category (str): 필터링할 카테고리 ('schedule', 'general', 'ai_log' 등). None이면 전체.
            limit (int): 최대 반환 건수 (기본 10)
        """
        try:
            if not query or not query.strip():
                return {"error": "검색 키워드가 비어있습니다."}

            from aot.databases.models.notes import Notes
            from sqlalchemy import or_

            _q = f"%{query.strip()}%"
            db_query = Notes.query.filter(
                Notes.is_archived == False,  # noqa: E712
                or_(
                    Notes.name.like(_q),
                    Notes.tags.like(_q),
                    Notes.note.like(_q),
                )
            )

            if category:
                db_query = db_query.filter(Notes.category == category)

            rows = db_query.order_by(Notes.date_time.desc()).limit(limit).all()

            if not rows:
                return {
                    "status": "success",
                    "count": 0,
                    "results": [],
                    "message": f"'{query}'에 해당하는 노트를 찾을 수 없습니다."
                }

            results = []
            for r in rows:
                results.append({
                    "note_id": r.unique_id,
                    "date": r.date_time.strftime("%Y-%m-%d %H:%M") if r.date_time else None,
                    "name": r.name,
                    "category": r.category,
                    "tags": r.tags,
                    "note": (r.note or "")[:300],
                    "target_id": r.target_id,
                })

            return {
                "status": "success",
                "count": len(results),
                "results": results,
                "query": query,
            }
        except Exception as e:
            logger.error(f"Error in search_notes_tool: {e}")
            return {"error": f"노트 검색 중 오류 발생: {str(e)}"}

    @staticmethod
    def schedule_device_control_tool(device_id, scheduled_time=None, state='on', duration_minutes=None,
                                     delay_seconds=None, duration_seconds=None, **kwargs):
        """
        [시스템 제어 예약 전용]
        밸브, 펌프, 스프링클러 등 시스템 장치의 제어를 특정 시간에 예약합니다.
        AISchedulerService.propose_job()으로 SchedulerJobMeta + APScheduler 등록까지 완료합니다.

        Accepts:
          scheduled_time: ISO 8601 string (absolute time) — preferred
          delay_seconds:  relative delay in seconds from now (alternative to scheduled_time)
          duration_minutes: run duration in minutes
          duration_seconds: run duration in seconds (alternative to duration_minutes)
        """
        try:
            from aot.utils.tz_utils import now_utc, to_utc
            from datetime import datetime, timedelta
            from aot.databases.models import Output
            from aot.ai.services.ai_scheduler_service import AISchedulerService

            # 1. 장치 확인 (UUID, 정확한 이름, 부분 이름 순서로 조회)
            output = Output.query.filter(or_(Output.unique_id == device_id, Output.name == device_id)).first()
            if not output:
                # Fuzzy fallback: ILIKE partial match
                output = Output.query.filter(Output.name.ilike(f'%{device_id}%')).first()
            if not output:
                return {"error": f"장치를 찾을 수 없습니다: {device_id}"}

            # 2. 시간 파싱 — scheduled_time 또는 delay_seconds 지원
            now = now_utc()
            if delay_seconds is not None:
                scheduled_dt = now + timedelta(seconds=int(delay_seconds))
            elif scheduled_time is not None:
                if isinstance(scheduled_time, str):
                    try:
                        scheduled_dt = datetime.fromisoformat(scheduled_time.replace('Z', '+00:00'))
                    except Exception:
                        return {"error": f"잘못된 시간 형식입니다: {scheduled_time}. ISO 8601 형식을 사용하세요."}
                else:
                    scheduled_dt = scheduled_time
                try:
                    scheduled_dt = to_utc(scheduled_dt)  # normalise to UTC-aware
                except ValueError:
                    return {"error": f"Ambiguous datetime (no timezone info): {scheduled_time}. Use ISO 8601 with timezone offset."}
                if scheduled_dt <= now:
                    return {"error": f"Requested schedule time {scheduled_time} is in the past. Please provide a future time."}
            else:
                return {"error": "scheduled_time 또는 delay_seconds 중 하나를 제공해야 합니다."}

            # 3. 시간 변환 — duration_seconds 지원
            if duration_seconds is not None:
                _duration_minutes = max(1, int(duration_seconds) // 60)
            elif duration_minutes is not None:
                _duration_minutes = int(duration_minutes)
            else:
                _duration_minutes = 5  # default

            duration_sec = _duration_minutes * 60

            # 3. SchedulerJobMeta 생성 + 자동 승인 (APScheduler 등록)
            #    proposed_by='HUMAN' + approval_required=False → propose_job() 내부에서 approve_job() 자동 호출
            meta = AISchedulerService.propose_job(
                action_type='control_output',
                target_id=output.unique_id,
                params={'state': state, 'duration_minutes': _duration_minutes},
                reasoning=f"사용자 요청: {output.name} {state} at {scheduled_dt.strftime('%H:%M')}",
                schedule_time=scheduled_dt,
                duration_sec=duration_sec,
                proposed_by='HUMAN',    # 사용자가 직접 지시 → 추가 승인 불필요
                approval_required=False  # → propose_job이 approve_job() 자동 호출
            )

            logger.info(f"[AI Schedule] Registered APScheduler job: {output.name} {state} at {scheduled_dt} (meta_id={meta.id if hasattr(meta, 'id') else meta})")
            return {
                "status": "success",
                "message": f"{scheduled_dt.strftime('%Y-%m-%d %H:%M:%S')}에 {output.name}을(를) {state}하도록 예약 완료 ({_duration_minutes}분간)",
                "scheduler_job_id": meta.id if hasattr(meta, 'id') else str(meta),
            }
        except Exception as e:
            logger.error(f"Error in schedule_device_control_tool: {e}")
            return {"error": f"장치 제어 예약 중 오류 발생: {str(e)}"}

    @staticmethod
    def analyze_system_failure_tool(device_id=None, tool_name=None, lookback_minutes=60, **kwargs):
        """
        @ANCHOR: ANALYZE_SYSTEM_FAILURE_TOOL
        [031_STEP_3] Diagnostic RAG — audit AITask failure logs and MCP bridge status.

        Called by the Planner when the user reports a hardware failure or
        when 'operate_device' returns PC-099-ERROR. Provides specific reasons
        instead of generic error codes.

        Args:
            device_id:         (optional) Target device UUID/name to filter logs.
            tool_name:         (optional) MCP tool name that failed (e.g. 'operate_device').
            lookback_minutes:  How far back to search AITask logs (default 60 min).

        Returns:
            dict with 'failure_summary', 'failed_tasks', 'mcp_status', 'recommendation'.
        """
        try:
            from aot.ai.services.mcp_bridge_service import MCPBridgeService
            from aot.utils.time_utils import utc_now

            cutoff = utc_now() - timedelta(minutes=int(lookback_minutes))

            # 1. Query recent failed AITask records
            failed_q = AITask.query.filter(
                AITask.status.in_(['failed', 'error']),
                AITask.created_at >= cutoff
            )
            if device_id:
                failed_q = failed_q.filter(
                    (AITask.target_id == device_id) | (AITask.title.contains(device_id))
                )
            failed_tasks_db = failed_q.order_by(AITask.created_at.desc()).limit(10).all()

            failed_tasks = []
            for t in failed_tasks_db:
                failed_tasks.append({
                    "task_id": t.unique_id,
                    "title": t.title,
                    "action_type": t.action_type,
                    "target_id": t.target_id,
                    "status": t.status,
                    "execution_result": (t.execution_result or '')[:300],
                    "created_at": t.created_at.isoformat() if t.created_at else None,
                })

            # 2. Query MCP server status
            mcp_status = []
            try:
                from aot.databases.models import MCPServer
                active_servers = MCPBridgeService.get_active_servers()
                all_servers = MCPServer.query.filter_by(is_activated=True).all()
                active_ids = {s.unique_id for s in active_servers}
                for srv in all_servers:
                    _is_degraded = srv.unique_id not in active_ids
                    mcp_status.append({
                        "name": srv.name,
                        "unique_id": srv.unique_id,
                        "is_degraded": _is_degraded,
                        "has_tool": tool_name in (srv.tool_names or []) if tool_name else None,
                    })
            except Exception as _mcp_err:
                logger.warning(f"[031_STEP_3] Could not query MCP status: {_mcp_err}")
                mcp_status = [{"error": str(_mcp_err)}]

            # 3. Build failure summary
            failure_reasons = []
            if not [s for s in mcp_status if not s.get('is_degraded') and not s.get('error')]:
                failure_reasons.append("모든 MCP 서버가 오프라인 또는 연결 불가 상태입니다.")
            elif tool_name:
                tool_server = next((s for s in mcp_status if s.get('has_tool') and not s.get('is_degraded')), None)
                if not tool_server:
                    failure_reasons.append(f"'{tool_name}' 도구를 제공하는 MCP 서버가 오프라인입니다.")

            for t in failed_tasks:
                err_text = t.get('execution_result', '')
                if 'PC-099-ERROR' in err_text:
                    failure_reasons.append(f"[{t['title']}] 물리적 실행 실패: {err_text[:150]}")
                elif 'Safety violation' in err_text:
                    failure_reasons.append(f"[{t['title']}] 안전 제약 위반으로 차단됨.")
                elif err_text:
                    failure_reasons.append(f"[{t['title']}] 오류: {err_text[:150]}")

            recommendation = "MCP 서버 상태를 확인하고 서버를 재시작하거나 장치 연결을 점검하세요."
            if not failure_reasons:
                recommendation = "최근 실패 기록이 없습니다. 장치 전원 및 네트워크 연결을 점검하세요."

            return {
                "failure_summary": failure_reasons if failure_reasons else ["특정 오류 원인을 찾지 못했습니다."],
                "failed_tasks": failed_tasks,
                "mcp_status": mcp_status,
                "recommendation": recommendation,
                "lookback_minutes": lookback_minutes,
            }

        except Exception as e:
            logger.error(f"[031_STEP_3] analyze_system_failure_tool error: {e}")
            return {"error": f"진단 도구 실행 중 오류 발생: {str(e)}"}

    @staticmethod
    def get_weather_tool(zone_name=None, zone_id=None, **kwargs):
        """
        포장/구역의 기상 센서 데이터를 InfluxDB에서 조회합니다.
        GeoShape.unique_id → Input(map_overlay_id) → DeviceMeasurements(device_id+channel) → InfluxDB
        외부 API를 직접 호출하지 않습니다. 데이터는 Input 데몬이 수집하여 InfluxDB에 저장합니다.
        @ANCHOR: WEATHER_TOOL_ENTRY
        """
        import json as _json

        try:
            # Step 1: Find GeoShape by zone_name or zone_id
            target_shape = None
            if zone_id:
                target_shape = GeoShape.query.filter_by(unique_id=zone_id).first()
            if not target_shape and zone_name:
                _zn = zone_name.strip().lower()
                for shape in GeoShape.query.all():
                    try:
                        feat = shape.feature if isinstance(shape.feature, dict) else _json.loads(shape.feature or '{}')
                        props = feat.get('properties') or {}
                        _name = str(props.get('name') or props.get('label') or props.get('title') or '').lower()
                        if _zn in _name or _name in _zn:
                            target_shape = shape
                            break
                    except Exception:
                        continue

            # Step 2: Resolve display name; return error if zone not found
            _resolved_name = zone_name or zone_id or "알 수 없는 구역"
            if target_shape:
                try:
                    _f = target_shape.feature if isinstance(target_shape.feature, dict) else _json.loads(target_shape.feature or '{}')
                    _resolved_name = (_f.get('properties') or {}).get('name', _resolved_name)
                except Exception:
                    pass
            else:
                _available = []
                for s in GeoShape.query.limit(20).all():
                    try:
                        f = s.feature if isinstance(s.feature, dict) else _json.loads(s.feature or '{}')
                        _n = (f.get('properties') or {}).get('name', s.unique_id)
                        _available.append(_n)
                    except Exception:
                        pass
                return {
                    "error": "zone_not_found",
                    "message": f"구역 '{zone_name or zone_id}'을 찾을 수 없습니다.",
                    "available_zones": _available[:10]
                }

            # Step 3: Delegate to get_sensor_detail via zone unique_id.
            # get_sensor_detail resolves: GeoShape.unique_id → Input(map_overlay_id)
            #   → DeviceMeasurements(device_id + channel) → InfluxDB read.
            # No external HTTP calls are made here.
            logger.info(f"[WEATHER_TOOL] Querying InfluxDB for zone '{_resolved_name}' (id={target_shape.unique_id})")
            _result = AoTDataToolService.get_sensor_detail(loc_id=target_shape.unique_id, time_range='1h')

            # Step 4: Attach zone context and return
            if isinstance(_result, list):
                return {"zone_name": _resolved_name, "data": _result}
            if isinstance(_result, dict):
                _result['zone_name'] = _resolved_name
                return _result
            return {"zone_name": _resolved_name, "data": _result}

        except Exception as e:
            logger.exception("[WEATHER_TOOL] Unexpected error")
            return {"error": "unexpected_error", "message": f"기상 데이터 조회 중 오류: {str(e)}"}

    # -------------------------------------------------------------------------
    # @ANCHOR: FUNCTION_MANAGEMENT_TOOLS
    # Function management tools — read/activate/deactivate Conditional, Trigger,
    # PID, and CustomController (Function_Custom) entities.
    # Models with is_activated: Conditional, Trigger, PID, CustomController.
    # Function (base container) has no is_activated field — excluded from
    # activate/deactivate operations.
    # -------------------------------------------------------------------------

    @staticmethod
    def get_function_list(function_type=None, active_only=False):
        """
        Returns all registered Function-type controllers with their name, type,
        activation state, and period.

        :param function_type: Filter by type string — one of 'conditional',
                              'trigger', 'pid', 'custom'. Case-insensitive.
                              None returns all types.
        :param active_only:   If True, returns only is_activated=True entries.
        :returns:             {"results": [...], "count": int}
        """
        try:
            from aot.databases.models.function import Conditional, Trigger
            from aot.databases.models.controller import CustomController
            from aot.databases.models.pid import PID

            results = []

            # Normalize filter
            _type_filter = function_type.lower().strip() if function_type else None

            def _should_include(type_key):
                return _type_filter is None or _type_filter == type_key

            if _should_include('conditional'):
                rows = Conditional.query.all()
                for r in rows:
                    if active_only and not getattr(r, 'is_activated', False):
                        continue
                    results.append({
                        "function_id": r.unique_id,
                        "name": r.name,
                        "function_type": "conditional",
                        "is_activated": bool(getattr(r, 'is_activated', False)),
                        "period": getattr(r, 'period', None),
                    })

            if _should_include('trigger'):
                rows = Trigger.query.all()
                for r in rows:
                    if active_only and not getattr(r, 'is_activated', False):
                        continue
                    results.append({
                        "function_id": r.unique_id,
                        "name": r.name,
                        "function_type": "trigger",
                        "is_activated": bool(getattr(r, 'is_activated', False)),
                        "period": getattr(r, 'period', None),
                    })

            if _should_include('pid'):
                rows = PID.query.all()
                for r in rows:
                    if active_only and not getattr(r, 'is_activated', False):
                        continue
                    results.append({
                        "function_id": r.unique_id,
                        "name": r.name,
                        "function_type": "pid",
                        "is_activated": bool(getattr(r, 'is_activated', False)),
                        "period": getattr(r, 'period', None),
                    })

            if _should_include('custom'):
                rows = CustomController.query.all()
                for r in rows:
                    if active_only and not getattr(r, 'is_activated', False):
                        continue
                    results.append({
                        "function_id": r.unique_id,
                        "name": r.name,
                        "function_type": "custom",
                        "device": getattr(r, 'device', None),
                        "is_activated": bool(getattr(r, 'is_activated', False)),
                        "period": getattr(r, 'period', None),
                    })

            return {"results": results, "count": len(results)}
        except Exception as e:
            logger.exception("Error in get_function_list")
            return {"error": f"Function 목록 조회 중 오류 발생: {str(e)}"}

    @staticmethod
    def get_function_detail(function_id):
        """
        Returns detailed configuration for a specific Function-type controller.
        Searches Conditional, Trigger, PID, and CustomController by unique_id
        or name (exact match).

        :param function_id: unique_id (UUID string) or exact name of the function.
        :returns:           dict with full field set for the matched entity.
        """
        try:
            from aot.databases.models.function import Conditional, Trigger
            from aot.databases.models.controller import CustomController
            from aot.databases.models.pid import PID

            if not function_id:
                return {"error": "function_id가 필요합니다."}

            # Search order: Conditional → Trigger → PID → CustomController
            cond = Conditional.query.filter(
                (Conditional.unique_id == function_id) | (Conditional.name == function_id)
            ).first()
            if cond:
                return {
                    "function_id": cond.unique_id,
                    "name": cond.name,
                    "function_type": "conditional",
                    "is_activated": bool(getattr(cond, 'is_activated', False)),
                    "period": getattr(cond, 'period', None),
                    "start_offset": getattr(cond, 'start_offset', None),
                    "use_pylint": getattr(cond, 'use_pylint', None),
                    "log_level_debug": getattr(cond, 'log_level_debug', None),
                    "tab_id": getattr(cond, 'tab_id', None),
                }

            trig = Trigger.query.filter(
                (Trigger.unique_id == function_id) | (Trigger.name == function_id)
            ).first()
            if trig:
                return {
                    "function_id": trig.unique_id,
                    "name": trig.name,
                    "function_type": "trigger",
                    "trigger_type": getattr(trig, 'trigger_type', None),
                    "is_activated": bool(getattr(trig, 'is_activated', False)),
                    "period": getattr(trig, 'period', None),
                    "timer_start_time": getattr(trig, 'timer_start_time', None),
                    "timer_end_time": getattr(trig, 'timer_end_time', None),
                    "log_level_debug": getattr(trig, 'log_level_debug', None),
                    "tab_id": getattr(trig, 'tab_id', None),
                }

            pid = PID.query.filter(
                (PID.unique_id == function_id) | (PID.name == function_id)
            ).first()
            if pid:
                return {
                    "function_id": pid.unique_id,
                    "name": pid.name,
                    "function_type": "pid",
                    "is_activated": bool(getattr(pid, 'is_activated', False)),
                    "period": getattr(pid, 'period', None),
                    "setpoint": getattr(pid, 'setpoint', None),
                    "log_level_debug": getattr(pid, 'log_level_debug', None),
                    "tab_id": getattr(pid, 'tab_id', None),
                }

            ctrl = CustomController.query.filter(
                (CustomController.unique_id == function_id) | (CustomController.name == function_id)
            ).first()
            if ctrl:
                return {
                    "function_id": ctrl.unique_id,
                    "name": ctrl.name,
                    "function_type": "custom",
                    "device": getattr(ctrl, 'device', None),
                    "is_activated": bool(getattr(ctrl, 'is_activated', False)),
                    "period": getattr(ctrl, 'period', None),
                    "log_level_debug": getattr(ctrl, 'log_level_debug', None),
                    "tab_id": getattr(ctrl, 'tab_id', None),
                }

            return {"error": f"Function을 찾을 수 없습니다: {function_id}"}
        except Exception as e:
            logger.exception("Error in get_function_detail")
            return {"error": f"Function 상세 조회 중 오류 발생: {str(e)}"}

    @staticmethod
    def get_function_doc(function_type):
        """
        @ANCHOR: GET_FUNCTION_DOC_TOOL
        Returns structured documentation for a function type from docs/ai_docs/functions.json.
        Used by the AI to answer advice/guidance queries about PID, Conditional, VPD, etc.

        :param function_type: e.g. 'pid', 'conditional', 'vpd', 'trigger', 'bangbang'
        :returns: Full doc entry dict including params, use_cases, constraints, examples.
        """
        try:
            from aot.ai.services.ai_doc_service import AiDocService
            if not function_type:
                return {"error": "function_type 파라미터가 필요합니다. 예: 'pid', 'conditional', 'vpd'"}

            # Normalize: try exact key first, then case-insensitive search
            _key = function_type.strip().upper()
            doc = AiDocService.get_function_doc(_key)
            if doc is None:
                # Fallback: keyword search
                results = AiDocService.search(function_type, doc_type='functions')
                if results:
                    return {
                        "function_type": function_type,
                        "note": f"Exact key '{_key}' not found. Best match returned.",
                        "doc": results[0]
                    }
                return {"error": f"'{function_type}'에 대한 문서를 찾을 수 없습니다."}

            return {
                "function_type": _key,
                "doc": doc.raw
            }
        except Exception as e:
            logger.exception("Error in get_function_doc")
            return {"error": f"문서 조회 중 오류 발생: {str(e)}"}

    @staticmethod
    def get_input_doc(query):
        """
        @ANCHOR: GET_INPUT_DOC_TOOL
        Returns catalog info for input (sensor) device types from docs/ai_docs/inputs.json.
        Searches by device type key or keyword (e.g. 'DHT22', 'temperature', 'BME280').

        :param query: Device type key or keyword string.
        :returns: Matching entries with input_name, measurements_name, interfaces, dependencies.
        """
        try:
            from aot.ai.services.ai_doc_service import AiDocService
            if not query:
                return {"error": "query 파라미터가 필요합니다. 예: 'DHT22', 'temperature', 'BME280'"}

            # Try exact key first (case-insensitive)
            doc = AiDocService.get_input_doc(query.strip().upper())
            if doc:
                return {"query": query, "results": [doc.raw], "count": 1}

            # Fallback: keyword search across catalogue
            results = AiDocService.search(query, doc_type='inputs')
            if results:
                return {"query": query, "results": results[:5], "count": len(results)}

            return {"query": query, "results": [], "count": 0,
                    "note": f"'{query}'에 대한 입력 장치 문서를 찾을 수 없습니다. "
                            "Supported-Inputs.md 매뉴얼에 더 상세한 정보가 있습니다."}
        except Exception as e:
            logger.exception("Error in get_input_doc")
            return {"error": f"입력 장치 문서 조회 중 오류 발생: {str(e)}"}

    @staticmethod
    def get_output_doc(query):
        """
        @ANCHOR: GET_OUTPUT_DOC_TOOL
        Returns catalog info for output device types from docs/ai_docs/outputs.json.
        Searches by output type key or keyword (e.g. 'pwm', 'relay', 'peristaltic_pump').

        :param query: Device type key or keyword string.
        :returns: Matching entries with output_name, interfaces, dependencies.
        """
        try:
            from aot.ai.services.ai_doc_service import AiDocService
            if not query:
                return {"error": "query 파라미터가 필요합니다. 예: 'pwm', 'relay', 'stepper'"}

            # Try exact key first (case-insensitive)
            doc = AiDocService.get_output_doc(query.strip().lower())
            if doc:
                return {"query": query, "results": [doc.raw], "count": 1}

            # Fallback: keyword search across catalogue
            results = AiDocService.search(query, doc_type='outputs')
            if results:
                return {"query": query, "results": results[:5], "count": len(results)}

            return {"query": query, "results": [], "count": 0,
                    "note": f"'{query}'에 대한 출력 장치 문서를 찾을 수 없습니다. "
                            "Supported-Outputs.md 매뉴얼에 더 상세한 정보가 있습니다."}
        except Exception as e:
            logger.exception("Error in get_output_doc")
            return {"error": f"출력 장치 문서 조회 중 오류 발생: {str(e)}"}

    @staticmethod
    def activate_function_tool(function_id):
        """
        Activates a Function-type controller (Conditional, Trigger, PID, or
        CustomController). Updates is_activated=True in DB and signals the daemon.

        NOTE: This tool is in APPROVAL_REQUIRED_TOOLS — the planning service
        will intercept it and request human confirmation before execution.

        :param function_id: unique_id (UUID) or exact name of the function.
        :returns:           {"status": "success", ...} or {"error": "..."}
        """
        return AoTDataToolService._set_function_activation(function_id, activate=True)

    @staticmethod
    def deactivate_function_tool(function_id):
        """
        Deactivates a Function-type controller (Conditional, Trigger, PID, or
        CustomController). Updates is_activated=False in DB and signals the daemon.

        NOTE: This tool is in APPROVAL_REQUIRED_TOOLS — the planning service
        will intercept it and request human confirmation before execution.

        :param function_id: unique_id (UUID) or exact name of the function.
        :returns:           {"status": "success", ...} or {"error": "..."}
        """
        return AoTDataToolService._set_function_activation(function_id, activate=False)

    @staticmethod
    def _set_function_activation(function_id, activate):
        """
        Internal helper shared by activate_function_tool and deactivate_function_tool.
        Resolves function type, updates DB, and calls DaemonControl.
        """
        try:
            from aot.databases.models.function import Conditional, Trigger
            from aot.databases.models.controller import CustomController
            from aot.databases.models.pid import PID
            from aot.aot_flask.extensions import db as _db
            from aot.aot_client import DaemonControl

            if not function_id:
                return {"error": "function_id가 필요합니다."}

            # Resolve entity and controller_type label used by DaemonControl
            mod = None
            controller_type = None

            cond = Conditional.query.filter(
                (Conditional.unique_id == function_id) | (Conditional.name == function_id)
            ).first()
            if cond:
                mod = cond
                controller_type = 'Conditional'

            if mod is None:
                trig = Trigger.query.filter(
                    (Trigger.unique_id == function_id) | (Trigger.name == function_id)
                ).first()
                if trig:
                    mod = trig
                    controller_type = 'Trigger'

            if mod is None:
                pid = PID.query.filter(
                    (PID.unique_id == function_id) | (PID.name == function_id)
                ).first()
                if pid:
                    mod = pid
                    controller_type = 'PID'

            if mod is None:
                ctrl = CustomController.query.filter(
                    (CustomController.unique_id == function_id) | (CustomController.name == function_id)
                ).first()
                if ctrl:
                    mod = ctrl
                    controller_type = 'Function'  # DaemonControl uses 'Function' for CustomController

            if mod is None:
                return {"error": f"Function을 찾을 수 없습니다: {function_id}"}

            # Update DB
            mod.is_activated = activate
            _db.session.commit()

            # Signal daemon
            action_label = 'activate' if activate else 'deactivate'
            try:
                daemon = DaemonControl()
                if activate:
                    ret_err, ret_msg = daemon.controller_activate(mod.unique_id)
                else:
                    ret_err, ret_msg = daemon.controller_deactivate(mod.unique_id)

                if ret_err:
                    logger.warning(
                        f"[_set_function_activation] Daemon warning for {mod.unique_id}: {ret_msg}"
                    )
                    return {
                        "status": "success_with_warning",
                        "function_id": mod.unique_id,
                        "name": mod.name,
                        "function_type": controller_type,
                        "is_activated": activate,
                        "daemon_warning": ret_msg,
                        "message": f"DB 업데이트 완료. 데몬 응답: {ret_msg}",
                    }
            except Exception as daemon_err:
                # Daemon may be offline — DB update succeeded, log warning
                logger.warning(
                    f"[_set_function_activation] Daemon call failed for {mod.unique_id}: {daemon_err}"
                )
                return {
                    "status": "success_with_warning",
                    "function_id": mod.unique_id,
                    "name": mod.name,
                    "function_type": controller_type,
                    "is_activated": activate,
                    "daemon_warning": str(daemon_err),
                    "message": "DB 업데이트 완료. 데몬이 오프라인 상태일 수 있습니다.",
                }

            logger.info(
                f"[_set_function_activation] {action_label} OK: "
                f"{controller_type}/{mod.unique_id} ({mod.name})"
            )
            return {
                "status": "success",
                "function_id": mod.unique_id,
                "name": mod.name,
                "function_type": controller_type,
                "is_activated": activate,
                "message": f"'{mod.name}' {'활성화' if activate else '비활성화'} 완료",
            }
        except Exception as e:
            logger.exception("Error in _set_function_activation")
            return {"error": f"Function {'활성화' if activate else '비활성화'} 중 오류 발생: {str(e)}"}

    @staticmethod
    def get_active_functions_summary(**kwargs):
        """
        Returns a summary of all currently active Function-type controllers.
        Designed for AI context injection — provides a compact view of what
        automation is currently running.

        :returns: {"active_functions": [...], "count": int}
        """
        try:
            from aot.databases.models.function import Conditional, Trigger
            from aot.databases.models.controller import CustomController
            from aot.databases.models.pid import PID

            active = []

            for r in Conditional.query.filter_by(is_activated=True).all():
                active.append({
                    "function_id": r.unique_id,
                    "name": r.name,
                    "function_type": "conditional",
                    "is_activated": True,
                    "period": getattr(r, 'period', None),
                })

            for r in Trigger.query.filter_by(is_activated=True).all():
                active.append({
                    "function_id": r.unique_id,
                    "name": r.name,
                    "function_type": "trigger",
                    "trigger_type": getattr(r, 'trigger_type', None),
                    "is_activated": True,
                    "period": getattr(r, 'period', None),
                })

            for r in PID.query.filter_by(is_activated=True).all():
                active.append({
                    "function_id": r.unique_id,
                    "name": r.name,
                    "function_type": "pid",
                    "is_activated": True,
                    "period": getattr(r, 'period', None),
                })

            for r in CustomController.query.filter_by(is_activated=True).all():
                active.append({
                    "function_id": r.unique_id,
                    "name": r.name,
                    "function_type": "custom",
                    "device": getattr(r, 'device', None),
                    "is_activated": True,
                    "period": getattr(r, 'period', None),
                })

            return {"active_functions": active, "count": len(active)}
        except Exception as e:
            logger.exception("Error in get_active_functions_summary")
            return {"error": f"활성 Function 요약 조회 중 오류 발생: {str(e)}"}

    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_range(range_str):
        if not range_str: return 86400
        range_str = str(range_str).lower()
        if range_str.endswith('h'):
            return int(range_str[:-1]) * 3600
        if range_str.endswith('d'):
            return int(range_str[:-1]) * 86400
        if range_str.isnumeric():
            return int(range_str)
        return 86400

    # -------------------------------------------------------------------------
    # @ANCHOR: FUNCTION_CREATE_TOOLS
    # Function creation and configuration tools.
    # create_function: create a new function by type with optional initial params.
    # modify_function_options: update custom_options of an existing function.
    # get_device_measurements: list measurement channels of an Input or Function.
    # -------------------------------------------------------------------------

    @staticmethod
    def get_device_measurements(device_id):
        """
        Returns all measurement channels for a given Input or CustomController device_id.
        Also accepts a search_devices result dict — extracts the first device_id automatically.
        Used by the AI to resolve measurement IDs needed for select_measurement options.
        """
        try:
            # Accept search_devices result dict (e.g. {"results": [{"id": "..."}], "count": 1})
            if isinstance(device_id, dict):
                results = device_id.get('results') or device_id.get('result', {}).get('results', [])
                if results and isinstance(results, list):
                    device_id = results[0].get('id') or results[0].get('unique_id') or results[0].get('device_id')
            if not device_id or not isinstance(device_id, str):
                return {"error": "device_id is required (string UUID)"}

            rows = DeviceMeasurements.query.filter_by(device_id=device_id).all()
            if not rows:
                return {"error": f"No measurements found for device_id: {device_id}"}

            measurements = [
                {
                    "measurement_id": r.unique_id,
                    "channel": r.channel,
                    "measurement": r.measurement,
                    "unit": r.unit,
                    "name": getattr(r, 'name', ''),
                    # Ready-to-use value for select_measurement fields: "device_id,measurement_id"
                    "select_value": f"{device_id},{r.unique_id}",
                }
                for r in rows
            ]

            # Convenience map: measurement_type → select_value  (e.g. "temperature" → "uuid,uuid")
            # Makes it easy for the AI to pick the right channel by type name.
            select_by_type = {
                m["measurement"]: m["select_value"]
                for m in measurements
            }

            return {
                "device_id": device_id,
                "measurements": measurements,
                "select_by_type": select_by_type,
            }
        except Exception as e:
            return {"error": str(e)}

    @staticmethod
    def create_function_tool(function_type, name=None, params=None):
        """
        Creates a new function of the given type.
        function_type: e.g. 'AoT_VPD', 'conditional_conditional', 'pid_pid',
                       'trigger_timer_duration', etc.
        name: optional display name (falls back to function module default)
        params: dict of custom_options values to override after creation.
                For select_measurement fields, use 'device_id,measurement_id' format.
        Returns: {"function_id": "...", "name": "...", "function_type": "..."}
        """
        import json as _json
        from aot.aot_flask.utils.utils_function import function_add

        if not function_type:
            return {"error": "function_type is required"}

        # Minimal form shim — function_add only reads .function_type.data
        class _FakeForm:
            class _Field:
                def __init__(self, data): self.data = data
            def __init__(self, ft): self.function_type = self._Field(ft)

        try:
            messages, dep_name, unmet_deps, dep_msg, new_function_id = function_add(_FakeForm(function_type))
        except Exception as e:
            logger.error(f"[create_function] function_add raised: {e}")
            return {"error": str(e)}

        if messages.get("error"):
            return {"error": "; ".join(messages["error"]), "unmet_deps": unmet_deps}

        if not new_function_id:
            return {"error": "Function created but unique_id not returned"}

        # Look up the newly created record by unique_id
        from aot.databases.models.controller import CustomController
        from aot.databases.models.function import Conditional, Trigger
        from aot.databases.models.pid import PID

        new_func = None
        for Model in [CustomController, Conditional, PID, Trigger]:
            try:
                row = Model.query.filter_by(unique_id=new_function_id).first()
                if row:
                    new_func = row
                    break
            except Exception:
                continue

        # Apply display name if provided
        if new_func and name:
            new_func.name = name
            db.session.commit()

        # Apply custom params if provided
        logger.info(f"[create_function] new_func={new_func}, params={params}")
        if new_func and params and isinstance(params, dict):
            existing = {}
            try:
                existing = _json.loads(getattr(new_func, 'custom_options', None) or '{}')
            except Exception:
                existing = {}
            logger.info(f"[create_function] existing before update: {existing}")
            existing.update(params)
            logger.info(f"[create_function] existing after update: {existing}")
            new_func.custom_options = _json.dumps(existing)
            db.session.commit()
            logger.info(f"[create_function] custom_options committed: {new_func.custom_options[:200]}")

        function_id = new_function_id

        # Activate in daemon
        try:
            from aot.aot_client import DaemonControl
            daemon = DaemonControl()
            daemon.controller_activate(function_id)
        except Exception as e:
            logger.warning(f"[create_function] daemon activate failed (non-fatal): {e}")

        return {
            "function_id": function_id,
            "name": getattr(new_func, 'name', ''),
            "function_type": function_type,
            "status": "created",
        }

    @staticmethod
    def modify_function_options(function_id, params):
        """
        Updates custom_options fields of an existing function.
        params: dict — keys are custom_option IDs, values are the new settings.
                For select_measurement fields: 'device_id,measurement_id' string.
        Also triggers daemon reload so the change takes effect immediately.
        """
        import json as _json
        if not function_id or not params:
            return {"error": "function_id and params are required"}

        from aot.databases.models.controller import CustomController
        from aot.databases.models.function import Conditional, Trigger
        from aot.databases.models.pid import PID

        func = None
        for Model in [CustomController, Conditional, PID, Trigger]:
            try:
                row = Model.query.filter_by(unique_id=function_id).first()
                if row:
                    func = row
                    break
            except Exception:
                continue

        if func is None:
            return {"error": f"Function not found: {function_id}"}

        existing = {}
        try:
            existing = _json.loads(getattr(func, 'custom_options', None) or '{}')
        except Exception:
            existing = {}

        existing.update(params)
        func.custom_options = _json.dumps(existing)
        db.session.commit()

        # Reload in daemon so changes take effect without manual restart
        try:
            from aot.aot_client import DaemonControl
            daemon = DaemonControl()
            daemon.controller_deactivate(function_id)
            daemon.controller_activate(function_id)
        except Exception as e:
            logger.warning(f"[modify_function_options] daemon reload failed (non-fatal): {e}")

        return {"status": "updated", "function_id": function_id, "updated_keys": list(params.keys())}
