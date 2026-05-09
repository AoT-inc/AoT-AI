# 시설 개구부 제어 Function 설계 문서

- **대상**: 측창(side window), 천창(roof vent), 커튼(curtain), 보온덮개(thermal screen)
- **작성일**: 2026-05-08
- **상태**: 설계 합의 단계 (구현 착수 승인 대기)
- **저장 위치**: `aot/functions/opening_brain.py`, `aot/functions/opening_device.py`, `aot/functions/utils/opening_pid.py`

---

## 1. 요구사항 요약

| # | 요구 |
|---|---|
| R1 | 모든 요소가 다 있을 수는 없음 (선택 등록) |
| R2 | 모든 요소가 하나만 있지는 않음 — 추가 가능 |
| R3 | 열림·닫힘 두 방향 output 등록 |
| R4 | 작동 시간 측정 → 열림 정도(%) 표시·제어 |
| R5 | 열림 정도에 따라 면적 계산 |
| R6 | 열림 정도를 결정하는 제어 로직 |
| R7 | 외부·내부 환경 데이터 수집 및 판단 |
| R8 | 목표 구체성 — 온도/습도/VPD 등 동적 setpoint, 하드코딩 지양 |
| R9 | 안전 — 환경 조건별 대상 장치를 달리 작동(예: 강우 시 창호만, 일사 시 커튼) |
| R10 | 시설 위치·방위 고려 (창 위치, 풍향 등에 따른 개별 조절) |
| R11 | 기존 function 활용 (PID, Trigger, VPD 등) |
| R12 | 하드웨어 보호 — 미세 조작 어려움, 짧은 잦은 운전이 수명 단축 |
| R13 | 긴급 작동 외에는 사용자가 지정한 주기마다 연산·운전 |
| R14 | 대시보드 시각화 — 별도 위젯 또는 facility 위젯 활용 |
| R15 | PID는 사용자 별도 설정 없음 — 내부 임베디드 또는 기존 로직 경유 |

---

## 2. 시스템 구조

### 2.1 계층

| 계층 | 신규/기존 | 책임 |
|---|---|---|
| **L1 Brain** | 신규 Function | 환경 판단, 안전 평가, 다목표 PID, 분배(distribute), 각 L2에 target_pct publish |
| **L2 Device** | 신규 Function (개구부당 1개) | 위치(%) 추정, 목표 추종, 인터록·하드웨어 보호, 면적 계산, output ON/OFF |
| **L3 IO** | 기존 AoT 자원 재사용 | Output 채널, Input/Function 측정값 (별도 개발 없음) |

L1·L2 모두 AoT의 **CustomController(Function) 메커니즘**으로 구현. 별도 데몬·스케줄러 불필요. AoT가 `loop()`을 시스템 `sample_rate` 주기로 호출.

### 2.2 데이터 흐름

```
[Sensors / Functions]              [기존 AoT IO]
        ↓ get_last_measurement()
   ┌─────────────────────┐
   │  L1 Brain Function  │
   │  - safety eval      │
   │  - PID(임베디드)    │
   │  - aggregate        │
   │  - distribute       │
   └──────────┬──────────┘
              ↓ publish target_pct (자기 measurement 채널에 write)
              ↓
   ┌──────────┴──────────┐    ┌──────────────────┐
   │  L2 Device #1       │    │  L2 Device #N    │  ← 개구부마다 1개
   │  - read target_pct  │    │  ...             │
   │  - integrate pos    │    │                  │
   │  - interlock/dwell  │    │                  │
   │  - calc area        │    │                  │
   └──────────┬──────────┘    └──────────────────┘
              ↓ output_on/off()
        [Open Relay] [Close Relay]
```

### 2.3 신규 파일 목록

```
aot/functions/
  opening_brain.py              # L1
  opening_device.py             # L2
  utils/opening_pid.py          # 경량 PID 유틸
aot/widgets/
  AoT_facility.py               # (수정) opening overlay 모드 추가
```

DB 모델 변경 없음. 기존 `CustomController.custom_options` (JSON)에 모든 설정 수용.

---

## 3. 기존 AoT 자원 매핑

### 3.1 Output 제어
- 클래스: `aot/outputs/base_output.py` `AbstractOutput`
- 호출: `controller_output.py` `OutputController.output_on_off(output_id, state, output_channel, output_type, amount, ...)`
- 식별자: `Output.unique_id` (UUID, 36자 문자열) + `output_channel` (정수)

### 3.2 측정값 조회
- 함수: `aot/utils/influx.py` `get_last_measurement(device_id, measurement_id, max_age=None)` → `[timestamp, value]`
- `AbstractBaseController` 정적 메서드로도 노출 (Function이 `self.get_last_measurement(...)`로 사용)
- Input/Function 모두 동일 인터페이스 — L1은 PV·setpoint 모두 measurement 참조로 받음

### 3.3 Function 메커니즘
- 기본 클래스: `aot/functions/base_function.py` `AbstractFunction`
- 실행: `controller_function.py`가 시스템 `sample_rate`(전역 `Misc.sample_rate_controller_function`) 주기로 `loop()` 호출
- 자체 주기: function 내부에서 `self.timer_loop`와 `update_period`(custom_options) 조합으로 운영 — `bang_bang.py` 패턴 답습

### 3.4 위젯
- `widget_function_status.py` — 즉시 활용 가능 (텍스트/숫자)
- `AoT_facility.py` — 시설 도면 위에 개구부 오버레이로 확장 (권장)

---

## 4. L2 Device Function 설계

### 4.1 책임
- 작동 시간 적분으로 `position_pct` 추정 (R4)
- `target_pct` 추종 (publish된 값 또는 외부 입력)
- 인터록(open/close 동시 통전 금지), 데드타임, dwell 등 하드웨어 보호 (R12)
- type별 면적 계산 (R5)
- (선택) 리미트 스위치로 위치 보정

### 4.2 custom_options 스키마

