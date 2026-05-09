# AI 오케스트레이션 아키텍처 분석

## 문서 정보
- 작성일: 2026-05-04
- 버전: 1.0
- 작업 디렉토리: `Build/5_docker`
- 소스 분석: unified_orchestrator.py, ai_router.py, ai_agent_service.py, ai_routing_service.py, brain_resolver.py, ai_philosophy_preamble.py, models/ai.py, routes_ai_agent.py

---

## 1. 개요

AoT AI 오케스트레이션 시스템은 **UnifiedOrchestrator (UOC) v5.1**을 중심으로 작동하는 5단계 라이프사이클 파이프라인이다. 시스템은 사용자 질의를 분류하고, 컨텍스트를 조립하며, 행동을 검증하고, 인간 승인을 거친 후 최종 실행으로 디스패치하는 구조를 따른다.

### 핵심 설계 원칙
- **조언형 AI**: 모든 사용자Facing 응답은 조언(Advisory) 언어를 사용
- **인간 승인**: 물리적 제어 행동은 P4 Human Gate를 통해 사용자 승인 필요
- **계층적 처리**: Tier0/Tier1/Tier2로 쿼리 복잡도에 따라 분류

---

## 2. 대화형 vs 조언형 구분

### 2.1 두 모드의 근본적 차이

| 구분 | 대화형 (CHAT) | 조언형 (CONTROL/DATA_QUERY/SCHEDULE/COMPOSITE) |
|------|--------------|----------------------------------------------|
| **Intent** | CHAT | CONTROL, DATA_QUERY, SCHEDULE, COMPOSITE |
| **Tier** | Tier0 (즉시 응답) 또는 Tier1 | Tier1 또는 Tier2 |
| **응답 특성** | 단순 인사, 신원 확인, 시간 조회 등 | 센서 데이터, 기기 제어, 일정 계획 등 |
| **행동 필요성** | X (읽기 전용) | O (데이터 조회 또는 행동 실행) |
| **P4 승인** | 불필요 | CONTROL/SCHEDULE/COMPOSITE는 필수 |
| ** PHILOSOPHY_PREAMBLE 적용** | chat 역할에만 적용 | worker, synthesizer 역할에 적용 |

### 2.2 PHILOSOPHY_PREAMBLE - 조언형 언어 규칙

`ai_philosophy_preamble.py`에 정의된 6가지 핵심 규칙:

```python
PHILOSOPHY_ROLES = {'synthesizer', 'worker', 'chat'}
```

1. **Advisory Language — Always**
   - CORRECT: "Based on current data, ventilation may be worth considering."
   - INCORRECT: "Activate ventilation immediately."
   - 명령Issuance 금지, 조언 형태 유지

2. **Express Confidence — Always**
   - 완전한 데이터: 명확한 발견 사항陈述
   - 불완전한 데이터: "This recommendation is based on general baselines — your facility-specific data has not yet been confirmed."

3. **Cite Your Sources — Always**
   - 응답에 영향을 미친 데이터/컨텍스트 명시
   - 시스템 생성 값 사용 시: "based on standard domain defaults, not yet confirmed"

4. **Acknowledge Learning State — When Relevant**
   - 초기 학습 단계 또는 시설 특정 데이터 부재 시 공개적으로 인정
   - 다음 권고를 개선하기 위해 필요한 정보 설명

5. **User Agency is Absolute**
   - 출력은 운영자를 위한 정보 제공, 운영자가 결정
   - 제안이라도 의무/명령/유일한 옵션으로프레이밍 금지

6. **Confidence Budget Calibration**
   - `confidence_budget` 파라미터 활용
   - `facility_learning_phase_active` true 시 hedge language 적용
   - LOW 신뢰도 도메인 명시적 인정

---

## 3. AI 에이전트 구조

### 3.1 AI 역할별 상세 비교

| 역할 | 코드 위치 | 주요 임무 | 프롬프트 유형 | 도구 접근 | PHILOSOPHY 적용 |
|------|----------|----------|-------------|----------|----------------|
| **AIRouterAI** | ai_router.py | 5가지 Intent 분류 | 미니멀리스트 Gatekeeper | 없음 | X |
| **Tier0Classifier** | ai_routing_service.py | 경량 사전 분류 | 규칙 기반 | 없음 | X |
| **Planner** | ai_agent_service.py | 복잡 명령 분해 | 전략적 Planning | 없음 | X |
| **Executor** | ai_agent_service.py | 도구 실행, 데이터 수집 | Precise Execution | All | X |
| **Synthesizer** | ai_agent_service.py | 결과 통합, 사실 검증 | Final Synthesis | 없음 | O |
| **Worker** | ai_agent_service.py | 범용 작업 수행 | Multimodal Analysis | All | O |

