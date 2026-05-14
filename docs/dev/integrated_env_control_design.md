# 시설 환경 통합 제어 시스템 설계

> **상태**: 설계 (v2)
> **작성일**: 2026-05-08 (v0)
> **개정일**: 2026-05-08 (v1 — 리뷰 보강), 2026-05-08 (v2 — Facility/GIS 통합 + R1/R2/R3 명문화)
> **선행 문서**: `opening_control_design.md` (개구부 단독 제어 — 본 문서로 대체 예정)
> **범위**: 시설 내 모든 환경 제어 액추에이터(개구부·냉난방·관수/포그·CO₂·차광/보온·보광)의 통합 조율
>
> **v2 핵심 변경**:
> - 목표 우선순위 명문화: **R1 (VPD primary) / R2 (Light secondary primary, optional) / R3 (T·RH constraint-only)**
> - Facility/GIS 통합: 장치별 `Output.lat/lon` + `GeoShape.feature` (polygon)에서 azimuth·area 자동 산출
> - 풍향 알고리즘 반영: `SafetyPreGate`가 개구부별 azimuth와 풍향을 비교해 **windward만 강제 폐쇄**
> - `ActuatorProfile` GIS 메타 필드(`geo_facility_id, slot_key, azimuth_deg, area_m2, capacity_meta`) 추가
> - `lighting` actuator kind 정식 포함 (보광 R2)

---

## 0. 설계 원칙

| ID | 원칙 |
|----|------|
| **P1** | 단위 센서값에 반응하지 않는다. **상위 목표(작물·생육·광합성)** 에서 환경 목표가 도출된다. |
| **P2** | 액추에이터는 "지금 이 상황에서의 효과 방향"으로 평가된다. 정적 메타데이터로 가정하지 않는다. |
| **P3** | 명령은 **한 곳에서 한 사이클에 동시에** 결정된다. 액추에이터 간 PID 독립 운영 금지. |
| **P4** | 각 계층은 **명확한 입출력 계약**을 가진다. 한 계층을 단독 교체·테스트할 수 있어야 한다. |
| **P5** | 기존 AoT 자산 (Input/Output/Method/Function/Measurement)을 **재발명하지 않고 활용**한다. |
| **P6** | 모든 계층의 의사결정은 **추적 가능**해야 한다 (사후 분석·튜닝·신뢰 구축). |
| **P7** | 루프는 **수렴**해야 한다. 명령 슬루레이트 제한, 방향 전환 히스테리시스, 누적 편차 anti-windup을 의무화한다. |
| **P8** | **안전은 조율 외부**에 있다. 강우·강풍·고온·저온·통신실패 등은 조율자 알고리즘과 무관하게 사전·사후 게이트에서 강제한다. |
| **P9** | **GIS-aware**. 시설 형상·장치 위치·창호 면적은 알고리즘의 1급 입력이다. AoT의 기존 자산(`Output.lat/lon`, `GeoShape.feature`, `GeoFacility`)에서 추출하며 별도 입력 요구하지 않는다. |
| **P10** | **목표 역할 분리**. R1=VPD primary, R2=Light secondary primary(optional), R3=T·RH constraint-only. T/RH는 직접 추적 목표가 아니라 VPD 분해 산출물 + min/max 제약. |

---

## 1. 문제 정의 — 왜 새 설계인가

### 1.1 현재 시스템의 한계

지금 구조는 **각 액추에이터가 각자 단위 환경값을 보고 독립 PID로 판단**한다.

```
창 PID    → 온도 보고 → 창 열기
냉방 PID  → 온도 보고 → 냉방 켜기     ← 서로 모름, 노이즈 발생
관수 PID  → 습도 보고 → 물 뿌리기
CO₂ PID  → CO₂ 보고 → 주입
```

**문제점:**

- **L1 — 액추에이터 간 충돌**: 창이 열리면서 냉방도 켜지고, 관수가 습도 올리면 창이 반응. 서로가 서로의 외란이 된다.
- **L2 — 외부 조건 무시**: 같은 "창 열기 50%" 명령이 여름·겨울 정반대 결과(가열 vs 냉각). 단순 PID는 이를 모른다.
- **L3 — 단위 데이터 의존**: "T가 높으면 창 연다" 식의 1:1 반응 — 본질적 목표(예: 광합성 최대화)와 분리됨.
- **L4 — VPD 제어 불완전**: VPD = f(T, RH)이므로 단일 액추에이터로는 본질적 통제 불가. 다종 액추에이터 협조 필수.
- **L5 — 장치 성능 차이**: 같은 모터·관수기여도 출력 특성이 시설마다 다름. 제어 로직에 하드코딩하면 이식성 없음.
- **L6 — 시설 형상 미인식**: 어느 면(N/S/E/W)에 측창이 달렸는지, 면적이 얼마인지 알고리즘이 모름. 결과: 강풍시 **모든 개구부 일률 폐쇄** (풍하측까지) — 환기 손실. AoT는 `Output.lat/lon`과 `GeoShape.feature`를 이미 보유하므로 azimuth·area는 추출 가능한데 **활용되지 않음**.

### 1.2 사용자 요구 정리 (대화에서 추출)

> "목적을 달성하기 위한 최적의 환경값을 추적하고 목표에 도달하기 위한 운전 값에 따라 각 장치가 작동하는게 정석"

> "외부 온도가 더 높은 경우(여름)와 낮은 경우(겨울) 장치는 목표에 도달하기 위해 반대 운전을 해야 함"

> "L2를 function으로 처리하지 않고 output에서 개폐 가능한 장치로 open % 값을 받아서 처리하게 하는 것도 괜찮음"

> "단일 function으로 합치는 것도 괜찮긴한데, 설정이 너무 많아지는 점과, 단일 장치를 제어해야 하는 경우(관리, 현장 상황에 따른 사용자 조작) 어려움"

→ **상위 목표 → 동적 운전값 → 장치 작동의 골격으로 재설계.**
→ **장치는 AoT Output**으로 두어 단독 수동 조작 가능성 확보.

---

## 2. 4계층 + 양측 안전 게이트 아키텍처