```yaml
# 식별 / 분류
type: side_window | roof_vent | curtain | thermal_screen
instance_label: "south_window_1"

# Output 바인딩 (R3)
output_open_id:        "<Output.unique_id>"
output_open_channel:   0
output_close_id:       "<Output.unique_id>"
output_close_channel:  0

# 이동 시간 (R4) — 양방향 비대칭 허용
travel_open_sec:   45.0
travel_close_sec:  50.0

# 면적 (R5)
max_area_m2:       12.5
geometry_model:    linear | sin_hinge   # 면적 함수 선택
geometry_params:   {}                    # 모델별 파라미터 (예: hinge length)

# (선택) 리미트 스위치
limit_open_input:  { device_id: "...", measurement_id: "..." }
limit_close_input: { device_id: "...", measurement_id: "..." }

# 방위 (R10) — L1 분배에 사용
orientation_deg:   180        # 0=북, 90=동, 180=남, 270=서
facade_label:      "south"

# 하드웨어 보호 (R12)
hardware_protection:
  min_pulse_sec:              4.0    # 최소 통전 시간
  deadband_pct:               5.0    # |target-position| < N% 면 idle
  min_dwell_sec:              30.0   # 정지 후 다음 기동까지 휴지
  reversal_extra_dwell_sec:   60.0   # 방향 전환 시 추가 휴지
  max_actuations_per_day:     200    # 일일 기동 횟수 상한

# Target 입력 — L1 publish 채널 참조
target_input:
  device_id:      "<L1 unique_id>"
  measurement_id: "<L1 measurement: target for this device>"

# 주기
update_period: 1.0    # 자체 loop 주기 (초). 위치 적분 정확도 위해 짧게.
```

### 4.3 측정값 노출 (DeviceMeasurements 채널)

| ch | 의미 | 단위 |
|---|---|---|
| 0 | position_pct | % (0–100) |
| 1 | open_area_m2 | m² |
| 2 | target_pct | % |
| 3 | state | 0=idle, 1=opening, 2=closing, 3=fault |
| 4 | actuation_count_today | count |

### 4.4 위치 추정 (R4)

```
Δt_open  = 통전 누적 시간 (열림 방향, 이번 주기)
Δt_close = 통전 누적 시간 (닫힘 방향)

position_pct(t) = clamp(
    last_position
    + (Δt_open  / travel_open_sec ) × 100
    - (Δt_close / travel_close_sec) × 100,
    0, 100
)
```

- 0% 또는 100% 도달 시 리미트 스위치(있으면)로 재캘리브레이션
- 주기적 full-close 보정 (선택, 운영 정책으로 노출)

### 4.5 면적 계산 (R5)

- `linear`: `area = position_pct/100 × max_area_m2` (커튼/보온덮개/슬라이딩 측창)
- `sin_hinge`: `area = sin(θ_max × position_pct/100) × max_area_m2` (힌지식 천창·측창)
- 향후 type/모델 추가 가능 (lookup 테이블 등)

### 4.6 상태 머신

```
IDLE ──set_target──▶ MOVE_DECISION
                     ├─ within deadband      → IDLE
                     ├─ dwell not satisfied  → IDLE (대기)
                     ├─ open needed          → OPENING
                     └─ close needed         → CLOSING
OPENING ──reached / timeout / safety──▶ COASTING(데드타임) ──▶ IDLE
CLOSING ──reached / timeout / safety──▶ COASTING(데드타임) ──▶ IDLE
ANY ──fault detected──▶ FAULT (수동 reset 또는 알림)
```

- open/close 동시 통전 절대 금지 (인터록 코드 보장)
- 방향 전환 시 `reversal_extra_dwell_sec` 강제

---

## 5. L1 Brain Function 설계

### 5.1 책임
- 환경 데이터 수집 (R7)
- 안전 이벤트 평가 — 대상 장치별 override (R9)
- 다목표 PID 연산 — 임베디드 (R8, R15)
- 다목표 합산(aggregate)
- 방위·풍향·constraint 기반 분배(distribute) (R10)
- 각 L2에 target_pct publish

### 5.2 이중 주기 (R13)

```
loop()  (AoT가 sample_rate 주기로 호출, 보통 1~수 초)
  ├─ FAST PATH (매 tick):
  │     evaluate_safety()
  │     └─ 위반 → 즉시 override publish, return
  │
  └─ SLOW PATH (update_period마다):
        collect_environment()
        for target in control_targets:
            u = pid_compute(target, env)
        combined = aggregate(u_list)
        per_device = distribute(combined, env, devices)
        publish_targets(per_device)
```

기본값: `update_period = 60` 초. 시설 응답 속도에 따라 30~300초 권장.

### 5.3 custom_options 스키마

```yaml
update_period: 60.0
safety_release_hold_sec: 90.0     # 안전 해제 직후 정상 복귀 지연

# 등록된 L2 목록 (R1, R2, R10)
devices:
  - device_function_id: "<L2 unique_id>"
    type: roof_vent
    orientation_deg: 180
    priority_order: 1                # 개방 우선순위 (낮을수록 먼저)
    target_measurement_channel: 0    # L1이 publish할 자기 채널
    constraints:
      max_pct_when_rain:               { threshold: 0.1, value: 0 }
      max_pct_when_wind_speed_gt:      { threshold: 8.0, value: 30 }
      windward_max_pct:                20    # 풍상측일 때 제한
  - device_function_id: "<L2 unique_id>"
    type: side_window
    orientation_deg: 90
    priority_order: 2
    target_measurement_channel: 1
    constraints: { ... }
  - device_function_id: "<L2 unique_id>"
    type: curtain
    priority_order: 3
    target_measurement_channel: 2

# 환경 센서 (R7) — 모두 measurement 참조
sensors:
  outdoor_temp:    { device_id, measurement_id }
  indoor_temp:     { device_id, measurement_id }
  outdoor_humidity:{ device_id, measurement_id }
  indoor_humidity: { device_id, measurement_id }
  wind_speed:      { device_id, measurement_id }
  wind_direction:  { device_id, measurement_id }   # degrees, 0=북
  rain:            { device_id, measurement_id }
  solar:           { device_id, measurement_id }

# 다목표 제어 (R8, R15)
control_targets:
  - name: temperature
    process_var:      { device_id, measurement_id }   # Input 또는 Function 출력
    setpoint_source:
      type: static                                     # static | measurement | method
      value: 25.0
    deadband: 0.5
    weight: 1.0
    gains: { kp: 8.0, ki: 0.1, kd: 0.0 }              # 생략 시 type 기본값
    output_action: lower_when_pv_high                  # 또는 raise_when_pv_high
  - name: vpd
    process_var:    { device_id: "<VPD Function>", measurement_id: "ch0" }
    setpoint_source:
      type: measurement
      ref: { device_id, measurement_id }               # 동적 setpoint
    deadband: 0.1
    weight: 0.6
    output_action: lower_when_pv_high

aggregate_mode: weighted_avg | max_of                  # 다목표 합산 방식

# 안전 이벤트 (R9)
safety:
  events:
    - id: heavy_rain
      when: { metric: rain, op: ">", value: 0.1 }
      hysteresis: { metric: rain, op: "<", value: 0.0 }
      targets: [side_window, roof_vent]
      action: { mode: force_close, override_pct: 0 }
      notify: "<notification_id>"

    - id: high_solar
      when: { metric: solar, op: ">", value: 800 }
      hysteresis: { metric: solar, op: "<", value: 600 }
      targets: [curtain]
      action: { mode: force_open, override_pct: 100 }

    - id: heat_emergency
      when: { metric: indoor_temp, op: ">", value: 35.0 }
      hysteresis: { metric: indoor_temp, op: "<", value: 33.0 }
      targets: [side_window, roof_vent, curtain]
      action: { mode: force_open, override_pct: 100 }

    - id: cold_protect
      when: { metric: indoor_temp, op: "<", value: 5.0 }
      hysteresis: { metric: indoor_temp, op: ">", value: 7.0 }
      targets: [thermal_screen]
      action: { mode: force_close, override_pct: 100 }

    - id: stuck_device
      when: { metric: position_no_change_sec, op: ">", value: 120 }
      targets: [self]
      action: { mode: alert_only }
      notify: "<notification_id>"
```

