# AoT_AI — 변경 이력

AoT_AI는 오픈소스 환경 제어 시스템 **AoT(Automated of Things)** 를 기반으로,  
**AI 오케스트레이션**과 **벡터 기반 GIS** 를 통합한 스마트팜 특화 플랫폼입니다.

---

## 주요 특징 (Platform Overview)

### AI 오케스트레이션
사용자가 직접 AI API 키를 등록해 **조언형(Advisory)** 또는 **챗봇형(Chat)** AI를 구성할 수 있습니다.

- **다중 AI 제공자 지원**: Anthropic(Claude), Google(Gemini), OpenAI, Mistral, Groq, Ollama(로컬 LLM), MiniMax
- **파이프라인 역할 분리**: Router → Planner → Executor → Synthesizer → Worker 계층 구조
- **Tier 기반 분류기**: Tier0 사전분류(0-토큰) → Tier1 라우팅 → Tier2 실행으로 응답 속도 최적화
- **MCP(Model Context Protocol) 서버**: AI가 시설 상태 조회(Observe), 이상 분석(Diagnose), 설정 변경(Control)을 도구 호출로 수행
- **사용자 승인 게이트**: 쓰기 도구(설정 변경)는 60초 내 사용자 승인 필요, 감사 로그 90일 보존

### AI 지식 레이어
AI 학습에 필요한 지식을 사용자가 직접 구성할 수 있는 레이어 시스템입니다.

- **AIContextSource**: REST API / 문서 / 웹 URL / 내부 쿼리 등 외부 지식 소스 등록 및 주기적 동기화
- **AIDomainGlossary**: 스마트팜 도메인 용어사전 (pending/active 상태 관리)
- **AIFacilityLearning**: 시설별 패턴 학습 및 모델 버전 관리
- **AIUserProfile**: 사용자별 선호 에이전트 및 피드백 설정
- **AISummary / AIRecommendation**: 일간 환경 요약 및 AI 권장사항 기록

### 벡터 기반 GIS
타일 기반이 아닌 벡터 렌더링으로 부드럽고 자연스러운 지도를 제공합니다.

- **GeoMap**: OSM / 위성 등 다양한 맵 프로바이더, 도형 그리기, 장치 배치
- **GeoFacility + 3D Widget**: 시설(온실/하우스) 외형을 폴리곤으로 정의하고 3D로 시각화
- **자동 액추에이터 제어**: 환기창(vent), 커튼(curtain), 측창(side window), 도어, 조명 등 시설 구성 요소를 GIS 폴리곤에 연결해 자동 제어
- **풍향 차등 제어**: 강풍 시 windward(풍상) 개구부만 강제 폐쇄, leeward(풍하) 환기 유지
- **GeoShape 기반 효과 산출**: 개구부 면적·방위각을 폴리곤에서 자동 계산해 제어 효과에 반영
- **시설 센서 바인딩**: 실내/외 온도·습도·CO₂·풍향 센서를 시설에 역할별로 연결

### 통합 환경 제어 (Layer 3 Coordinator)
PI 제어 기반의 다중 액추에이터 조율 시스템입니다.

- **ActuatorProfile**: GIS 폴리곤에서 azimuth·면적을 자동 산출해 프로필 구성
- **SafetyPreGate**: 강풍·강우·폭염·혹한 안전 관문 (하드 제약, 롤백 보장)
- **예측 피드포워드**: 외부 기상 예보 기반 선행 제어
- **광합성 모델**: Big-Leaf 모델(A_max, K_L, T_opt, VPD_half)로 작물 맞춤 목표값 산출
- **누적 추적**: DLI(일적산광량), GDD(적산온도), VPD, CO₂ 일별 누적 관리
- **보정 시스템**: 센서·액추에이터 오차 캘리브레이션

---

# v26.05.0 (2026-05-18)

## 기능 추가 (Features)

### AI 시스템
- **MCP 서버 추가** (`aot/mcp_server/`): FastMCP 기반, stdio/HTTP SSE 모드 지원
  - `Observe` 도구: 시설 상태·센서 이력·액추에이터 명령값 조회
  - `Diagnose` 도구: 센서 이상 탐지·환경 제어 성능 분석
  - `Control` 도구: VPD 목표값·메서드 제어점 변경, 수동 잠금 (사용자 승인 필요)
- **MCPAuditLog / MCPConfirmation 모델 추가**: 도구 호출 이력 및 승인 큐
- **AIAgent `allowed_tools` 필드 추가**: 에이전트별 MCP 도구 접근 범위 제한

### 벡터 GIS
- **GeoFacility fittings**: 창호·도어·커튼 등 시설 구성 요소 등록 및 GeoShape 연결 (`p5_6`)
- **시설 센서 바인딩** (`facility_sensors.py`): 실내외 센서를 역할별로 시설에 연결, 가중 평균 산출
- **시설 풍향 분석** (`facility_wind.py`): 외부 풍향 데이터 처리 및 개구부 방위각 비교
- **GeoFacility timezone 필드 추가** (`p5_1`)
- **B2-fix**: `get_facility_integration` 페이로드 개선 — fitting-only 등록 누락 해소, GeoShape N+1 쿼리 → bulk fetch, vent 면적 이중 회계 차단