```
┌─────────────────────────────────────────────────────────────┐
│ Sensor Inputs + External Context Collector                  │
└────────────────────────────┬────────────────────────────────┘
                             ↓
                ╔════════════════════════╗
                ║ Safety Pre-Gate (P8)   ║
                ║  강우·강풍·통신실패     ║
                ║  → 강제 명령 사전 결정  ║
                ╚════════════════════════╝
                             ↓ (강제 명령 없으면 통과)
┌─────────────────────────────────────────────────────────────┐
│ Layer 1 — Goal Manager (목표 관리자)                        │
│  IN  : 작물 종류, 생육 단계, 시각, 정책 우선순위            │
│  OUT : EnvTarget {var: {value, tolerance, priority, mode}}  │
└────────────────────────────┬────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2 — Situation Assessor (상황 평가자)                  │
│  IN  : EnvTarget, 모든 센서값(내부+외부)                    │
│  로직: VPD 목표 → T·RH 보조 목표로 분해 (§5.4)              │
│  OUT : SituationReport {state, context, deviation,          │
│                          limiting_factor, mode}              │
└────────────────────────────┬────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3 — Actuator Coordinator (액추에이터 조율자)          │
│  IN  : SituationReport, 등록된 ActuatorProfile 목록         │
│  로직: live_effect 평가 → 우선순위·비용 선택                │
│        slew·hysteresis·anti-windup 적용 (§4)                │
│  OUT : ActuatorCommands {actuator_id: {value, ttl, reason}} │
└────────────────────────────┬────────────────────────────────┘
                             ↓
                ╔════════════════════════╗
                ║ Safety Post-Gate (P8)  ║
                ║  하드 한계·수동락 검사  ║
                ║  → 명령 정합성 강제     ║
                ╚════════════════════════╝
                             ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 4 — Actuator Outputs (장치 출력기)                    │
│  IN  : 정규화 명령 (% 또는 on/off duration)                 │
│  로직: 장치별 캘리브레이션 → 물리 신호                       │
│  OUT : 위치/상태 측정값 → InfluxDB                          │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 계층별 책임 요약

| Layer | 한 줄 책임 | 시간 스케일 |
|-------|-----------|-------------|
| Pre-Gate | "먼저 강제할 안전 명령이 있나" | 매 사이클 |
| L1 Goal | "지금 무엇을 추구해야 하나" | 시·일 단위 |
| L2 Situation | "지금 무엇이 잘못됐고 왜인가" | 분 단위 |
| L3 Coordinator | "그래서 누구를 어떻게 시킬까" | 분 단위 |
| Post-Gate | "결과 명령이 안전·정합성 위반인가" | 매 사이클 |
| L4 Output | "받은 명령을 물리 신호로" | 초 단위 |

---

## 3. 핵심 추상 — `ActuatorProfile`

각 Layer 4 Output 플러그인이 자기 자신을 신고하는 메타데이터. **Layer 3은 이 프로필만 보고 조율한다.**

### 3.1 스키마

```python
ACTUATOR_PROFILE = {
    'actuator_id'  : '<unique_id>',             # AoT Output unique_id
    'kind'         : 'opening' | 'cooler' | 'heater' | 'fogger'
                   | 'co2_injector' | 'shade' | 'curtain',
    'capabilities' : ['ventilation', 'cooling', 'humidify', ...],
    'cost_fn'      : CostFn,                    # ↓ §3.4
    'response_sec' : 60,                        # 명령 후 효과 발현까지
    'safe_default' : 0.0,                       # 명령 없을 때 안전 위치
    'manual_lock'  : ManualLockState,           # ↓ §3.6
    'effect_model' : {                          # ↓ §3.2~§3.3
        'temperature': EffectFn,
        'humidity'   : EffectFn,
        'co2'        : EffectFn,
        # 'vpd'은 1급 변수가 아님 — L2에서 T·RH로 분해 (§5.4)
    },
    'cmd_constraints': {                        # ↓ §4.3
        'slew_per_cycle' : 20.0,                # 사이클당 최대 명령 변화 (%)
        'min_on_pct'     : 5.0,                 # 미만은 0으로 스냅
        'min_dwell_sec'  : 30.0,                # 명령 유지 최소 시간
    },
}
```

### 3.2 `EffectFn` 시그니처와 단위 규약

```python
EffectFn = Callable[[EnvContext, float], EffectResult]

EnvContext = {
    'T_int', 'RH_int', 'CO2_int', 'VPD_int',      # 내부 상태
    'T_ext', 'RH_ext', 'CO2_ext', 'wind', 'rain', # 외부 상태
    'solar', 'dewpoint',
    'cycle_sec',                                  # 현재 사이클 주기
}

EffectResult = {
    'direction'       : '↑' | '↓' | '0',
    'magnitude_native': float,    # 변수 native 단위 / 사이클
                                  #   T: °C/cycle, RH: %/cycle,
                                  #   CO2: ppm/cycle, VPD: kPa/cycle
}
```

**단위 규약 (R1)**:
- `magnitude_native`는 **변수의 native 단위 / 1 사이클**이다.
- 누적 추적(`accumulated`), 잔여(`residual`), 공차(`tolerance`)도 모두 native 단위.
- 우선순위 정렬 시에만 정규화 (`|deviation| / tolerance × priority`).
- 정규화는 비교용 일시값이고 alleen 누적기에 들어가지 않는다.

### 3.3 효과 함수 예시

```python
# ── 개구부 (창) ── 외부 조건과 풍속 활용
def opening_temp_effect(env, cmd_pct):
    """외부 온도 방향으로 끌어당김. 풍속이 강하면 효과 가속."""
    delta = env['T_ext'] - env['T_int']
    if abs(delta) < 0.5:
        return {'direction': '0', 'magnitude_native': 0.0}
    direction = '↑' if delta > 0 else '↓'
    wind_boost = 1.0 + 0.15 * min(env.get('wind', 0.0), 8.0)  # 풍속 가속, 8m/s 상한
    magnitude = abs(delta) * (cmd_pct / 100) * K_OPENING_T * wind_boost
    return {'direction': direction, 'magnitude_native': magnitude}

def opening_humid_effect(env, cmd_pct):
    delta = env['RH_ext'] - env['RH_int']
    if abs(delta) < 1.0:
        return {'direction': '0', 'magnitude_native': 0.0}
    direction = '↑' if delta > 0 else '↓'
    wind_boost = 1.0 + 0.15 * min(env.get('wind', 0.0), 8.0)
    return {'direction': direction,
            'magnitude_native': abs(delta) * (cmd_pct / 100) * K_OPENING_RH * wind_boost}

def opening_co2_effect(env, cmd_pct):
    """외부 CO₂(~400ppm)로 수렴."""
    excess = env['CO2_int'] - env.get('CO2_ext', 400)
    if excess <= 20:
        return {'direction': '0', 'magnitude_native': 0.0}
    return {'direction': '↓',
            'magnitude_native': excess * (cmd_pct / 100) * K_OPENING_CO2}

# ── 냉방기 ── 외부 무관, 항상 냉각
def cooler_temp_effect(env, cmd_pct):
    return {'direction': '↓', 'magnitude_native': K_COOLER_T * (cmd_pct / 100)}

def cooler_humid_effect(env, cmd_pct):
    """응결로 RH 상승 경향."""
    return {'direction': '↑', 'magnitude_native': K_COOLER_RH * (cmd_pct / 100)}

# ── 포그/관수 ── 가습 + 증발냉각
def fogger_humid_effect(env, cmd_pct):
    return {'direction': '↑', 'magnitude_native': K_FOG_RH * (cmd_pct / 100)}

def fogger_temp_effect(env, cmd_pct):
    return {'direction': '↓', 'magnitude_native': K_FOG_T * (cmd_pct / 100)}

# ── 난방기 ──
def heater_temp_effect(env, cmd_pct):
    return {'direction': '↑', 'magnitude_native': K_HEATER_T * (cmd_pct / 100)}

def heater_humid_effect(env, cmd_pct):
    """온도↑로 RH↓ (절대습도 일정 시)."""
    return {'direction': '↓', 'magnitude_native': K_HEATER_RH * (cmd_pct / 100)}
```

### 3.4 `CostFn` — 동적 비용

```python
CostFn = Callable[[EnvContext, float], float]
# (env_context, cmd_pct) -> cost_value (낮을수록 우선)

# 정적 비용 — 호환용 기본값
cost_static = lambda env, pct: 3.0

# 시간대 전기요금 반영 예시
def cost_cooler_electric(env, pct):
    hour = datetime.fromtimestamp(env['now_ts']).hour
    peak = 9.0 if 9 <= hour < 22 else 4.0   # 피크/오프피크
    return peak * (pct / 100)

# 가스난방 — 단위 가스비, on/off 무관 고정 점화비 추가
def cost_heater_gas(env, pct):
    return 6.0 + 5.0 * (pct / 100)