### 3.2 AIRouterAI (Intent Router)

```python
AI_INFORMATION = {
    "engine_type": "ai_router",
    "ai_name": "Intent Router",
    "specialty": "intent classification, routing, disambiguation",
    "system_prompt": (
        "Your MISSION is to classify user intent into one of: "
        "CONTROL, DATA_QUERY, SCHEDULE, COMPOSITE, CHAT."
    )
}
```

**5가지 Intent 분류:**
- **CONTROL**: 물리적 기기 명령 (밸브, 펌프 즉시 작동)
- **DATA_QUERY**: 센서 상태/이력, 날씨 정보 조회
- **SCHEDULE**: 미래 시점 작업 계획/예약
- **COMPOSITE**: 데이터 조회 + 기기 제어 혼합
- **CHAT**: 일반 지식 대화 (도구 불필요)

**분류 실패 시 Fallback:**
```python
# ai_router.py line 185-193
# v6: Fallback to DATA_QUERY instead of C_AMBIGUOUS (Force Tool Policy)
logger.warning(f"[AIRouter] Failed to parse classification for '{goal}'. 
                Returning DATA_QUERY (Force Tool Policy).")
return {
    "intent": "DATA_QUERY",
    "confidence": 0.0,
    "requires_tools": True,
    "insight": "의도를 분류하지 못했습니다.",
    "actions": []
}
```

### 3.3 Tier0Classifier (경량 분류기)

```python
class Tier0Classifier:
    """
    Zero-token pre-classifier for trivially resolvable queries.
    Guards against over-classification via dual-validation.
    """
```

**처리 유형:**
- 인사 (안녕, hello, hi, こんにちは)
- 현재 시간 조회
- 신원 확인 (who are you)
- 시스템 설명 (what is AoT)
- 언어 지원查询
- 순수 산술 계산

**분류 로직:**
```python
# ai_routing_service.py line 90-173
@classmethod
def classify(cls, command_text):
    user_query = cls.extract_user_query(command_text)
    clean = re.sub(r'[!?.~]', '', user_query.strip().lower()).strip()
    
    # Guard 1: Too long → TIER 1
    if len(clean) > cls._MAX_LEN:  # 30 chars
        return None
    
    # Guard 2: Data dependency keyword present → TIER 1
    if cls._has_data_dependency(clean):
        return None
    
    # Guard 3: Connector (compound request) → TIER 1
    if cls._has_connector(clean):
        return None
    
    # ... static response for greetings, time, identity, etc.
```

### 3.4 BrainResolver (엔진 인스턴스 해석)

```python
@dataclass
class EngineContext:
    provider: str
    model_name: str
    engine_instance: object  # AbstractAI instance
```

**Resolution 과정:**
```
AIEntry (서비스 연결) + AIAgent (페르소나/로직) + AIAgentSkeleton (스칼라)
                              ↓
                    BrainResolver.resolve()
                              ↓
                    EngineContext (엔진 인스턴스)
```

**핵심 단계:**
1. **Target Entry 해결**: preferred_entry_id 또는 최적 활성 엔트리 검색
2. **Skeleton 로드**: display_name, system_prompt, custom_options_json
3. **Behavior 스칼라**: temperature, max_tokens, model_tier
4. **Philosophy 주입**: law_8_philosophy_alignment에 따라 preamble 추가
5. **Confidence Budget 도출**: AIFacilityLearning에서 도메인별 신뢰도 계산
6. **엔진 인스턴스화**: ENGINE_REGISTRY에서 클래스 조회 후 인스턴스 생성

### 3.5 UnifiedOrchestrator (UOC) - 5단계 라이프사이클

```python
class LifecycleState(Enum):
    INITIAL = "INITIAL"
    ROUTED = "ROUTED"
    PLANNED = "PLANNED"
    VALIDATED = "VALIDATED"
    APPROVED = "APPROVED"
    DISPATCHED = "DISPATCHED"

class Tier(Enum):
    TIER0 = "Tier0"  # Cached simple response
    TIER1 = "Tier1"  # LLM processable
    TIER2 = "Tier2"  # Requires planner (complex)
```