#### 안전 평가 규칙

- `targets`는 type 또는 instance label 리스트
- 동시 다중 위반 시 mode 우선순위: **force_close > force_open > alert_only**
- 히스테리시스 필수 (재투입 진동 방지)
- 안전 발동 중 PID 출력 무시, 해제 후 `safety_release_hold_sec` 동안 hold 후 정상 복귀

### 5.4 PID 임베디드 (R15)

`aot/functions/utils/opening_pid.py`:

```
class LightPID:
    def __init__(self, kp, ki, kd, out_limits=(0, 100), integral_limits=...):
        ...
    def compute(self, pv, sp, dt) -> float:
        # 표준 PID + 적분 항 anti-windup
        ...
    def reset(self):
        ...
```

- type별 합리적 기본 게인 상수 보유
- control_target 단위 오버라이드만 허용
- 사용자 별도 PID Controller 등록 불필요 (R15 충족)
- 향후 필요 시 기존 `controller_pid.py`의 PID 클래스를 import해 옵션 B로 전환 가능

### 5.5 다목표 합산 (aggregate)

```
u_list = [pid_compute(t, env) for t in control_targets]   # 각 0..100

if aggregate_mode == "weighted_avg":
    combined = Σ (u_i × w_i) / Σ w_i
elif aggregate_mode == "max_of":
    combined = max(u_i)        # 가장 다급한 목표 우선

combined = clamp(combined, 0, 100)
combined = lpf(combined, alpha)             # 저역통과
combined = quantize(combined, step=5)       # 5% 단위 양자화
combined = rate_limit(combined, prev, max_per_period=15)
```

### 5.6 분배 (distribute) — 방위·풍향 (R10)

#### 5.6.1 device 그룹 분리

같은 `combined_target_pct` 1개 값으로 모든 type을 처리할 수 없음(환기/차광/단열은 *효과 차원*이 다름). control_target 별로 어떤 device 그룹에 작용할지 명시:

```yaml
control_targets:
  - name: temperature
    actuator_group: ventilation     # side_window + roof_vent
  - name: humidity
    actuator_group: ventilation
  - name: light
    actuator_group: shading         # curtain
  - name: night_thermal
    actuator_group: insulation      # thermal_screen
```

→ 각 그룹마다 **독립적으로 aggregate + distribute** 수행. 그룹 간 간섭 없음.

#### 5.6.2 그룹별 알고리즘

**환기 그룹 (창류) — 면적 합산식**

```
combined_pct = aggregate(u_list, mode)   # weighted_avg | max_of

if mode == "weighted_avg":
    # 면적 비례 분배 — 천창 → 측창 우선순위 따름
    total_demand_area = combined_pct / 100 × Σ device.max_area_m2
    for dev in sorted(group, key=priority_order):
        cap_pct = apply_caps(dev, env)              # safety override + constraints + windward
        remaining_area = max(0, total_demand_area - allocated_area)
        dev.target_pct = min(cap_pct, remaining_area / dev.max_area_m2 × 100)
        allocated_area += dev.target_pct / 100 × dev.max_area_m2

elif mode == "max_of":
    # 동일 개방률 일괄 적용 (가장 다급한 목표 기준)
    for dev in group:
        cap_pct = apply_caps(dev, env)
        dev.target_pct = min(combined_pct, cap_pct)
```

**차광/단열 그룹 (커튼·보온덮개) — 단일 변수 추적**

```
# 면적 합산 의미 없음 — 각 device가 동일 target 추종
for dev in group:
    cap_pct = apply_caps(dev, env)              # windward 무시 (옥내)
    dev.target_pct = min(combined_pct, cap_pct)
```

#### 5.6.3 `apply_caps` 공통

```
def apply_caps(dev, env):
    cap = 100
    if dev in safety_overrides:
        return safety_overrides[dev]            # 안전이 절대 우선
    cap = min(cap, eval_constraints(dev, env))  # rain/wind threshold
    if dev.group == "ventilation" and is_windward(dev.orientation_deg, env.wind_direction):
        cap = min(cap, dev.constraints.windward_max_pct)
    return cap
```

#### 5.6.4 `is_windward` 정의 (정식)

- `orientation_deg`: **창의 외향 법선 방향** (창 바깥 면이 향하는 방위, 0=북, 90=동).
- `wind_direction`: **바람이 불어오는 방향** (기상학 표준, 0=북풍).
- 풍상측 판정: `angular_diff(orientation_deg, wind_direction) ≤ 90°` 이면 windward.
  - 예: 남향 창(180°) + 남풍(180°) → diff=0° → windward (창이 풍상)
  - 예: 남향 창(180°) + 북풍(0°)   → diff=180° → leeward
- `angular_diff` = `min(|a-b|, 360-|a-b|)`.

#### 5.6.5 옥내 장치 처리

`actuator_group ∈ {shading, insulation}`인 device는 분배에서 **windward 판정 스킵**. `orientation_deg` 미설정 시 자동으로 차광/단열 그룹 취급.

### 5.6bis 수동 Override 우선순위 (정식)

L2의 `target_pct` 결정에는 4가지 입력 경로가 있음. **우선순위 (높음 → 낮음)**:

| 순위 | 출처 | 메커니즘 | 만료 |
|---|---|---|---|
| 1 | L2 자체 인터록·보호 | 상태머신 (deadband, dwell, fault) | 영구 |
| 2 | L1 Safety override | 안전 이벤트 발동 | hysteresis 해제 + safety_release_hold_sec |
| 3 | MCP `set_position` 수동 명령 | `manual_override_until` 타임스탬프 | TTL 만료 (기본 600초) |
| 4 | L1 정상 PID `target_input` | measurement 구독 | 항시 (다음 SLOW PATH 갱신) |