```

기본값은 정적 상수도 허용. 추후 시간대 요금·연료비를 자연스럽게 흡수할 수 있도록 함수형으로 둔다.

### 3.5 캘리브레이션 계수 (`K_*`) — 장치 차이 흡수

`K_*` 계수는 장치별 캘리브레이션 파라미터. **모듈 변수 기본값 + DB 사용자 오버라이드** 형태로 보관.

**머지 규칙 (R2)**:
```
effective_K = K_db if K_db not in (None, '', 0)  else K_module_default

# 즉:
# 1. DB(custom_options)에 사용자가 입력한 값이 있으면 우선
# 2. DB 값이 비어 있거나 None이면 모듈 기본값 사용
# 3. 0은 "비활성화 의도"로 보지 않고 빈 값으로 간주 (오작동 방지)
#    → 0을 진짜 비활성화로 두려면 별도 enabled 플래그 사용
```

L3 조율 로직은 `effective_K`만 본다 — 시설 차이·장치 노후화 시 DB 값만 조정하면 됨.

### 3.6 수동 오버라이드 락 (`ManualLockState`)

사용자가 AoT Output 페이지에서 수동 조작하면 일정 시간 조율자 명령을 차단:

```python
ManualLockState = {
    'locked'        : bool,
    'until_ts'      : float,     # 락 해제 시각 (epoch)
    'manual_value'  : float,     # 사용자가 설정한 값
    'reason'        : str,       # 'user_ui' | 'maintenance' | 'pre_gate'
}
```

L3는 매 사이클 시작 시 모든 액추에이터의 `manual_lock`을 조회:
- 락 활성 → 그 액추에이터는 후보 제외, `live_effect` 계산 시 0%로 가정
- 의사결정 로그에 `reason=20 (manual_override)`으로 기록
- 락 만료 즉시 다음 사이클부터 정상 편입

기본 락 TTL: 30분 (사용자 설정 가능).

---

## 4. Layer 3 조율 알고리즘

### 4.1 안정성 메커니즘 (P7)

조율자는 다음 세 장치를 의무적으로 적용한다:

1. **명령 슬루레이트 제한**:
   `cmd_new ∈ [cmd_prev - slew_per_cycle, cmd_prev + slew_per_cycle]`
   → 한 사이클 내 급변 차단 (액추에이터 보호 + 외란 흡수).

2. **방향 전환 히스테리시스**:
   ```
   tolerance_inner = tolerance × 0.5   # 동작 진입선
   tolerance_outer = tolerance × 1.0   # 동작 해제선
   |deviation| > tolerance_outer → 동작 시작
   |deviation| < tolerance_inner → 동작 정지
   ```
   → 공차 경계에서 진동 차단.

3. **Anti-windup 적분항**:
   `compute_cmd`에 PI 적분기 사용. 명령이 한계(0/100)에 닿으면 적분 정지.
   ```
   integral[var] += residual × dt          # 누적 편차
   if |cmd_raw| at limit and same_sign:    # 포화 + 방향 동일 시
       integral[var] -= residual × dt      # back-calculate (windup 방지)
   ```

### 4.2 `compute_cmd` 명세

```python
def compute_cmd(residual_native, var_target, actuator, integral_state):
    """
    PI 형태로 명령 산출. 단위는 native.
    residual_native : 잔여 편차 (해결 못한 부분, native)
    var_target      : EnvTarget[var] (tolerance, priority 포함)
    actuator        : ActuatorProfile (live_effect 계산용)
    integral_state  : {var: cumulative} — 사이클 간 보존
    """
    Kp = actuator.gains.get('kp', 1.0)
    Ki = actuator.gains.get('ki', 0.05)

    p_term = Kp * residual_native
    i_term = Ki * integral_state.get(var, 0.0)

    # 액추에이터 단위 효과 크기 (cmd=100% 기준)
    unit_mag = actuator.live_effect[var].magnitude_native or 1e-6

    # 필요 효과량 / 단위 효과량 = 명령 비율
    cmd_pct = (p_term + i_term) / unit_mag * 100.0

    return clamp(cmd_pct, 0, 100)
```

### 4.3 의사코드 (안정성 통합 버전)

```
function coordinate(situation, profiles, prev_commands, integral_state):
    commands     = {}
    accumulated  = {var: 0.0 for var in situation.deviation}    # native 단위
    sorted_vars  = sort_by(|deviation_native| / tolerance × priority, descending)

    # 1. 라이브 효과 계산 (cmd=100% 기준 단위 효과)
    for p in profiles:
        if p.manual_lock.locked:
            commands[p.actuator_id] = {'value': 0.0, 'reason': 20}
            continue
        p.live_effect = {var: p.effect_model[var](situation.context, 100)
                         for var in p.effect_model}

    # 2. 변수별 순회 — 가장 시급한 것부터
    for var in sorted_vars:
        residual = situation.deviation_native[var] - accumulated[var]
        tol      = situation.target[var].tolerance

        # 히스테리시스 — 이전 사이클 액션 여부 따라 진입선 다름
        active = was_active_last_cycle(var)
        tol_use = tol * 0.5 if not active else tol * 1.0
        if |residual| < tol_use:
            integral_state[var] *= 0.95   # 누적 천천히 감쇠
            continue

        needed_dir = '↓' if residual > 0 else '↑'

        # 적분 누적
        integral_state[var] += residual * (cycle_sec / 60.0)

        # 후보 + 비용 정렬
        helpers = [p for p in profiles
                   if p.actuator_id not in commands             # 락된 것 제외
                   and p.live_effect[var].direction == needed_dir]
        helpers.sort(key=lambda p: p.cost_fn(situation.context, 100))

        for p in helpers:
            if |residual| < tol * 0.5: break

            # 부작용 평가 — 다른 변수에 미치는 영향
            side_effects = compute_side_effects(p, situation, accumulated)
            if creates_conflict(side_effects, situation.deviation_native, tol):
                continue

            # PI 명령 산출
            cmd_raw = compute_cmd(residual, situation.target[var],
                                  p, integral_state)

            # Anti-windup — 한계 포화 + 방향 동일 시 적분 되돌림
            if cmd_raw in (0, 100) and same_sign(residual, integral_state[var]):
                integral_state[var] -= residual * (cycle_sec / 60.0)

            # 슬루레이트 제한
            cmd_prev = prev_commands.get(p.actuator_id, 0.0)
            slew     = p.cmd_constraints['slew_per_cycle']
            cmd_lim  = clamp(cmd_raw, cmd_prev - slew, cmd_prev + slew)

            # 최소 ON 스냅
            if 0 < cmd_lim < p.cmd_constraints['min_on_pct']:
                cmd_lim = 0.0

            commands[p.actuator_id] = {'value': cmd_lim, 'reason': 1 if first else 2}

            # 누적 효과 업데이트 (모든 변수)
            for v in p.live_effect:
                eff = p.live_effect[v]
                signed = eff.magnitude_native * (cmd_lim / 100) * \
                         (+1 if eff.direction == '↑' else -1 if eff.direction == '↓' else 0)
                accumulated[v] += signed

            residual -= signed_for_var

    # 3. 명령 안 받은 액추에이터는 안전 기본값
    for p in profiles:
        commands.setdefault(p.actuator_id, {'value': p.safe_default, 'reason': 0})

    return commands, integral_state