---

## 4. 파이프라인 흐름

### 4.1 상태 다이어그램

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         UnifiedOrchestrator Lifecycle                        │
└─────────────────────────────────────────────────────────────────────────────┘

                                    ┌─────────────┐
                                    │   INITIAL   │
                                    └──────┬──────┘
                                           │ route()
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  GATE_1: AdvisoryLanguageValidator                                          │
│  - Advisory framing validation                                               │
│  - Violations → ValueError raised                                            │
└──────────────────────────────────────────────────────────────────────────────┘
                                           │
                                    ┌──────▼──────┐
                                    │   ROUTED    │
                                    │ Tier0/1/2   │
                                    └──────┬──────┘
                                           │ plan()
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  KBG Context Assembly (KnowledgeBaseGateway)                                │
│  - get_merged_context() → L3 Veto/Override algorithm                        │
│  - MergedContext with confidence_metadata                                    │
└──────────────────────────────────────────────────────────────────────────────┘
                                           │
                                    ┌──────▼──────┐
                                    │   PLANNED    │
                                    │ ActionChain  │
                                    └──────┬──────┘
                                           │ resolve_actions()
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  GATE_2: ActionNormalizer                                                   │
│  - Parameter validation                                                      │
│  - Executor type mapping (virtual/physical/MCP)                              │
│                                                                              │
│  GATE_4: SafetyVEEModule                                                    │
│  - Hardware bounds verification                                              │
│  - Operational limits confirmation                                            │
│  - Emergency stop detection                                                   │
│  - VEE Validation/Evaluation                                                 │
└──────────────────────────────────────────────────────────────────────────────┘
                                           │
                                    ┌──────▼──────┐
                                    │  VALIDATED   │
                                    │ Normalized[] │
                                    └──────┬──────┘
                                           │ await_approval()
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  GATE_3: P4ApprovalPanel                                                   │
│  - ActionSummary with confidence display                                     │
│  - User chooses: CONFIRM / MODIFY / DISMISS                                 │
│  - 300 seconds timeout                                                      │
└──────────────────────────────────────────────────────────────────────────────┘
                                           │
                                    ┌──────▼──────┐
                                    │  APPROVED    │
                                    │ UserDecision │
                                    └──────┬──────┘
                                           │ dispatch()
                                           ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│  DAEMON Dispatch (Pyro5 RPC)                                                │
│  - execute_action via DaemonControl                                          │
│  - Results/errors collection                                                 │
└──────────────────────────────────────────────────────────────────────────────┘
                                           │
                                    ┌──────▼──────┐
                                    │  DISPATCHED  │
                                    └─────────────┘
```

### 4.2 Tier 라우팅 상세

#### Tier0 - 캐시된 단순 응답
```
요청 → Tier0Classifier.classify() → 정적 응답 반환
                                 ↓ (분류 실패 시)
                              Tier1 처리
```

#### Tier1 - LLM 처리 가능
```
요청 → AIRouterAI.run_reasoning() → Intent 분류
                              ↓
                    AIAgentService 실행 (Worker/Executor)
                              ↓
                    Synthesizer 통합
```

#### Tier2 - 플래너 필요 (복잡한 작업)
```
요청 → Planner 분해 → Executor 순차 실행 → Synthesizer 통합
```

### 4.3 Intent별 승인 흐름

| Intent | P4 승인 필요 | 즉시 실행 허용 | 예시 |
|--------|-------------|--------------|------|
| **CHAT** | X | O (Tier0) | "안녕", "시간 알려줘" |
| **DATA_QUERY** | X | O (읽기 전용) | "현재 온도 알려줘" |
| **CONTROL** | O | X | "밸브2 켜줘" |
| **SCHEDULE** | O | X | "30분 뒤에 밸브2 켜줘" |
| **COMPOSITE** | O | X | "온도 높으면 팬 켜줘" |

---

## 5. 데이터 모델 의존성

### 5.1 핵심 모델 관계

```
┌─────────────────┐     1:N     ┌─────────────────┐
│    AIEntry      │◄────────────│    AIAgent      │
│ (서비스 연결)    │   entry_id  │ (페르소나/로직)  │
└─────────────────┘             └─────────────────┘
                                          │
                                          │ pipeline_role
                                          ▼
                              ┌─────────────────────────┐
                              │   AgentRolePreset       │
                              │ (DB 관리 롤 설정)        │
                              └─────────────────────────┘