**구현**:
- L2의 `loop()`에서 매 tick 우선순위 평가 후 effective_target 결정.
- MCP `set_position` 호출 시 `self.manual_override_until = time.time() + ttl`.
- `manual_override_until > now`인 동안 L1의 `target_input` 무시.
- TTL 만료 후 자동으로 L1 추적 복귀 (bumpless: 적분기 reset).

### 5.7 측정값 노출 (DeviceMeasurements 채널)

AoT의 DeviceMeasurements 채널은 0부터 순차 정수. 아래는 N개 device + M개 control_target 가정한 **순차 할당 규칙**:

| ch 범위 | 의미 |
|---|---|
| `0 .. N-1` | 각 device의 target_pct (devices 배열 순서) |
| `N` | combined_target_pct |
| `N+1` | active_safety_event_code (0=없음, 1=heavy_rain, 2=high_solar, …) |
| `N+2 .. N+1+M` | 각 control_target의 error (control_targets 배열 순서) |
| `N+2+M` | schedule_state (0=active_all, 1=partial_rest, 2=full_rest) — §14 |
| `N+3+M` | next_window_start_unixtime — §14 |

채널 매핑 표는 L1 인스턴스 등록 시 생성·로깅. 사용자/위젯/Conditional은 측정값 이름(`combined_target_pct` 등)으로 조회. ch 번호는 내부 구현 디테일.

→ Conditional Controller가 `active_safety_event_code` 채널을 감시해 알림(Slack/Email/MQTT) 라우팅 가능. 기존 Notification 메커니즘 그대로 활용.

---

## 6. 대시보드 위젯 (R14)

| 옵션 | 신규 여부 | 적합도 |
|---|---|---|
| **A. `widget_function_status` 활용** | 기존 | ✅ 즉시 사용 |
| **B. `AoT_facility.py` 확장** | 기존 확장 | ✅✅ 권장 |
| **C. 신규 `widget_opening.py`** | 신규 (선택) | 보조 — 단일 개구부 헬스 모니터링 |

**권장 단계**:
1. 단기: 기존 `widget_function_status`로 L2 측정값 노출 — 추가 코드 0
2. 중기: `AoT_facility.py`에 "opening overlay" 모드 추가 — 시설 도면 위에 개구부 마커, position_pct 색상·애니메이션, 풍향 화살표
3. 장기(선택): 단일 개구부 상세 위젯 — 일일 기동 횟수, 누적 운전시간, fault 로그

---

## 7. 등록·운영 흐름

1. 사용자가 Output 2개(open/close)를 기존 UI로 등록
2. (선택) 리미트 스위치 Input 등록
3. **L2 Function**(opening_device) 추가 — 개구부 1개당 1개. custom_options에 type, output 바인딩, 이동시간, 면적, 방위, 보호 파라미터 입력
4. 시설에 N개 개구부 → L2 N개
5. **L1 Function**(opening_brain) 1개 추가 — `devices`에 L2 목록, `sensors`에 환경 measurement, `control_targets`, `safety` 구성
6. 활성화 → 시스템 sample_rate 주기로 loop 동작 시작
7. 대시보드에서 facility 위젯으로 시각 확인

요구사항 R1·R2 충족 — 개구부 추가/삭제는 L2 Function 추가/삭제 + L1의 devices 리스트 갱신만으로 완결.

---

## 8. 안전·신뢰성 보장

| 항목 | 보장 메커니즘 |
|---|---|
| 동시 통전 방지 | L2 상태 머신 인터록 |
| 모터 보호 | 방향 전환 시 데드타임 + reversal dwell |
| 잦은 기동 방지 | min_pulse, deadband, min_dwell, rate_limit, LPF, quantize |
| PID 발진 억제 | 60초 SLOW PATH + LPF + deadband |
| 강우/강풍/혹한혹서 | safety events (즉시 override, FAST PATH) |
| 통신 단절 | (선택) measurement max_age 초과 감지 → 안전 위치 |
| 알림 | 측정값 채널 publish → 기존 Conditional/Notification에 위임 |
| 진단 | stuck 감지(position_no_change_sec), daily actuation count |

---

## 9. 요구사항 ↔ 설계 매핑

| 요구 | 설계 항목 |
|---|---|
| R1, R2 | L2 인스턴스 N개, L1 `devices` 동적 리스트 |
| R3 | L2 `output_open_id` / `output_close_id` |
| R4 | L2 시간 적분 위치 추정, channel 0 publish |
| R5 | L2 `geometry_model`, `calc_open_area()`, channel 1 publish |
| R6 | L1 `control_targets` + LightPID + aggregate + distribute |
| R7 | L1 `sensors` + `collect_environment()` |
| R8 | `setpoint_source` (static/measurement/method) — method 모드는 사용자가 method 페이지에서 생성한 시간기반 곡선을 드롭다운으로 선택, `load_method_handler` + `calculate_setpoint` 활용. PV는 measurement 참조 |
| R9 | `safety.events`의 `targets` 필드로 장치별 가변 |
| R10 | `orientation_deg` + `is_windward` + `windward_max_pct` + `priority_order` |
| R11 | LightPID 임베디드 + 기존 `controller_pid.py`로 폴백 옵션, Conditional/Notification 위임, VPD Function을 PV로 사용 |
| R12 | L2 `hardware_protection` 6종 + L1 LPF·quantize·rate_limit |
| R13 | FAST/SLOW PATH 분리, `update_period` 사용자 옵션 |
| R14 | `widget_function_status` + `AoT_facility` 확장 |
| R15 | LightPID 임베디드, 사용자 PID Controller 별도 등록 불필요 |

---

## 10. 구현 단계 (제안)

| 단계 | 산출물 |
|---|---|
| 1 | `utils/opening_pid.py` LightPID 클래스 |
| 2 | `opening_device.py` L2 — 등록·output 바인딩·시간 적분·면적·인터록 |
| 3 | L2 단독 검증 — 수동 target_pct로 추종 동작 확인 |
| 4 | `opening_brain.py` L1 — 환경수집·PID·aggregate·distribute |
| 5 | 안전 이벤트 평가·override |
| 6 | `AoT_facility.py` opening overlay 확장 |
| 7 | 통합 검증 — 실제 시설 또는 시뮬레이션 |

---

## 11. AI MCP 서버 연동

### 11.1 기존 메커니즘 (조사 결과)

AoT MCP는 두 경로로 도구를 노출:

- **Path A — VIRTUAL_TOOLS** (`aot/ai/agents/mcp_aot.py`, lines 44-171): 명시 등록된 가상 도구 배열. 신규 도구는 수동 추가 필요.
- **Path B — AoTNativeToolEngine** (`aot/ai/services/aot_native_tool_engine.py`, lines 27-43): Input/Output 테이블을 스캔해 동적 스키마 생성. **Function은 자동 노출 안 됨.**