```

### 4.4 계절별 자동 분기 — 알고리즘 검증

**같은 상황: T_int=28°C, T_target=25°C (편차 +3°C, 냉각 필요)**

#### 여름 (T_ext=35°C, RH_ext=70%, 풍속 1m/s)

```
Step 1: 온도 변수 처리
Step 2: live_effect 평가
  - 창: T 효과 = ↑ (외기 더 뜨거움) → 후보 제외
  - 냉방: T 효과 = ↓ → 후보
  - 포그: T 효과 = ↓ (증발냉각) → 후보

Step 3: cost_fn 정렬 (예: 포그 < 냉방)
Step 4: 부작용 평가
  - 포그: humidity ↑ (현재 65%, 목표 70% → 도움)
  - 채택

→ 명령: 창 0%, 포그 50%, 냉방 30%
```

#### 겨울 (T_ext=5°C, RH_ext=30%, 풍속 4m/s)

```
Step 2: live_effect 평가
  - 창: T 효과 = ↓ (외기 더 차가움), 풍속 가속 → 후보 채택!
  - 냉방: T 효과 = ↓ → 후보지만 cost 높음
  - 포그: T 효과 = ↓ → 후보

Step 3: cost_fn 정렬 → 창 cost 가장 낮음
Step 4: 부작용 평가
  - 창: RH ↓ (외기 건조) → RH 편차 작으면 허용

→ 명령: 창 30%, 냉방 0%, 포그 0%
```

**같은 알고리즘이 동일 코드로 반대 명령을 만든다.** P2 원칙의 결과.

---

## 5. Layer 1·2 — 목표 관리자 + 상황 평가자

### 5.1 Layer 1 입력

- **작물 프로필**: 작목 ID + 생육 단계 (육묘·생장·개화·수확 등)
- **시각**: 주야 분리 (광합성 활성 시간 vs 호흡 시간)
- **정책 모드**: `photosynthesis_max` | `energy_save` | `safety_first` | `quality_focus`
- **외부 조건**: 폭염·한파 시 안전 모드 자동 진입

### 5.2 작물 라이브러리 (정적 테이블 — 초기)

```yaml
crops:
  tomato:
    stages:
      seedling:
        day:    {T: 25, RH: 70, VPD: 0.8, CO2: 800}
        night:  {T: 18, RH: 75, VPD: 0.5, CO2: 400}
      vegetative:
        day:    {T: 24, RH: 65, VPD: 1.0, CO2: 1000}
        night:  {T: 17, RH: 70, VPD: 0.6, CO2: 400}
      flowering:
        day:    {T: 23, RH: 60, VPD: 1.2, CO2: 1000}
```

### 5.3 Layer 1 출력 — `EnvTarget`

#### 변수 역할 (R1/R2/R3 — 광합성 최적화 관점)

| 역할 | 변수 | 운용 |
|---|---|---|
| **R1 — Primary** | `vpd` | 1차 추적 목표. 항상 활성. L2가 T/RH 보조 목표로 분해 (§5.4) |
| **R2 — Secondary primary** (optional) | `light` (PAR/PPFD) | 보광 사용 시에만 활성. 대부분 시설은 보광 없음 → 비활성. 활성 시 cost 낮은 장치 우선 활용 |
| **R3 — Constraint-only** | `temp_max/min`, `humid_max/min` | **target이 아닌 제약**. 위반시 강제 force-cool/heat/humidify/dehumidify로 제약 복귀까지만 운용. 평상시에는 R1 분해 결과를 따른다. |
| 보조 | `co2` | 광합성 제한 인자가 CO₂일 때 priority 상승 (§5.6) |

```python
{
    # R1: VPD primary
    'vpd':         {'value': 1.0,  'tolerance': 0.1, 'priority': 1.2, 'unit': 'kPa'},

    # R2: Light secondary primary (set only when supplemental lighting is registered)
    'light':       {'value': 400,  'tolerance': 50,  'priority': 0.9, 'unit': 'µmol/m²/s'},

    # R3: T/RH as constraints (min/max bounds, not tracked targets)
    'temp_max':    {'value': 35.0, 'unit': '°C'},
    'temp_min':    {'value': 5.0,  'unit': '°C'},
    'humid_max':   {'value': 90.0, 'unit': '%'},
    'humid_min':   {'value': 30.0, 'unit': '%'},

    # CO₂ secondary (boosted when limiting factor is co2)
    'co2':         {'value': 1000, 'tolerance': 100, 'priority': 0.6, 'unit': 'ppm'},
}
```

L2가 R1을 T/RH 보조 목표로 분해(§5.4)하지만, 그 분해된 T/RH는 **R3 min/max를 절대 위반할 수 없다**. 위반 위험시 R3가 우선해 force-mode로 진입.

### 5.4 Layer 2 — VPD 분해 정책 (택일: 옵션 A 채택)

VPD는 1급 변수가 아니다. **L2가 VPD 목표를 T·RH 보조 목표로 분해**해 L3에 전달한다 (옵션 A).

이유:
- L3 알고리즘은 독립 변수만 다루는 것이 단순·안정.
- 액추에이터 effect는 T·RH·CO₂에 직접 작용하고, VPD는 거기서 유도되는 종속변수.
- 비선형 자코비언을 L3에 넣으면 알고리즘이 복잡해지고 이중 카운팅 위험.

#### 분해 알고리즘

```python
def decompose_vpd(env_target, current_state):
    """
    VPD 목표를 T·RH 보조 목표로 분해.
    
    VPD = (1 - RH/100) × SVP(T)
    SVP(T) ≈ 0.6108 × exp(17.27T/(T+237.3))   [kPa]
    """
    if 'vpd' not in env_target:
        return env_target
    
    vpd_t = env_target['vpd']['value']
    T_now, RH_now = current_state['T'], current_state['RH']
    vpd_now = compute_vpd(T_now, RH_now)
    
    if abs(vpd_now - vpd_t) < env_target['vpd']['tolerance']:
        return env_target   # 분해 불필요
    
    # 1) 현재 T 유지 가정 시 필요한 RH
    rh_needed = (1 - vpd_t / svp(T_now)) * 100
    # 2) 현재 RH 유지 가정 시 필요한 T
    t_needed_for_vpd = invert_svp(vpd_t / (1 - RH_now/100))
    
    # 3) T 목표·RH 목표 각각의 가용 여유 평가
    #    → 가용 여유에 비례해서 두 변수에 분할 부담
    t_room  = abs(env_target['temperature']['value'] - T_now)
    rh_room = abs(env_target['humidity']['value']    - RH_now)
    
    weight_t  = t_room  / (t_room + rh_room + 1e-6)
    weight_rh = 1 - weight_t
    
    # 4) 보조 목표를 T, RH의 priority에 기여 형태로 추가
    #    (덮어쓰는 것이 아니라 priority 가중치로 합산)
    env_target['temperature']['priority'] += env_target['vpd']['priority'] * weight_t
    env_target['humidity']['priority']    += env_target['vpd']['priority'] * weight_rh
    
    # 5) value도 가중 혼합 (현 목표와 vpd-derived 목표 사이)
    env_target['temperature']['value'] = mix(env_target['temperature']['value'],
                                             t_needed_for_vpd, weight_t)
    env_target['humidity']['value']    = mix(env_target['humidity']['value'],
                                             rh_needed, weight_rh)
    
    # VPD는 SituationReport에서 진단용으로만 보존 — L3에는 노출 안 함
    env_target['_vpd_diag'] = env_target.pop('vpd')
    return env_target