┌─────────────────┐     1:1     ┌─────────────────┐
│   GeoFacility   │◄────────────│    GeoShape     │
│ (시설 데이터)     │  shape_uuid │ (도형 데이터)     │
└─────────────────┘             └─────────────────┘
         │
         │ facility_id (AIFacilityLearning 참조)
         ▼
┌─────────────────────────┐
│  AIFacilityLearning     │
│  (시설 학습 상태)          │
│  - learning_phase_active │
│  - confirmations_json    │
│  → Confidence Budget     │
└─────────────────────────┘

┌─────────────────┐
│   AIHistory     │ (이력 로그)
│ - agent_id      │
│ - goal/insight  │
│ - actions_json  │
│ - thread_id     │
│ - user_id       │
└─────────────────┘

┌─────────────────────┐     ┌─────────────────────┐
│   AIRoleConfig      │     │  AIActionRegistry   │
│ (런타임 롤 오버라이드) │     │ (액션 라우팅/자격)   │
└─────────────────────┘     └─────────────────────┘
```

### 5.2 AIAgent 주요 필드

```python
class AIAgent(CRUDMixin, db.Model):
    # Link to Service Provider (Brain)
    entry_id = db.Column(db.String(36), db.ForeignKey('ai_entry.unique_id'))
    
    # Persona & Behavior
    role = db.Column(db.String(20), default='worker')
    specialty = db.Column(db.String(100), default='general')
    system_prompt = db.Column(db.Text, default='You are a helpful assistant.')
    temperature = db.Column(db.Float, default=0.7)
    max_tokens = db.Column(db.Integer, default=2048)

    # v6 Pipeline Role & Configuration
    pipeline_role = db.Column(db.String(20), default='worker')  
    # router, planner, executor, synthesizer, worker
    model_tier = db.Column(db.String(20), default='standard')   
    # lightweight, standard, heavy
    tool_access = db.Column(db.String(20), default='auto')      
    # all, none, assigned, auto
    custom_options_json = db.Column(db.Text, default='{}')
```

---

## 6. 오류 및 미사용 로직

### 6.1 Dead Code / Shim 파일

| 파일 | 상태 | 설명 |
|------|------|------|
| `aot/ai/services/ai_routing_service.py` | Shim | `aot/ai/ai_routing_service.py`로 리다이렉트 |
| `aot/ai/ai_routing_service.py` | 활성 | 실제 구현 (Tier0Classifier 포함) |

```python
# aot/ai/services/ai_routing_service.py (line 1-4)
# SHIM: Backward-compatibility redirect. Module moved to aot.ai.ai_routing_service.
from aot.ai.ai_routing_service import *  # noqa: F401, F403
```

### 6.2 오류 처리 패턴

#### BrainResolver 실패 시
```python
# brain_resolver.py line 47-48
if not entry:
    logger.error(f"[BrainResolver] Could not resolve any AIEntry for skeleton {skeleton_id}")
    return None
```

#### 엔진 인스턴스화 실패 시
```python
# brain_resolver.py line 177-179
except Exception as e:
    logger.error(f"[BrainResolver] Failed to instantiate engine {target_type}: {e}")
    return None
```

#### AIRouter 분류 실패 시 (v6 Force Tool Policy)
```python
# ai_router.py line 185-193
# v6: Fallback to DATA_QUERY instead of C_AMBIGUOUS (Force Tool Policy)
return {
    "intent": "DATA_QUERY",
    "confidence": 0.0,
    "requires_tools": True,
    "insight": "의도를 분류하지 못했습니다.",
    "actions": []
}
```

#### Tier0Classifier 미분류 시
```python
# ai_routing_service.py line 173
return None  # → Tier1 LLM classification proceeds
```

### 6.3 즉시 실행 허용 액션 (Safe Actions)

```python
# ai_agent_service.py line 24
IMMEDIATE_ACTIONS = [
    'read_manual',           # 메뉴얼 읽기
    'get_detailed_manifest', # 상세 Manifest
    'mcp_tool_call',         # MCP 도구 호출
    'virtual_tool_call',     # 가상 도구 호출
    'mcp_resource_read',     # MCP 리소스 읽기
    'mcp_prompt_get'         # MCP 프롬프트 읽기
]
```

### 6.4 Rate Limiter 설정

```python
# ai_agent_service.py line 220
# v6.3: Raised to 30 — prompt caching reduces token load; paid tier confirmed.
_RATE_LIMITER = _TokenBucketRateLimiter(max_rpm=30)
```

---

## 7. 주요 데이터 흐름

### 7.1 UnifiedOrchestrator 5단계 실행 예시

```
사용자: "밸브2 켜줘"