도구 실행 디스패치: `aot/aot_mcp_server.py` `_dispatch_virtual_tool()` (lines 124-174)의 dict에 매핑 추가 필요.

에이전트 접근 제어: `AgentMCPAccess` 테이블, `allowed_tools=NULL`이면 모든 도구 자동 허용 (`scripts/seed_agent_mcp_access.py`).

### 11.2 신규 Function의 MCP 노출 — 작업 항목

**자동 통합되는 부분**: 에이전트 접근 제어 (NULL 정책).
**수동 필요한 부분**: 도구 스키마 등록 + 디스패치 매핑 + 서비스 구현.

#### 11.2.1 VIRTUAL_TOOLS 추가 (3개 도구)

`aot/ai/agents/mcp_aot.py`의 `VIRTUAL_TOOLS` 배열에 추가:

```python
{
    "tool_name": "control_opening",
    "description": "Control facility opening (side window / roof vent / curtain / "
                   "thermal screen) by setting target position or commanding "
                   "open/close/stop. Wraps L2 Device Function.",
    "input_schema": {
        "type": "object",
        "properties": {
            "device_function_id": {"type": "string", "description": "L2 Function unique_id"},
            "action": {"type": "string", "enum": ["set_position", "open", "close", "stop"]},
            "position_pct": {"type": "number", "minimum": 0, "maximum": 100}
        },
        "required": ["device_function_id", "action"]
    }
},
{
    "tool_name": "get_opening_status",
    "description": "Read current state of an opening: position_pct, target_pct, "
                   "open_area_m2, state, daily actuation count.",
    "input_schema": {
        "type": "object",
        "properties": { "device_function_id": {"type": "string"} },
        "required": ["device_function_id"]
    }
},
{
    "tool_name": "list_openings",
    "description": "List all registered opening devices (L2) and their parent brain (L1) "
                   "with type, facility, current state.",
    "input_schema": {
        "type": "object",
        "properties": { "facility_uuid": {"type": "string", "description": "Optional filter"} }
    }
}
```

`set_position`은 L1 우회(수동 override)이며, L1이 활성 상태면 다음 SLOW PATH에서 덮어씀 — `manual_override_until` 같은 임시 잠금 옵션 도입 검토.

#### 11.2.2 디스패치 매핑

`aot/aot_mcp_server.py` `_dispatch_virtual_tool()`에:

```python
"control_opening":    lambda a: OpeningControlService.control(...),
"get_opening_status": lambda a: OpeningControlService.get_status(...),
"list_openings":      lambda a: OpeningControlService.list_openings(...),
```

#### 11.2.3 신규 서비스

`aot/ai/services/opening_control_service.py` (신규):
- `control(device_function_id, action, position_pct)` — L2 Function의 custom_options 또는 in-memory state에 명령 주입. AoT의 Function instance 메서드 호출 메커니즘 활용 (controller_function.py의 `run_function`에 메서드 노출).
- `get_status(device_function_id)` — `get_last_measurement`로 ch0..ch4 조회해 dict 반환.
- `list_openings(facility_uuid=None)` — Function 테이블에서 `function_type='opening_device'` 또는 `'opening_brain'` 필터.

### 11.3 안전 — AI 호출 제약

- AI가 안전 이벤트 진행 중 `control_opening` 호출 시 거부 (or 경고 + 무시)
- `set_position`의 manual override 지속시간 상한 (예: 600초)
- 호출 로그 기록 (audit trail)

---

## 12. Geo/Facility 페이지 연동

### 12.1 기존 메커니즘 (조사 결과)

| 자원 | 위치 | 역할 |
|---|---|---|
| `GeoFacility` 모델 | `aot/databases/models/geo.py` | 시설 메타데이터 — geometry_3d, envelope (side_vent/roof_vent 정보 포함), actuators (output 매핑), bays |
| `GeoShape` | 동상 | 지도/평면도 위 도형. `type` 필드로 분류: `facility`, `facility_bay`, `aot_device` 등 |
| `Function` 모델 | `aot/databases/models/function.py` | **이미** `latitude`, `longitude`, `marker_icon`, `marker_color`, `marker_size`, `map_overlay_id` 필드 보유 |
| `facility_io.py` | `aot/aot_flask/geo/` | facility 저장/조회. envelope의 side_vent/roof_vent 필드 처리 (calc만, 시각화 미구현) |
| `facility_calc.py` | 동상 (lines 265-279) | 개구부 면적 계산 로직 **이미 존재** — `vent_height_m`, `vent_length_ratio` 등 |
| `geo_overlays.py` | 동상 | GeoShape CRUD (`save_overlays`, `get_overlays`) — type별 디스패치 |
| `AoT_facility.py` 위젯 | `aot/widgets/` | Three.js 3D 시설 렌더링. envelope/actuators/geometry_3d 사용 |
| `/api/aot/facility/<uuid>/runtime` | `routes_geo.py` (lines 1121-1172) | actuator_states, outdoor, indoor 등 실시간 데이터 노출 |

**핵심 발견**: 
- Function 모델에 위치·마커 필드가 이미 있어 L2를 facility 도면에 marker로 자연 배치 가능
- envelope의 vent 필드는 **계산용**으로만 존재, GeoShape 오버레이로 시각화 안 됨
- facility_calc.py의 개구부 면적 계산이 L2의 `calc_open_area()`와 **중복** — 통합 또는 위임 필요

### 12.2 신규 Function의 facility 연동 — 작업 항목

#### 12.2.1 L2 Function의 공간 배치

**자동 통합**: Function 테이블의 `latitude`, `longitude`, `map_overlay_id`, `marker_*` 필드 활용 — 별도 모델 변경 없이 L2가 시설 도면에 배치 가능.

**custom_options 스키마 보완** (Section 4.2에 추가):
```yaml
facility_link:
  facility_uuid: "<GeoFacility.unique_id>"      # 어느 시설에 속하는가
  bay_index: 2                                  # (선택) 어느 베이
  vent_role: side_left | side_right | roof_north | roof_south | curtain | thermal
  geometry_ref:                                  # 도면 위 위치
    type: line | point
    coordinates: [[lng1,lat1], [lng2,lat2]]      # LineString이면 개구부 경계
```

#### 12.2.2 GeoShape 'facility_opening' 타입 신규

`geo_overlays.py`의 type 디스패치에 `'facility_opening'` 추가. L2 등록 시 자동으로 GeoShape 생성:

```python
# opening_device.py 의 initialize() 또는 별도 hook
GeoShape(
    type='facility_opening',
    geo_id=facility.geo_id,
    parent_id=facility_outer_shape_id,
    device_id=l2_function.unique_id,        # Function unique_id
    feature={
        'type': 'Feature',
        'geometry': {'type': 'LineString', 'coordinates': [...]},
        'properties': {
            'aot_type': 'facility_opening',
            'opening_type': 'side_window',     # type from L2 custom_options
            'function_uuid': l2_function.unique_id,
            'orientation_deg': 90,
            'max_area_m2': 12.5
        }
    }
)
```

→ `geo_overlays.save_overlays()`/`get_overlays()`가 일관 처리.

#### 12.2.3 facility_calc.py 통합

기존 `facility_calc.py`(lines 265-279)의 개구부 면적 산출은 **정적 추정**(envelope 플래그 + 가정 상수). L2의 `position_pct` 기반 동적 면적이 도입되면 중복.

**처리 방향**:
- `facility_calc.py`에 분기 추가: facility에 L2 Function이 등록돼 있으면 그쪽의 `open_area_m2` 측정값(ch1) 합산, 없으면 기존 정적 가정 fallback.
- 통합 함수: `aot/aot_flask/geo/facility_calc.py`에 `dynamic_vent_area(facility_uuid)` 신규.

#### 12.2.4 runtime API 확장

`/api/aot/facility/<uuid>/runtime` (routes_geo.py lines 1121-1172)에 `openings` 섹션 추가:

```python
runtime['openings'] = [
    {
        'function_uuid': l2.unique_id,
        'opening_type': l2_opts['type'],
        'role': l2_opts['facility_link']['vent_role'],
        'position_pct': last_measurement(l2.unique_id, 'ch0')[1],
        'target_pct':   last_measurement(l2.unique_id, 'ch2')[1],
        'open_area_m2': last_measurement(l2.unique_id, 'ch1')[1],
        'state':        last_measurement(l2.unique_id, 'ch3')[1],
        'safety_active': bool_from_l1(facility_uuid),
    }
    for l2 in find_l2_functions_for(facility_uuid)
]
```

→ 위젯/AI/외부 통합 모두 단일 엔드포인트 활용.

#### 12.2.5 AoT_facility 위젯 확장

`AoT_facility.py` + 프론트 (Three.js):
- runtime API의 `openings` 사용
- 각 opening을 LineString 좌표 기반 3D Plane으로 렌더 (열린 각도 = position_pct 매핑)
- 색상: idle=회색, opening=주황, closing=청록, fault=적색, safety_active=점멸
- 클릭 시 모달 → MCP의 `control_opening` 또는 직접 API 호출 (수동 override)
- 풍향 화살표 추가 (L1의 wind_direction sensor)

### 12.3 동기화 흐름 정리

```
[L2 등록]
    ├─→ Function 테이블 (lat/lng, marker)
    ├─→ GeoShape (type='facility_opening', LineString)
    └─→ facility.envelope.vent_functions[role] = l2.unique_id  (역참조)

[L2 loop()]
    └─→ measurements(ch0..4) publish

[runtime API]
    └─→ openings[] 배열 조립 (L2 measurements 합산)

[facility 위젯]
    └─→ runtime API 폴링 → 3D 시각화

[AI MCP control_opening]
    └─→ OpeningControlService → L2 manual override / target publish
```

### 12.4 작업 단계 추가 (Section 10 보완)

| 단계 | 산출물 | 영향 파일 |
|---|---|---|
| 8 | `OpeningControlService` 구현 | `aot/ai/services/opening_control_service.py` (신규) |
| 9 | MCP VIRTUAL_TOOLS 3개 + 디스패치 | `aot/ai/agents/mcp_aot.py`, `aot/aot_mcp_server.py` |
| 10 | GeoShape `facility_opening` 타입 처리 | `aot/aot_flask/geo/geo_overlays.py` |
| 11 | L2 등록 시 GeoShape 자동 생성 hook | `aot/functions/opening_device.py` (initialize) |
| 12 | runtime API openings 섹션 추가 | `aot/aot_flask/routes_geo.py` |
| 13 | facility_calc.py dynamic_vent_area | `aot/aot_flask/geo/facility_calc.py` |
| 14 | AoT_facility 위젯 3D 오버레이 | `aot/widgets/AoT_facility.py` + 프론트 JS |

---

## 13. Method 연동 — 시간 기반 동적 Setpoint

### 13.1 기존 Method 시스템 (조사 결과)

| 자원 | 위치 | 역할 |
|---|---|---|
| `Method`, `MethodData` 모델 | `aot/databases/models/method.py` | 시간 기반 setpoint 곡선 정의 (DB 저장) |
| `AbstractMethod` + 서브클래스 | `aot/utils/method.py` | `Date`, `Daily`, `DailySine`, `DailyBezier`, `Duration`, `Cascade` 등 |
| `load_method_handler(method_id, logger)` | `aot/utils/method.py` (line 447) | method_id로 핸들러 로드 |
| `handler.calculate_setpoint(now, method_start_time=None)` | `aot/utils/method.py` (line 57) | **표준 진입점** — 현재 시각의 setpoint 반환 |
| 기존 사용처 | `controller_pid.py:332` `setup_method`, `controller_trigger.py:281` `start_method` | PID·Trigger의 setpoint를 method로 추적 |
| UI 페이지 | `aot/aot_flask/routes_method.py`, `forms_method.py` | 사용자가 method 생성·편집 |

핵심: **`load_method_handler` + `calculate_setpoint`** 두 줄로 시간 기반 setpoint 사용 가능. 기존 PID/Trigger와 동일한 패턴.

### 13.2 L1 Brain의 Method 활용

`control_targets.setpoint_source`에 method 모드 추가:

```yaml
control_targets:
  - name: temperature
    process_var: { device_id, measurement_id }
    setpoint_source:
      type: method                              # static | measurement | method
      method_id: "<Method.unique_id>"           # 사용자가 method 페이지에서 생성한 곡선
      method_start_time: null                   # null=실행 시작 시각, 또는 ISO datetime
    deadband: 0.5
    weight: 1.0
```

**구현**:
```python
# opening_brain.py 의 read_setpoint(target)
if target.setpoint_source.type == "method":
    if not hasattr(target, "_method_handler"):
        target._method_handler = load_method_handler(
            target.setpoint_source.method_id, self.logger)
        target._method_start = target.setpoint_source.method_start_time or time.time()
    sp, ended = target._method_handler.calculate_setpoint(
        time.time(), method_start_time=target._method_start)
    if ended:
        # Duration method 종료 시 fallback 정책 (마지막 값 유지 또는 정지)
        sp = target._last_valid_sp
    target._last_valid_sp = sp
    return sp
elif target.setpoint_source.type == "measurement":
    last = self.get_last_measurement(...ref...)
    return last[1] if last else None
elif target.setpoint_source.type == "static":
    return target.setpoint_source.value
```