```

### 5.5 Situation Context 분리

```python
{
    'internal': {'T': 28.0, 'RH': 60.0, 'VPD': 1.5, 'CO2': 850},
    'external': {'T': 35.0, 'RH': 45.0, 'wind': 3.2, 'rain': 0.0,
                 'solar': 850, 'CO2': 410, 'dewpoint': 18.0},
    'trends'  : {'T_5min': '+0.3', 'solar_15min': '+120'},
    'now_ts'  : 1715140800,
    'cycle_sec': 60,
}
```

### 5.6 광합성 제한 인자 (Limiting Factor)

```python
def limiting_factor(state, target, crop_profile):
    scores = {
        'light':       light_response(state['PAR']),
        'co2':         co2_response(state['CO2']),
        'temperature': temp_response_curve(state['T'], crop_profile),
        'water':       vpd_response(state['VPD']),
    }
    return min(scores, key=scores.get)
```

→ **현재 광합성 병목**을 식별해 해당 변수의 우선순위를 올림.

### 5.7 운전 모드 결정

| 모드 | 조건 | 의미 |
|------|------|------|
| `cooling` | T_int > T_target + tol | 냉각 우선 |
| `heating` | T_int < T_target - tol | 가열 우선 |
| `humidify` | RH_int < RH_target - tol | 가습 우선 |
| `dehumidify` | RH_int > RH_target + tol | 제습 우선 |
| `co2_enrich` | CO2_int < CO2_target - tol & 광합성 활성 | CO₂ 보충 |
| `conservation` | 모두 tolerance 내 | 유지·에너지 절약 |
| `emergency` | Pre-Gate가 강제 명령 발동 | 모든 조율 차단 |

복합 모드 가능 (`cooling` + `humidify` 동시).

---

## 6. 안전 게이트 (P8) — 조율 알고리즘 외부

### 6.1 Pre-Gate (사전 게이트)

L1~L3 진입 전에 평가. 발동 시 **L1~L3을 우회**하고 직접 L4에 강제 명령 전달.

| 트리거 | 조건 | 강제 명령 | TTL |
|-------|------|----------|------|
| 강우 | rain_sensor > 임계 | 모든 개구부 0% | 5분 또는 해제까지 |
| 강풍 | wind > 임계 | 개구부 0%, 차광막 0% | 5분 또는 해제까지 |
| 외부 컨텍스트 만료 | last_ext_ts > 5분 | 모든 액추에이터 safe_default | 외부 복구까지 |
| 내부 센서 만료 | last_int_ts > 임계 | conservation 모드 강제 | 센서 복구까지 |
| 폭염 | T_ext > 안전 임계 + T_int > 위험 임계 | 개구부 100%, 차광 100%, 냉방 ON | 해제까지 |
| 한파 | T_ext < 안전 임계 + T_int < 위험 임계 | 개구부 0%, 보온 100%, 난방 ON | 해제까지 |

발동 시:
- 의사결정 로그 `reason=12 (safety_pre_gate)`
- 운전 모드 `emergency`로 마킹
- 해제 후 L3 적분 상태 리셋 (bumpless 복귀)

### 6.2 Post-Gate (사후 게이트)

L3 결과를 L4 전달 전 검사.

| 검사 | 동작 |
|------|------|
| 하드 한계 위반 | 0~100 클램프 |
| 수동락 액추에이터 | 명령 무시, 사용자 수동값 유지 |
| 동일 사이클 모순 (예: 난방+냉방 동시 ON) | cost 낮은 쪽 채택, 다른 쪽 0 |
| 명령 NaN/Inf | 안전 기본값 강제 |
| 통신 실패 누적 액추에이터 | 후보에서 영구 제외 알림 |

### 6.3 통신 실패·타임아웃 정책

```
Output 명령 전달 (DaemonControl.output_on):
  1차 실패 → 1초 대기 후 1회 재시도
  연속 2회 실패 → 해당 actuator를 'unavailable'로 마킹 (5분)
  unavailable 액추에이터:
    - 다음 사이클부터 후보 제외
    - 5분 후 자동 재시도
    - 사용자에게 알림 (UI)
  의사결정 로그: reason=13 (output_unavailable)
```

---

## 7. Layer 4 — Output 플러그인

### 7.1 표준 인터페이스

```python
ACTUATOR_PROFILE = {...}   # 모듈 변수 (§3.1)

class CustomOutput(AbstractOutput):
    OUTPUT_INFORMATION = {
        'output_name_unique': 'opening_actuator',
        'output_name': '시설 개구부',
        'output_types': ['value'],
        'channels_dict': {0: {...}, 1: {...}},
    }

    def output_switch(self, state, output_type, amount, ...):
        """0~100% 명령 수신 → 캘리브레이션 → 물리 제어."""
        ...

    def get_profile(self) -> dict:
        """L3 조율자가 호출. 캘리브레이션·락 적용된 프로필 반환.
        
        머지 규칙 (§3.5 R2):
          DB 값 우선, 빈 값은 모듈 기본 fallback.
        """
        return apply_calibration(ACTUATOR_PROFILE, self.custom_options)

    def manual_acquire(self, value, ttl_sec=1800, reason='user_ui'):
        """수동 조작 시 락 설정 — UI에서 호출."""
        self._manual_lock = ManualLockState(
            locked=True, until_ts=time.time() + ttl_sec,
            manual_value=value, reason=reason)

    def manual_release(self):
        self._manual_lock = ManualLockState(locked=False, until_ts=0)
```

### 7.2 Output 종류

| 플러그인 | 기능 | 채널 |
|---------|------|------|
| `opening_actuator.py` | 개구부 (측창·천창) | 0~100% 위치 |
| `hvac_actuator.py` | 냉난방기 | on/off 또는 설정온도 |
| `fogger_actuator.py` | 포그·관수 가습 | on/off + 시간 또는 % |
| `co2_injector_actuator.py` | CO₂ 주입 | on/off + 시간 |
| `shade_curtain_actuator.py` | 차광막·보온덮개 | 0~100% 위치 |

### 7.3 단독 사용성 보장

- AoT Output 페이지에서 **수동 제어 가능** (§3.6 락으로 조율자 차단)
- 다른 PID·스케줄에서 위임 사용 가능
- 표준 측정값 등록 → InfluxDB 자동 기록
- 조율자 정지 시에도 Output은 자기 안전 동작 유지

---

## 8. 외부 환경 컨텍스트 수집기 (단일 진실원)

### 8.1 책임

- 모든 외부 센서를 한 번에 수집 (T_ext, RH_ext, wind, rain, solar, dewpoint, CO2_ext)
- `EnvContext['external']`로 시스템 단일 진실원 제공
- 캐시·만료·fallback 정책 보유

### 8.2 Fallback 정책 (단일점 장애 방지)

```
정상 수집 → 캐시 갱신 + last_ts 업데이트
센서 누락 → 마지막 정상값 유지, age 표시

age > 60s   : 경고 (로그)
age > 5분   : 만료 — Pre-Gate 발동 (모든 액추에이터 safe_default)
age > 30분  : 시스템 알림 (관리자 호출)
```

### 8.3 다중 외부 센서 처리

같은 변수에 여러 외부 센서 등록 시:
- Median 또는 가중평균 사용 (단일 센서 오류 흡수)
- 개별 센서 만료 시 나머지로 fallback

---

## 9. 사이클 주기 결정

### 9.1 규칙

```
cycle_sec ≥ max(actuator.response_sec for all registered) × 1.5