Step 1: route()
├── GATE_1: AdvisoryLanguageValidator 통과
├── Tier 분류: TIER1 (CONTROL intent)
└── RoutingDecision(tier=TIER1, confidence=0.80)

Step 2: plan()
├── KBG.get_merged_context() 실행
├── L3 Veto/Override 알고리즘 적용
├── ActionChain 생성
│   └── Action(action_id='output_operate', parameters={'device_id': 'valve2'})
└── MergedContext with ConfidenceMetadata

Step 3: resolve_actions()
├── GATE_2: ActionNormalizer.normalize() → executor_type=VIRTUAL
├── GATE_4: SafetyVEEModule.validate_action()
│   └── hardware_bounds, operational_limits 확인
└── NormalizedAction 리스트 반환

Step 4: await_approval()
├── P4ApprovalPanel.register_draft()
├── UI에 승인 패널 표시
└── 사용자 선택: CONFIRM / MODIFY / DISMISS

Step 5: dispatch()
├── DaemonControl.proxy().execute_action()
├── Pyro5 RPC로 Daemon에 명령 전달
└── 결과/오류 수집 후 반환
```

### 7.2 Confidence Budget 흐름

```python
# brain_resolver.py Phase 3: Derive confidence_budget from facility learning state

AIFacilityLearning.confirmations_json
    ↓
{domain: {confirmed: N, total: M}}
    ↓
각 도메인별 비율 계산
    ↓
ratio >= 0.7 → HIGH
ratio >= 0.3 → MEDIUM
ratio < 0.3  → LOW
    ↓
custom_options_json에 confidence_budget 주입
    ↓
엔진 인스턴스가 hedge language 자동 적용
```

---

## 8. 요약 표

### 8.1 핵심 컴포넌트

| 컴포넌트 | 파일 | 클래스/함수 | 주요 기능 |
|---------|------|------------|---------|
| **UnifiedOrchestrator** | unified_orchestrator.py | UnifiedOrchestrator | 5단계 라이프사이클 코디네이터 |
| **Intent Router** | ai_router.py | AIRouterAI | 5가지 Intent 분류 |
| **Tier0 Classifier** | ai_routing_service.py | Tier0Classifier | 경량 사전 분류 |
| **Brain Resolver** | brain_resolver.py | BrainResolver | AIEntry → 엔진 인스턴스 변환 |
| **Philosophy Preamble** | ai_philosophy_preamble.py | get_preamble(), inject() | 조언형 언어 규칙 주입 |
| **Agent Service** | ai_agent_service.py | AIAgentService | 에이전트 라이프사이클 관리 |
| **Routing Service** | ai_routing_service.py | AIRoutingService | 의도 라우팅/액션 검증 |

### 8.2 GATE 요약

| GATE | 검증기 | 위치 | 목적 |
|------|-------|------|------|
| GATE_1 | AdvisoryLanguageValidator | unified_orchestrator.py | 조언형 언어 프레이밍 검증 |
| GATE_2 | ActionNormalizer | validation/action_normalizer.py | 액션 파라미터 검증 |
| GATE_3 | P4ApprovalPanel | ui/p4_approval_panel.py | 인간 승인 패널 |
| GATE_4 | SafetyVEEModule | validation/safety_vee_module.py | 안전/VEE 검증 |

---

## 9. 참고 파일 경로

| 파일 | 경로 |
|------|------|
| UnifiedOrchestrator | `aot/ai/orchestration/unified_orchestrator.py` |
| AIRouterAI | `aot/ai/agents/ai_router.py` |
| AIRoutingService | `aot/ai/ai_routing_service.py` |
| BrainResolver | `aot/ai/brain_resolver.py` |
| Philosophy Preamble | `aot/ai/ai_philosophy_preamble.py` |
| AIAgentService | `aot/ai/services/ai_agent_service.py` |
| AI Models | `aot/databases/models/ai.py` |
| Routes | `aot/aot_flask/routes_ai_agent.py` |