### 환경 제어
- **Function cumulative state** (`p5_5`): DLI·GDD 일별 누적 및 보상 제어 (`FunctionCumulativeState`)
- **Function crop preset** (`p5_3`): 작물 광합성 파라미터 DB 저장 (`FunctionCropPreset`)
- **lighting 액추에이터**: `ACTUATOR_KINDS` 정식 등록, R2 경로(보광 등록 시 활성) 추가 (G5)
- **풍향 차등 SafetyPreGate** (G4): windward 60° arc 내 개구부만 강제 폐쇄, leeward 환기 유지
- **EffectFn 면적·단열 가중** (G3): 개구부 면적·u_effective를 반영한 효과 산출 (기존 `profile=None` 호환)
- **GIS 기반 profile builder** (G2): GeoShape per-device 우선 조회, fallback 균등 분할 유지
- **env_control 모듈 추가**: `authority`, `calibration`, `cumulative_tracker`, `forecast_feedforward`, `photosynthesis`, `group_expander`, `ext_context_fallback`

### 기타
- **MCP Audit 테이블** (`p4_3`): `MCPAuditLog`, `MCPConfirmation`
- **Function runtime state** (`p2_5`): 함수 실행 상태 영속화
- **Method points JSON** (`p3_5`): 제어 곡선 제어점 JSON 저장
- **output_actuator_paired**: 양방향 액추에이터 액션 추가 (`aot/actions/`)
- **작물 프리셋 데이터**: 상추·파프리카·고추·딸기·토마토 VPD 프리셋 (`aot/data/method_presets/`)

## 버그 수정 (Bug Fixes)

- **actuator_paired**: safe-stop 3개 지점(stop_output / _watchdog_fire / calib_stop) 진행 방향만 OFF, `_running_relay_id` 헬퍼 추가, `reverse_pause` 수학 수정, stop-in-place 처리
- **base_output**: OFF write 시 `measurement_channel` lookup fallback (template-only 안전 처리)
- **on_off_mqtt_farmon_v1**: `status_client` 누수 정리, orphan client 콜백 차단, `cache=None` 시 OFF publish 차단, `device_measurements` 동기화
- **on_off_mqtt_multi**: `execute_at_modification` → `device_measurements` 동기화

## DB 마이그레이션
- `p2_5` → `p3_5` → `p4_3` → `p4_4`(merge) → `p5_1` → `p5_5` → `p5_3` → `p5_6` ← **현재 HEAD**
- `ALEMBIC_VERSION`: `d0e1f2a3b4c5` → `p5_6_geo_facility_fittings`

---

# v26.02.1 (2026-02-14)

## 기능 (Features)

### 벡터 GIS 시스템
- **Geo Design**: OSM·위성 등 다양한 맵 유형, 도형 그리기(폴리곤·선·점), 장치 배치
- **Geo Input**: 지도 위 입력 장치 배치 및 측정값 오버레이
- **Geo Setting**: 장치 마커 컬링 줌 레벨, 맵 잠금 등 전역 설정
- **GeoFacility**: 시설 외형 폴리곤 정의 및 3D Facility Widget 연동
- **AoT_map Widget**:
  - 지도 위 입력·출력·함수 제어 및 상태 표시
  - 장치 도형 투명도(0–100%) 설정
  - 맵 잠금 상태 세션 간 유지
  - 토글 스위치 UI, 알약 스타일 마커

### 노트 시스템
- **장치 노트**: 입력·출력·함수 장치별 노트 작성
- **지도 노트**: 특정 좌표에 노트 배치
- **카드 페이지**: 노트 목록 관리
- **위젯 통합**: 지도 위젯과 노트 연동

## 미구현 / 예정 사항
- **관수 로직**: 유량은 GIS 도형 수량 기반 단순 산출 (코어 로직 미연동)
- **Geo Design 설비 상세화**: 펌프·밸브 등 하위 카테고리

---

# v26.02.1 (2026-02-14) — English

## Features

### Vector GIS System
- **Geo Design**: Multiple map types (OSM, satellite), shape drawing, device placement
- **Geo Input**: Input device integration on maps with measurement overlay
- **Geo Setting**: Global map settings (marker cull zoom, map lock)
- **GeoFacility**: Facility polygon definition with 3D Facility Widget integration
- **AoT_map Widget**: Real-time device control on map, shape opacity, map lock persistence, toggle switch UI, pill-style markers

### Note System
- **Device Notes**: Notes per Input / Output / Function device
- **Map Notes**: Coordinate-anchored notes on the map
- **Card Page**: Note list management
- **Widget Integration**: Notes linked to map widget

## Unimplemented / Upcoming
- **Irrigation Logic**: Flow rate currently based on GIS shape count (not linked to core logic)
- **Geo Design Facility Detail**: Sub-categories for pumps, valves, etc.