기본값 60초.
빠른 응답 액추에이터(<30s)만 있으면 30초까지 단축 가능.
느린 액추에이터(개구부 모터 90s+ 포함) 있으면 120s 권장.
```

이유: 한 사이클 명령 효과가 발현되기 전에 다음 사이클이 또 명령하면 over-shoot → 진동.

### 9.2 사용자 설정

`update_period`는 Function의 custom_option으로 노출하되, 등록된 액추에이터의 max(response_sec)보다 작으면 경고 후 자동 보정.

---

## 10. 의사결정 로깅 (관측성)

매 사이클의 결정을 InfluxDB 측정값으로 기록.

| measurement | channel | 의미 |
|------------|---------|------|
| `goal_target_<var>` | 0~9 | L1 → 현재 목표값 |
| `goal_priority_<var>` | 10~19 | L1 → 현재 우선순위 |
| `situation_deviation_<var>` | 20~29 | L2 → native 편차 |
| `situation_limiting_factor` | 30 | L2 → 광합성 제한 인자 ID |
| `situation_mode` | 31 | L2 → 운전 모드 코드 |
| `coord_actuator_<id>_command` | 40+ | L3 → 액추에이터별 명령 |
| `coord_actuator_<id>_reason` | 50+ | L3 → 선택/배제 근거 코드 |
| `coord_integral_<var>` | 60+ | L3 → 적분 누적 (디버그) |
| `safety_gate_active` | 70 | Gate → 활성 게이트 비트마스크 |
| `output_<id>_position` | (각 Output 자체) | L4 → 실제 위치/상태 |

### 10.1 근거 코드

| 코드 | 의미 |
|------|------|
| 0 | 사용 안 함 (모든 변수 허용 범위 내) |
| 1 | 효과 방향 일치, 비용 최저 |
| 2 | 효과 방향 일치, 보조 |
| 10 | 효과 방향 불일치 — 제외 |
| 11 | 부작용 충돌 — 제외 |
| 12 | 안전 Pre-Gate 강제 명령 |
| 13 | Output unavailable (통신 실패) |
| 14 | 안전 Post-Gate 보정 |
| 20 | 수동 오버라이드 — 락 활성 |

---

## 11. 단계별 구축 로드맵

설계는 4계층 + 양측 게이트 전체를 확정, 구현은 **하부에서 상부로** 검증하며 올라간다.

### Phase A — 인프라 + 표준 정의

- A1. `ActuatorProfile` 표준 스키마 확정 (§3.1) + 캘리브레이션 머지 규칙 R2 (§3.5)
- A2. `EffectFn` / `CostFn` 시그니처 확정, 단위 규약 R1 (§3.2)
- A3. Output 플러그인이 자기 프로필을 노출하는 메커니즘 (`get_profile()`)
- A4. **외부 환경 컨텍스트 수집기 + Fallback 정책** (§8)
- A5. 의사결정 로깅 채널 표준 (§10)
- A6. **안전 Pre-Gate / Post-Gate 프레임워크** (§6) — 구현은 비어 있어도 호출 지점만 확보
- A7. `ManualLockState` API + Output 페이지 락/해제 UI (§3.6)
- A8. 기존 `opening_brain.py` / `opening_device.py` 보존 (참고용 격리)

### Phase B — Layer 4 Output 플러그인

- B1. `opening_actuator.py` (지금 `opening_device.py`를 Output으로 재작성)
- B2. `hvac_actuator.py`
- B3. `fogger_actuator.py`
- B4. `co2_injector_actuator.py`
- B5. `shade_curtain_actuator.py`

각 Output은 단독 검증 — 수동 제어 + 안정성 + 락 동작 확인 후 다음.

### Phase C — Layer 3 조율자

- C1. **`ActuatorProfile` 발견 메커니즘**:
  - AoT Output 등록 시 DB의 output table에 record가 생긴다.
  - 조율자 Function은 `output table`을 query → `output_name_unique`가 본 설계의 actuator 종류 목록에 속하는 record만 추림.
  - 그 Output 인스턴스의 `get_profile()` 호출해 ACTUATOR_PROFILE 수집.
  - Foreman의 직무 관리와는 별개. AoT 기존 Output 등록 흐름을 그대로 활용.
- C2. 효과 방향 평가 엔진 (`live_effect` 계산)
- C3. 조율 알고리즘 (§4) — 슬루·히스테리시스·anti-windup 포함
- C4. 부작용 충돌 검출
- C5. 의사결정 로깅 적용

### Phase D — Layer 2 상황 평가자

- D1. 외부/내부 상태 분리 + 추세 산출
- D2. 광합성 제한 인자 모델 (간단 룩업 → 점진 정교화)
- D3. 운전 모드 자동 결정 (§5.7)
- D4. **VPD 분해 (§5.4)**
- D5. Pre-Gate 트리거 평가 (강우·강풍·만료)

### Phase E — Layer 1 목표 관리자

- E1. 작물 프로필 라이브러리 (정적 YAML/JSON 시작)
- E2. 시간 변환 (주야 다른 목표)
- E3. 정책 모드 (광합성 최대 / 에너지 절약 / 안전 우선)
- E4. Method 활용한 시간 곡선 보간

### Phase F — 자동 캘리브레이션 (선택)

- F1. 장치별 효과 계수 `K_*` 자동 학습 (효과 측정 → 회귀)
- F2. 외부 조건별 효과 모델 정밀화

---

## 12. 결정 항목 (Phase A 진입 전)

| ID | 결정 사항 | 결정 |
|----|----------|------|
| **D1** | `ActuatorProfile` 위치 | **모듈 변수 + DB 오버라이드**, 머지 규칙 R2 (§3.5) |
| **D2** | 외부 환경 센서 | **단일 진실원** (외부 컨텍스트 수집기) + Fallback (§8.2) |
| **D3** | L1~L3 분리 시점 | **단일 Function 시작**, 인터페이스만 명확히 분리 |
| **D4** | Output ↔ Coordinator 통신 | **표준 Output API** (`DaemonControl.output_on`) + 실패 정책 (§6.3) |
| **D5** | VPD 처리 방식 | **옵션 A** — L2가 T·RH 보조 목표로 분해, L3에는 VPD 미노출 (§5.4) |
| **D6** | 광합성 모델 | **단순 제한 인자 룩업** 시작, F단계에서 정교화 |
| **D7** | 캘리브레이션 학습 | **수동 시작**, F단계에서 자동화 |
| **D8** | `cost_index` 형태 | **`cost_fn` 함수형** (§3.4) — 정적 상수도 허용 |
| **D9** | 사이클 주기 | `max(response_sec) × 1.5` 규칙, 기본 60s (§9) |

---

## 13. 데이터 흐름 (한 사이클)

```
[사이클 시작]
    │
    ├─► 외부 컨텍스트 수집기
    │     · T_ext, RH_ext, wind, rain, solar, dewpoint, CO2_ext
    │     · age 검사 → 만료 시 Pre-Gate에 시그널
    │     · → InfluxDB
    │
    ├─► Pre-Gate 평가
    │     · 강우/강풍/만료/극한온도 검사
    │     · 발동 → L1~L3 우회, 강제 명령 → Post-Gate
    │     · 비발동 → L1 진행
    │
    ├─► L1 Goal Manager
    │     · 작물·생육단계·시각·정책 → EnvTarget
    │     · → InfluxDB (goal_target_*)
    │
    ├─► L2 Situation Assessor
    │     · 내부 센서 + 외부 컨텍스트 수집
    │     · VPD 분해 → T·RH 보조 목표 가중 추가
    │     · 편차·제한인자·운전모드 산출
    │     · → InfluxDB (situation_*)
    │
    ├─► L3 Actuator Coordinator
    │     · 등록 Output들의 ActuatorProfile 조회
    │     · 락 액추에이터 제외
    │     · live_effect 평가
    │     · 우선순위·비용·부작용·슬루·히스테리시스·적분 적용
    │     · → InfluxDB (coord_*)
    │
    ├─► Post-Gate
    │     · 하드 한계, 수동락, 모순 검사
    │     · → InfluxDB (safety_gate_active)
    │
    ├─► Output 명령 발송 (DaemonControl.output_on, 실패 시 재시도)
    │     · 각 Output: 캘리브레이션 적용 → 물리 신호
    │     · → InfluxDB (output_*_position)
    │
    └─► 다음 사이클 대기