### 13.3 다중 method — 목표마다 독립적

각 control_target이 독립된 method_id를 가짐. 예:
- 온도: `temperature_daily_curve` (DailyBezier)
- VPD: `vpd_dli_response` (Daily)
- 야간 보온: `night_thermal_curve` (Date)

→ 작물 생장 단계별·일조 패턴별 곡선을 사용자가 method 페이지에서 자유 구성, L1은 `method_id`만 참조.

### 13.4 UI — 드롭다운 통합

L1 Function의 custom_options 폼에서 `setpoint_source.method_id`를 **Method 목록 드롭다운**으로 노출. 기존 PID Controller가 method를 선택하는 UI 패턴(`forms_pid.py`) 답습.

`aot/functions/opening_brain.py`의 `custom_options_dict`에:
```python
{
    'id': 'setpoint_method',
    'type': 'select',
    'default_value': '',
    'options_select': [('Method', 'method')],   # 기존 표준 옵션
    'name': '온도 Setpoint Method',
    'phrase': '시간 기반 setpoint 곡선 선택 (없으면 static value 사용)'
}
```

### 13.5 Method 종료 처리

`Duration` 계열 method는 `ended=True`를 반환하며 종료. L1의 fallback 정책:
- **last_value_hold** (기본): 마지막 유효 setpoint 유지
- **fallback_static**: `setpoint_source.fallback_value`로 회귀
- **disable_target**: 해당 control_target 비활성화

`setpoint_source.on_method_end` 옵션으로 노출.

### 13.6 요구사항 매핑 갱신

§9 요구사항 매핑의 R8 행을 다음으로 갱신:

| R8 | `setpoint_source` 3종(static/measurement/method) — **method 모드는 사용자가 method 페이지에서 생성한 시간기반 곡선을 드롭다운으로 선택**, `load_method_handler` + `calculate_setpoint` 활용 |

### 13.7 작업 단계 추가 (Section 10·12.4 보완)

| 단계 | 산출물 | 영향 파일 |
|---|---|---|
| 15 | L1 `read_setpoint()`에 method 분기 구현 | `aot/functions/opening_brain.py` |
| 16 | custom_options에 `setpoint_method` 셀렉트 옵션 추가 | 동상 |
| 17 | method 종료 fallback 정책 처리 | 동상 |

신규 파일 없음. 기존 `aot/utils/method.py`의 표준 API만 호출.

---

## 14. 작동 시간 설정 — Duration & 운휴 윈도우

### 14.1 기존 AoT 패턴 (조사 결과)

`aot/databases/models/function.py` `Trigger` 모델 (lines 118-183)에 이미 다음 필드 보유:

| 필드 | 의미 |
|---|---|
| `output_duration` | 출력 통전 지속 시간 (초) — Trigger Duration |
| `output_duty_cycle` | PWM duty cycle |
| `timer_start_time` / `timer_end_time` | 타이머 시작·종료 시각 (`HH:MM`) |
| `rise_or_set` + `latitude`/`longitude` + `time_offset_minutes` | 일출/일몰 기준 시각 |
| `period` | 반복 주기 |
| `method_start_time` / `method_end_time` | Method 적용 윈도우 |

→ **신규 필드 발명 불필요**. 동일한 명칭·시맨틱을 차용해 일관성 유지.

### 14.2 L2 Device — 통전 Duration

L2의 하드웨어 보호와 결합:
- 기존 `min_pulse_sec`은 *최소* 통전 — 그대로 유지
- 신규 `max_pulse_sec` 추가 — 한 번의 명령으로 통전할 수 있는 *최대* 시간 (안전 상한, travel_*_sec와 별개)
- 위치 추적 실패·리미트 미작동 시 폭주 방지

```yaml
hardware_protection:
  min_pulse_sec:    4.0
  max_pulse_sec:   90.0           # ← 신규. travel_*_sec × 1.5 정도 권장
  ...
```

### 14.3 L1 Brain — 운휴 윈도우 (Operating Hours)

**선택적** 시간 기반 게이트. 사용 안 하면 24시간 가동.

```yaml
operating_schedule:                # (선택) 전체 또는 device별
  enabled: true                    # false 시 항상 가동
  windows:                         # 가동 허용 시간대 (여러 개 가능)
    - { start: "06:00", end: "20:00" }
  pauses:                          # 명시적 휴식 시간 (windows 안에서)
    - { start: "12:00", end: "13:00", reason: "midday_rest" }
  rest_mode: hold | safe_close     # 휴식 시 동작
                                   #   hold: 마지막 위치 유지
                                   #   safe_close: 닫힘
  sunrise_offset_min: null         # (선택) 일출 기준 +N분에 가동 시작
  sunset_offset_min:  null         # 일몰 기준 ±N분에 가동 종료
  device_overrides:                # type/instance별 별도 스케줄
    thermal_screen:
      enabled: true
      windows: [{ start: "18:00", end: "06:00" }]   # 야간 전용
      rest_mode: hold
```

**평가 우선순위** (높은→낮은):
1. **Safety override** (§5.3) — 항상 최우선, 시간 무시
2. **Operating schedule** — 휴식 중이면 SLOW PATH 명령 발행 안 함
3. **Manual override** (MCP control_opening) — 휴식 중에도 허용 가능 옵션
4. **정상 PID 제어**

### 14.4 L1 loop() 흐름 — 게이트 추가

```python
def loop(self):
    # FAST PATH (매 tick) — safety
    if self.evaluate_safety_and_override():
        return

    # SLOW PATH (update_period마다)
    if self.timer_loop > time.time(): return
    self._advance_timer()

    env = self.collect_environment()

    # ── 시간 게이트 평가 (신규) ──
    schedule_state = self.evaluate_operating_schedule(now=time.time())
    # schedule_state.active_devices: set of device_ids 허용된 장치
    # schedule_state.resting_devices: dict of {device_id: rest_mode}

    # 정상 제어 — active_devices만
    targets = self.compute_targets(env, devices=schedule_state.active_devices)

    # 휴식 장치 — rest_mode에 따라 처리
    for dev_id, mode in schedule_state.resting_devices.items():
        if mode == "safe_close":
            targets[dev_id] = 0
        elif mode == "hold":
            continue        # 명령 미발행 → L2가 마지막 target 유지

    self.publish_targets(targets)
```

### 14.5 일출/일몰 기반 (Trigger 패턴 차용)

기존 `Trigger.rise_or_set` + `latitude`/`longitude` + `time_offset_minutes` 메커니즘을 재사용. 보온덮개의 "일몰 30분 후 닫힘 → 일출 30분 전 열림" 같은 운영을 명시적 시각 입력 없이 자동 계산.

L1의 `operating_schedule.sunrise_offset_min` / `sunset_offset_min` 설정 시 매일 새로 계산해 `windows`에 반영. 시설의 `latitude`/`longitude`는 GeoFacility에서 자동 상속.

### 14.6 측정값 노출 — 운영 상태

L1 measurements에 채널 추가:
| ch | 의미 |
|---|---|
| 130 | schedule_state (0=active_all, 1=partial_rest, 2=full_rest) |
| 131 | next_window_start_unixtime |

→ Conditional이 채널 130을 감시해 운영자에게 휴식 진입/해제 알림 가능.

### 14.7 요구사항 매핑 갱신

| R12-b | 작동 시간 옵션 | L2 `max_pulse_sec` (안전 상한) + L1 `operating_schedule.windows`/`pauses`/`rest_mode` (선택적). 야간 운휴·점심 휴식 등 명시적 시간대 설정. 일출/일몰 오프셋(`sunrise_offset_min`)으로 자동 계산 가능. **사용 안 하면 24시간 가동**. |

### 14.8 작업 단계 추가

| 단계 | 산출물 | 영향 파일 |
|---|---|---|
| 18 | L2 `max_pulse_sec` 처리 | `aot/functions/opening_device.py` |
| 19 | L1 `evaluate_operating_schedule()` | `aot/functions/opening_brain.py` |
| 20 | 일출/일몰 계산 (기존 sunrise/sunset 유틸 재사용) | 동상 |
| 21 | UI 옵션 노출 (선택적 활성화 플래그) | `custom_options_dict` |

신규 파일 없음. 기존 Trigger의 시간 처리 유틸 재사용.

---

## 15. 미결 사항 / 구현 시 반영 (제어론 보강)

### 15.1 운영 정책 미결
- 다목표 `aggregate_mode` 기본값 (`weighted_avg` vs `max_of`) — 현장 검증 후 결정
- `geometry_model` 추가 type 필요 여부 (현재 linear, sin_hinge)
- 통신 단절 fail-safe 정책 (hold vs safe_close) 의 기본값
- Output 고착 감지 (명령 발행 vs 위치 변화 mismatch) 임계값
- audit log 메커니즘 (어떤 명령이 언제 발행됐는지 기록 형식)

### 15.2 제어론 보강 — 구현 시 반드시 반영

검토 결과 일반 제어론 표준 대비 다음 항목이 누락 또는 약함. 구현 단계에서 반영 필요.

| # | 항목 | 반영 위치 | 비고 |
|---|---|---|---|
| **C1** | **외기온 Feedforward** — 외란을 오차로만 보지 말고 직접 보상. 그린하우스 제어 표준. `control_targets[i].feedforward: { ref, gain }` 옵션 추가 | `opening_brain.py` PID compute | 옵션, 미설정 시 비활성 |
| **C2** | **Derivative-on-PV** — D항을 setpoint가 아닌 PV에만 적용. setpoint 변화 시 derivative kick 방지 | `utils/opening_pid.py` LightPID | 표준 모범, 기본 ON |
| **C3** | **Anti-windup back-calculation** — 단순 clamp가 아닌 saturation 시 적분기 역계산 또는 conditional integration | `utils/opening_pid.py` | 표준 |
| **C4** | **Bumpless Transfer** — Safety 해제 / Method 전환 / Manual TTL 만료 시 적분기 PV로 재초기화 | `opening_brain.py` | `safety_release_hold_sec`만으론 부족 |
| **C5** | **Setpoint Slew Rate** — Method 곡선이 급변해도 PID에는 ramp된 setpoint 입력. 분당 ±N(°C/%RH/kPa) 상한 | `opening_brain.py` read_setpoint() 직후 | 옵션 `setpoint_slew_per_min` |
| **C6** | **Dead-time 인지** — 시설 시정수 + 액추에이터 이동 시간을 사용자 옵션으로 받고 PID 게인 자동 조정 또는 Smith Predictor 옵션 | `custom_options` `system_dynamics: { tau_sec, deadtime_sec }` | 향후 옵션, 미설정 시 단순 PID |
| **C7** | **샘플링 주기 가이드** — `update_period`는 시정수의 1/10 이하 권고. UI에서 경고 메시지 | UI 폼 | 검증 로직 |
| **C8** | **Drift 자동 보정** — limit switch 없는 경우 N일 또는 M회 동작마다 자동 full-close 시퀀스 | `opening_device.py` | 옵션 `drift_recalibration: { every_days, every_actuations }` |
| **C9** | **Auto-calibration 모드** — 초기 등록 시 사용자가 트리거하면 full-open → full-close 측정해 `travel_*_sec` 자동 채움 | `opening_device.py` 메서드 노출 | MCP에도 노출 |
| **C10** | **Sensor staleness 의무화** — 모든 measurement 참조에 `max_age_sec` 기본값 적용. 초과 시 fail-safe | `opening_brain.py` collect_environment() | 기본 60초 (env), 30초 (PV) |
| **C11** | **이중 Cascade 명시화** — 외루프(L1, 환경 → target_pct) + 내루프(L2, target_pct → 위치)를 cascade로 문서화. 추후 내루프에 별도 PID 도입 시 자연 확장 | 문서 §2.1 보완 가능 | 현재 구조가 이미 cascade에 부합 |
| **C12** | **MIMO 한계 명시** — §5.6에서 actuator_group 분리로 일부 해소. 그러나 그룹 내부(예: 천창과 측창의 환기 효율 차이)는 동일 효과로 가정. 추후 베이별 풍속·내부 온도 분포 도입 시 재설계 | 문서 명시 완료 | — |

### 15.3 운영 가드 (FMEA 보강)

| 시나리오 | 감지 | 대응 |
|---|---|---|
| Output 고착 (명령 ON인데 position 변화 없음) | `position_no_change_sec > min(travel_*_sec) × 1.5` | `state=fault`, 알림, manual reset 대기 |
| Sensor 단절 (PV staleness) | `max_age_sec` 초과 | 해당 control_target 비활성, fallback 정책 |
| L1↔L2 통신 단절 (target_pct staleness) | L2의 target_input max_age 초과 | L2 자체 fail-safe (hold 또는 safe_close) |
| 일일 actuation 상한 초과 | ch4 카운트 비교 | 알림, 그날 추가 동작 거부 (옵션) |
| Position 누적 드리프트 | 자동 보정 실패 시 | 알림 + 보정 모드 강제 진입 |