```

---

## 14. Facility & GIS Integration (v2)

### 14.1 동기 — 왜 GIS가 알고리즘의 1급 입력인가

§1.1의 L6에서 정리한 대로, 같은 "측창 50% 개방" 명령도 **풍하측은 환기로 작용하고 풍상측은 강풍 유입**으로 작용한다. 풍속 임계만 보고 모든 개구부를 일률 폐쇄하면:

- 풍하측 환기 손실 → VPD/온도 제어 실패
- 무풍 시 면적 큰 천창과 작은 측창이 같은 cmd_pct에서 같은 효과로 모델링 → 큰 창에서 과도 환기

GIS 데이터(개구부 방향·면적)를 알고리즘에 도입해야 R1(VPD)·R3(T/RH 제약)을 시설 형상에 맞게 충실히 추적할 수 있다.

### 14.2 활용할 기존 자산

AoT는 별도 입력 없이 다음에서 facility 정보를 추출한다:

| 자산 | 보유 데이터 | 활용 |
|---|---|---|
| `Output.latitude/longitude` | 장치별 위치점 | 개구부 위치 좌표 |
| `Output.location*` | I2C/UART/GPIO 등 물리 인터페이스 | (제어 외 메타) |
| `GeoShape.feature` (GeoJSON) | 장치 또는 채널의 polygon/line/point | **azimuth** (외향 법선) + **area** (면적) 산출 |
| `GeoShape.device_id` + `channel_id` | 장치-도형 결합 | actuator → shape 역참조 |
| `GeoFacility.shape_uuid` | 시설 외곽 polygon 링크 | 시설 둘레·체적·envelope 면적 |
| `GeoFacility.actuators` | {slot → output_uuid} | 시설별 등록된 액추에이터 dict |
| `GeoFacility.envelope/curtain` | 외피·커튼 enabled/material | u_eff·transmittance·차광/단열 효과 |
| `GeoFacility.computed` | `floor_m2, envelope_m2, vent_open_m2, volume_m3, u_effective, ach_natural, heating_kw, cooling_kw` | 알고리즘 가중치 캐시 |

→ 추가 데이터 모델링은 기본 불필요. 기존 컬럼·JSON에서 산출.

### 14.3 ActuatorProfile GIS 메타 (구현됨)

`types.py::ActuatorProfile`에 추가된 필드:

```python
geo_facility_id: Optional[str]  = None   # GeoFacility.unique_id
slot_key:        Optional[str]  = None   # 'outer_side_vent_motor' 등
azimuth_deg:     Optional[float]= None   # 외향 법선 (0=N, 90=E, 180=S, 270=W)
area_m2:         Optional[float]= None   # 개구부 유효 면적
capacity_meta:   Dict[str, float]= field(default_factory=dict)
                                         # u_effective, volume_m3, envelope_m2 캐시
```

profile-builder 우선순위:
1. **장치별 GeoShape**가 있으면 거기서 azimuth·area 직접 산출 (가장 정확)
2. 없으면 `GeoFacility.shape_uuid`의 외곽 polygon에서 변별 azimuth + 균등 분할 area 추정
3. 둘 다 없으면 `azimuth_deg=None, area_m2=None` (알고리즘이 fallback 정량값 사용)

### 14.4 Polygon → azimuth/area 산출 규칙

`aot_flask/geo/facility_calc.py::_ring_area_m2`가 이미 면적을 산출. azimuth는 동일 헬퍼 모듈에 추가:

```python
def edge_outward_azimuth(coords, edge_index) -> float:
    """polygon 외곽 변의 외향 법선 방위각 (0–360°, deg).

    polygon이 시계 외향(CCW)이면 변에서 외향은 변의 우측 90° 회전.
    GeoJSON 표준은 outer ring CCW, hole CW.
    """
```

장치 단위:
- **point Shape** (e.g. fan): location만 보유, azimuth=None
- **line Shape** (e.g. 측창 1개의 line strip): line의 외향 법선 = azimuth, length·height → area
- **polygon Shape** (e.g. 천창 면): polygon area = area, 평균 외향 법선 = azimuth

시설 외곽 fallback:
- `outer_side_vent_motor` 1개 등록인데 GeoShape 없음 → 시설 polygon 4면 모두 매칭하는 가상 4-개구부로 분할 처리(같은 Output UUID 공유). 풍향 알고리즘은 풍하측만 활성. 향후 사용자가 면별 등록하면 정확도 ↑.

### 14.5 SafetyPreGate 풍향 차등 폐쇄

기존(`safety_gates.py::SafetyPreGate.evaluate`):
```python
if ext.get('wind', 0.0) >= cfg.wind_threshold:
    triggered = True   # 모든 개구부 강제 폐쇄
```

v2 확장:
```python
def evaluate(env, profiles, last_uid):
    wind_speed = env['external'].get('wind', 0.0)
    wind_dir   = env['external'].get('wind_dir')   # None이면 종전과 동일
    forced_close = set()

    if wind_speed >= cfg.wind_threshold:
        for p in profiles:
            if p.kind != 'opening':
                continue
            if p.azimuth_deg is None or wind_dir is None:
                forced_close.add(p.actuator_id)    # 정보 부족 → 보수적 폐쇄
                continue
            angle_diff = abs(((wind_dir - p.azimuth_deg + 180) % 360) - 180)
            if angle_diff < cfg.windward_arc_deg:  # default 60°
                forced_close.add(p.actuator_id)    # windward만 폐쇄

    # leeward 개구부는 정상 운용
    return GateResult(forced_close=forced_close, ...)
```

`PreGateConfig`에 추가:
```python
windward_arc_deg: float = 60.0   # ±60° = 풍상측으로 간주
```

### 14.6 Coordinator/Effect — 면적·u_eff 가중

`effect_functions.py`의 `K_OPENING_T` 등 정적 상수를 면적·단열성능 결합 동적 K로 확장:

```python
def opening_temp_effect(env, cmd_pct, profile=None):
    delta = env.get('T_ext', 0.0) - env.get('T_int', 0.0)
    if abs(delta) < 0.5:
        return EffectResult('0', 0.0)

    # 면적 가중 (없으면 1.0)
    area_factor = 1.0
    if profile and profile.area_m2:
        ref_area = 10.0   # 참조 면적 m²
        area_factor = profile.area_m2 / ref_area

    # 단열성능 가중 (없으면 1.0)
    u_factor = 1.0
    u_eff = (profile.capacity_meta.get('u_effective')
             if profile and profile.capacity_meta else None)
    if u_eff and u_eff > 0:
        u_factor = u_eff / 4.0   # 4 W/m²K 기준

    direction = '↑' if delta > 0 else '↓'
    magnitude = (abs(delta) * (cmd_pct/100.0) * K_OPENING_T
                 * _wind_boost(env) * area_factor * u_factor)
    return EffectResult(direction, magnitude)
```

`coordinator.py`는 이미 EffectFn을 호출 중이므로 시그니처에 `profile` 추가만 하면 됨.

### 14.7 R1/R2/R3와 facility의 결합

| Layer | 기능 | facility 결합 |
|---|---|---|
| L1 (`goal.py`) | EnvTarget 생성 (R1/R2/R3) | 작물 프로필 + crop stage. facility 영향 없음 |
| L2 (`situation.py`) | VPD 분해, 제한 인자 | facility.computed.heating_kw로 계절적 가중 (선택) |
| L3 (`coordinator.py`) | 명령 산출 | **여기서 GIS 결합 핵심**. profile.area_m2/azimuth로 effect·cost 계산 |
| Pre-Gate | 안전 차단 | **풍향 차등 폐쇄** (§14.5) |
| Post-Gate | 명령 후 검증 | 변화 없음 |

### 14.8 구현 단계 (Phase 매핑)

| 단계 | 내용 | 위치 |
|---|---|---|
| **G1** | `geo` 헬퍼: `polygon_outward_azimuth`, `shape_to_azimuth_area(shape, channel)` | `aot/aot_flask/geo/facility_geo_helpers.py` (신규) |
| **G2** | `_reload_profiles`에서 GeoShape per-device 우선 → fallback facility polygon | `env_coordinator.py::_reload_profiles` (이미 facility hybrid 단계 완료, GeoShape 분기만 추가) |
| **G3** | `EffectFn` 시그니처에 `profile` 추가 + 가중 산식 적용 | `effect_functions.py`, `coordinator.py` |
| **G4** | `SafetyPreGate.evaluate` per-opening 풍향 차등 | `safety_gates.py` |
| **G5** | `lighting` kind을 `ACTUATOR_KINDS`에 정식 등록 + R2 EnvTarget·limiting_factor에 light 분기 | `types.py`, `goal.py`, `situation.py` |

### 14.9 향후 다듬어갈 항목 (이번 범위 밖)

다음은 v2 본문에 포함하지 않고 별도 phase로 분리:

- 면별 측창 사용자 등록 UI (현재는 enabled 토글 1개)
- bay_index 기반 zone 제어
- `circulation_fan/exhaust_fan` 슬롯의 ACH 직접 모델링
- 커튼 coverage(roof/side/envelope) 분리 운용
- 센서-구역 결합 (sensor zone wiring) — `routes_geo.py` Phase 2 항목과 연계
- 모바일 designer UI 조정
- end_behavior가 facility-derived profile에 어떻게 매핑되는지 (env_actuator action에는 있고 facility 슬롯에는 없는 비대칭)

각 항목은 별도 PRD/issue로 진행하며, 본 문서는 G1~G5 완료 후 v3로 흡수.

---

## 15. 제외 사항 (이 설계 범위 밖)

- **양액·관수 EC/pH 제어**: 본 시스템은 환경(공기·온도·습도)만 다룸
- **카메라·이미지 분석**: 식물 상태 직접 관측은 별도 시스템

(v1까지는 LED 보광도 제외 항목이었으나, v2부터 `lighting` actuator로 정식 포함되어 본 항목에서 제외 — §14.7, §14.8.G5)

---

## 16. 변경 이력

| 버전 | 일자 | 변경 |
|------|------|------|
| v0 | 2026-05-08 | 초안 작성 (대화 합의 반영) |
| v1 | 2026-05-08 | 리뷰 보강:<br>· P7(안정성)·P8(안전 분리) 원칙 추가<br>· §3.2 단위 규약 R1 명문화<br>· §3.4 `cost_fn` 함수형, §3.5 머지 규칙 R2, §3.6 수동 락<br>· §4 슬루·히스테리시스·anti-windup·`compute_cmd` 명세<br>· §5.4 VPD 분해 정책 (옵션 A 채택)<br>· §6 안전 Pre/Post-Gate 분리 명시<br>· §8 외부 컨텍스트 fallback 정책<br>· §9 사이클 주기 결정 규칙<br>· §11 Phase A 보강, §12 결정표 갱신 |
| v2 | 2026-05-08 | Facility/GIS 통합 + R1/R2/R3 명문화:<br>· P9(GIS-aware), P10(목표 역할 분리) 원칙 추가<br>· §1.1 L6 (시설 형상 미인식) 추가<br>· §5.3 EnvTarget에 R1/R2/R3 변수 역할표<br>· §14 Facility & GIS Integration 신설 (`Output.lat/lon` + `GeoShape.feature` 활용, 풍향 차등 폐쇄, 면적·u_eff 가중)<br>· `ActuatorProfile`에 `geo_facility_id, slot_key, azimuth_deg, area_m2, capacity_meta` 필드<br>· `lighting` kind을 정식 actuator로 포함<br>· §14.9에 향후 다듬어갈 항목 분리 |

---

## 부록 A — 용어

| 용어 | 정의 |
|------|------|
| `EnvTarget` | L1 출력. 환경 변수별 목표·허용범위·우선순위 묶음 |
| `SituationReport` | L2 출력. 현재 상태·편차·운전모드 묶음 |
| `ActuatorProfile` | Output 플러그인이 자기를 노출하는 메타데이터 |
| `EffectFn` | 외부 조건과 명령%를 입력받아 효과 방향·크기를 반환하는 함수 |
| `CostFn` | 외부 조건과 명령%를 입력받아 비용을 반환하는 함수 (낮을수록 우선) |
| `live_effect` | 현재 상황에 `EffectFn`을 적용한 결과 (방향·크기) |
| `safe_default` | 명령 없을 때 액추에이터의 안전 위치 |
| `ManualLockState` | 수동 조작 시 조율자 차단 상태 |
| `Pre-Gate` | L1 진입 전 안전 검사. 발동 시 L1~L3 우회 |
| `Post-Gate` | L3 결과를 L4에 전달 전 안전·정합성 검사 |
| `R1` | EffectFn magnitude 단위 규약 (native/cycle) |
| `R2` | 캘리브레이션 머지 규칙 (DB > 모듈 fallback) |

## 부록 B — 참고 문헌·근거

- Farquhar, G.D., et al. (1980) — C3 광합성 모델
- Stanghellini, C. (1987) — 온실 환경 동적 모델
- AoT 기존 문서: `opening_control_design.md` (단일 액추에이터 PID 기반 — 본 문서로 대체)

## 부록 C — 리뷰 대응 매트릭스 (v0 → v1)

| 리뷰 지적 | 대응 위치 |
|----------|----------|
| §3.1 안정성 메커니즘 부재 | §0 P7, §4.1, §4.2, §4.3 |
| §3.2 accumulated 단위 일관성 | §3.2 R1, §4.3 (모두 native) |
| §3.3 VPD 처리 모호 | §5.4 옵션 A 채택 |
| §3.4 cost_index 표현력 | §3.4 `CostFn` 함수형 |
| §3.5 안전 모드 우선순위 | §0 P8, §6 게이트 분리 |
| §3.6 외부 컨텍스트 SPOF | §8.2 fallback 정책 |
| §3.7 D1 머지 규칙 | §3.5 R2 |
| §3.8 통신 실패·타임아웃 | §6.3 |
| §3.8 수동 오버라이드 락 | §3.6 `ManualLockState` |
| §3.8 사이클 주기 | §9 결정 규칙 |
| §3.9 wind 미활용 | §3.3 `opening_temp_effect` 풍속 가속 |
| §3.9 Phase C C1 자동 발견 | §11 Phase C C1 보강 |
