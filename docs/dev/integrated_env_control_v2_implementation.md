# 통합 환경 제어 v2 — Facility/GIS 통합 구현 작업서

> **상태**: 작업 (Phase G 진행)
> **작성일**: 2026-05-08
> **선행 문서**: [`integrated_env_control_design.md`](./integrated_env_control_design.md) §14
> **범위**: 설계 문서 §14.8의 G1–G5 단계 구현
> **범위 밖**: §14.9 향후 다듬어갈 항목 (bay_index, fan ACH, 커튼 coverage, sensor zone wiring, designer UI 등)

---

## 0. 목적

설계 문서 v2의 §14 (Facility & GIS Integration)을 실제 코드에 반영한다. 결과적으로:

- 장치별 `Output.lat/lon` + `GeoShape.feature` → ActuatorProfile의 `azimuth_deg`, `area_m2`로 자동 산출
- `SafetyPreGate`가 풍향과 개구부 방향을 비교해 **windward만 강제 폐쇄** (leeward 환기 유지)
- 효과 산식이 면적·단열성능을 반영
- `lighting` actuator가 정식 kind로 등록되고 R2(Light secondary primary, optional) 경로로 동작

---

## 1. 사전 상태 (Pre-requisites — 이미 완료)

| 항목 | 상태 | 위치 |
|---|---|---|
| `ActuatorProfile`에 GIS 필드 추가 | ✅ | [types.py](../../aot/functions/utils/env_control/types.py) |
| env_coordinator hybrid 모드 (facility 옵션 + manual action) | ✅ | [env_coordinator.py](../../aot/functions/custom_functions/env_coordinator.py) `_reload_profiles` |
| `wind_dir` 입력 옵션 + `_build_gate_env`에 전달 | ✅ | [env_coordinator.py](../../aot/functions/custom_functions/env_coordinator.py) |
| `lighting` UI/effect_model | ✅ (env_actuator UI, effect_functions) — 단 `ACTUATOR_KINDS` 미등록 (G5에서 처리) |
| `Custom_Options.html`의 `select_device + ['GeoFacility']` | ✅ | [Custom_Options.html](../../aot/aot_flask/templates/pages/form_options/Custom_Options.html) |

---

## 2. 작업 단계

### G1 — geo 헬퍼: polygon → azimuth/area 산출

**목표**: GeoJSON feature(point/line/polygon)에서 외향 법선 azimuth와 면적을 산출하는 헬퍼 함수.

**파일**: `aot/aot_flask/geo/facility_geo_helpers.py` (신규)

**API**:
```python
def shape_azimuth_area(feature: dict) -> tuple[float | None, float | None]:
    """GeoJSON feature → (azimuth_deg, area_m2).

    point   → (None, None)
    line    → (외향 법선 deg, length_m × default_height_m)
    polygon → (평균 외향 법선 deg, ring area)
    """

def edge_outward_azimuth(coords, edge_index=0) -> float:
    """polygon 외곽 변의 외향 법선 방위각 (0–360°, deg).
    GeoJSON CCW 외곽 가정 → 변에서 우측 90° 회전 = 외향.
    """

def polygon_avg_outward_azimuth(coords) -> float | None:
    """polygon 모든 외곽 변의 외향 azimuth 평균 (length-weighted).
    면적이 큰 polygon은 일반적으로 면 단위 azimuth가 의미 약함 — 호출측 판단."""
```

기존 [facility_calc.py](../../aot/aot_flask/geo/facility_calc.py)의 `_ring_area_m2`, `_ring_perimeter_m`를 재사용.

**수용 기준**:
- 단위 테스트: 정사각형 polygon (북쪽 변) → azimuth ≈ 0° (북향), 면적 정확
- 단위 테스트: 동서 line → azimuth ≈ 0° 또는 180° (남향/북향)
- 점 GeoJSON → (None, None)

---

### G2 — profile builder가 GeoShape per-device 우선

**목표**: `_reload_profiles`에서 액추에이터별 GeoShape를 먼저 조회해 azimuth/area를 채운다. GeoShape 없으면 facility 외곽 polygon에서 fallback.

**파일**: `aot/functions/custom_functions/env_coordinator.py::_reload_profiles`

**변경**:
```python
# 현재: facility-driven profile에서 azimuth_deg=None, area_m2=area_per_vent
# 변경: 우선순위 1) device GeoShape → 2) facility shape fallback

from aot.databases.models import GeoShape

# facility_meta 산출 시:
shape = GeoShape.query.filter_by(device_id=output_uuid).first()
if shape and shape.feature:
    azimuth_deg, area_m2 = shape_azimuth_area(shape.feature)
else:
    azimuth_deg = None
    # facility shape fallback for area
    area_m2 = area_per_vent  # 기존 균등 분할 유지
```

**수용 기준**:
- GeoShape에 polygon 등록된 액추에이터의 `ActuatorProfile.azimuth_deg`가 None이 아님
- `area_m2`가 GeoShape feature에서 산출됨
- GeoShape 미등록 액추에이터는 기존 fallback(area 균등 분할)으로 동작 — 회귀 없음
- 로그 라인에 GIS 보유 비율 표시: `gis_resolved=N/M`

---

### G3 — EffectFn 면적·u_eff 가중

**목표**: `EffectFn` 시그니처에 `profile` 인자 추가. 면적·단열성능에 따라 효과 크기 동적 산출.

**파일**:
- `aot/functions/utils/env_control/types.py` — `EffectFn` 시그니처 변경
- `aot/functions/utils/env_control/effect_functions.py` — 모든 `*_effect` 함수에 `profile` 추가
- `aot/functions/utils/env_control/coordinator.py` — EffectFn 호출처에 profile 전달

**시그니처 변경**:
```python
# 기존
EffectFn = Callable[[EnvContext, float], EffectResult]

# 신규
EffectFn = Callable[[EnvContext, float, Optional[ActuatorProfile]], EffectResult]
```

**산식 (opening 예시)**:
```python
def opening_temp_effect(env, cmd_pct, profile=None):
    delta = env.get('T_ext', 0.0) - env.get('T_int', 0.0)
    if abs(delta) < 0.5:
        return EffectResult('0', 0.0)
    direction = '↑' if delta > 0 else '↓'

    area_factor = 1.0
    u_factor = 1.0
    if profile:
        if profile.area_m2:
            area_factor = profile.area_m2 / REFERENCE_OPENING_AREA_M2  # default 10.0
        u_eff = profile.capacity_meta.get('u_effective')
        if u_eff and u_eff > 0:
            u_factor = REFERENCE_U_EFF / u_eff   # 단열 좋을수록 효과 작음

    magnitude = (abs(delta) * (cmd_pct/100.0) * K_OPENING_T
                 * _wind_boost(env) * area_factor * u_factor)
    return EffectResult(direction, magnitude)
```

상수: `REFERENCE_OPENING_AREA_M2 = 10.0`, `REFERENCE_U_EFF = 4.0` (모듈 상수, 추후 캘리브레이션 대상)

**호환성**: `profile=None` 기본값 → 기존 호출 코드 동작 유지.

**수용 기준**:
- 단위 테스트: 동일 cmd_pct에서 area_m2=20 vs 5인 두 profile이 다른 magnitude 산출
- 단위 테스트: u_eff=2 (좋은 단열) vs 6 (나쁜 단열)에서 다른 magnitude
- profile=None일 때 v1과 동일 결과 (회귀 방지)

---

### G4 — SafetyPreGate 풍향 차등 폐쇄

**목표**: 강풍시 모든 개구부가 아닌 **windward 개구부만** 강제 폐쇄.

**파일**: `aot/functions/utils/env_control/safety_gates.py`

**변경**:
```python
@dataclass
class PreGateConfig:
    wind_threshold:    float = 12.0
    rain_threshold:    float = 0.5
    heat_ext_threshold: float = 45.0
    cold_ext_threshold: float = -5.0
    windward_arc_deg:   float = 60.0   # NEW: ±60° = windward 간주
```

`SafetyPreGate.evaluate(env, profiles, last_uid)` 반환에 `forced_close: set[str]` (개구부별 강제 폐쇄 집합) 추가. 기존 booleon `triggered`는 "전역 차단"용으로 유지하되 풍향 단독 발동시는 미발동, 대신 forced_close만 채움.

```python
def evaluate(self, env, profiles, last_uid):
    ext = env.get('external', {})
    wind_speed = ext.get('wind', 0.0)
    wind_dir   = ext.get('wind_dir')
    forced_close = set()
    reasons = []

    # 강풍: per-opening 차등
    if wind_speed >= self.config.wind_threshold:
        for p in profiles:
            if p.kind != 'opening':
                continue
            if p.azimuth_deg is None or wind_dir is None:
                forced_close.add(p.actuator_id)
                continue
            angle_diff = abs(((wind_dir - p.azimuth_deg + 180) % 360) - 180)
            if angle_diff < self.config.windward_arc_deg:
                forced_close.add(p.actuator_id)
        if forced_close:
            reasons.append(f'wind_windward({len(forced_close)})')

    # 강우/폭염/혹한: 기존 전역 차단 유지
    # ... (기존 로직)

    return GateResult(triggered=bool(reasons and 'rain' in reasons),
                      forced_close=forced_close,
                      reasons=reasons)
```

**호환성**: `wind_dir=None` 또는 `azimuth_deg=None` 시 → 보수적으로 폐쇄 (v1과 동일 동작 보장).

**수용 기준**:
- 단위 테스트: wind_speed=15, wind_dir=0(N), 두 profile (azimuth=0=N, 180=S) → N만 forced_close
- 단위 테스트: wind_dir=None → 모두 forced_close (보수)
- 단위 테스트: 비-opening profile은 forced_close에서 제외

---

### G5 — `lighting` 정식 actuator 등록 + R2 경로

**목표**: `lighting` kind을 `ACTUATOR_KINDS`에 추가하고 EnvTarget/limiting_factor에 light 분기를 마련. R2 경로(보광 등록 시에만 활성).

**파일**:
- `types.py::ACTUATOR_KINDS` — `'lighting'` 추가
- `goal.py::build_env_target` — light target 산출 (등록된 `lighting` actuator가 있을 때만)
- `situation.py` — limiting_factor에 PAR 입력 처리 (이미 `light_response` 자리표시자 있음, §5.6)

**수용 기준**:
- `'lighting' in ACTUATOR_KINDS == True`
- env_coordinator에 lighting actuator 등록 + sensor_light 매핑 시 EnvTarget에 `'light'` 키 등장
- 미등록 시 `'light'` 키 없음 (현재와 동일)

---

## 3. 진행 순서 + 검증 게이트

| 순서 | 작업 | 검증 방법 |
|---|---|---|
| 1 | G1 헬퍼 구현 + 단위 테스트 | `pytest aot/tests/test_facility_geo_helpers.py` |
| 2 | G2 profile builder GeoShape 우선 | 로그에 `gis_resolved=N/M` 표시, 기존 facility-only 테스트 회귀 없음 |
| 3 | G3 EffectFn 시그니처 + 가중 산식 | 단위 테스트 (다른 면적/u_eff에서 다른 결과), 회귀 테스트 (profile=None) |
| 4 | G4 SafetyPreGate 풍향 분기 | 단위 테스트 (windward/leeward 케이스), 기존 SafetyPreGate 테스트 회귀 없음 |
| 5 | G5 lighting 정식 등록 | env_coordinator 모달에서 lighting 동작, EnvTarget 노출 확인 |
| 6 | 통합: env_coordinator 한 사이클 실행 → decision_log 확인 | facility 등록된 시설에서 풍향 변화 시 forced_close 로그 |

각 단계 완료 후 서버 재시작 + UI 회귀 점검.

---

## 4. 위험 / 롤백

| 위험 | 영향 | 완화 |
|---|---|---|
| `EffectFn` 시그니처 변경 | 외부 코드가 EffectFn 직접 호출시 깨짐 | `profile=None` 기본값으로 후방 호환 |
| `SafetyPreGate.GateResult` 필드 추가 | 호출자가 dict-likeness에 의존시 | `dataclass` 추가 필드는 기본값으로 안전 |
| Polygon 외향 법선 오류 (CW/CCW 혼용) | 풍하측을 풍상측으로 잘못 판정 | 단위 테스트 + 양방향 토글 옵션 (v3) |
| reference 상수(`REFERENCE_OPENING_AREA_M2` 등)의 보정 | 계수 실측 불일치 | 모듈 상수로 노출 → 추후 캘리브레이션 (`apply_calibration`)로 오버라이드 |

각 단계 변경은 git 단위로 분리해 단계별 롤백 가능.

---

## 5. 진행 상태

| 단계 | 상태 | 비고 |
|---|---|---|
| G1 | ✅ 완료 | `facility_geo_helpers.py` + 19개 단위 테스트 PASS |
| G2 | ✅ 완료 | `_reload_profiles`에서 GeoShape per-device 우선 조회, fallback facility 면적, 로그 `gis_resolved=N/M` |
| G3 | ✅ 완료 | EffectFn 시그니처 `(env, pct, profile=None)`. opening/shade에 면적 가중. 개구부 u_eff 우회 (물리적). 9개 단위 테스트 PASS |
| G4 | ✅ 완료 | `windward_arc_deg=60°` config + `GateResult.partial`. 강풍 단독 + per-opening 정보 시 windward만 폐쇄. 8개 단위 테스트 PASS |
| G5 | ✅ 완료 | `lighting`을 `ACTUATOR_KINDS` 정식 등록. `build_env_target`에 `Light_target` 인자 (R2 — 보광 등록 시만 활성). 5개 단위 테스트 PASS |
| B2-fix | ✅ 완료 (2026-05-18) | `get_facility_integration` 페이로드 일관성 강화 — fitting-only 등록 누락 해소, vent 이중 회계 차단, GeoShape bulk fetch, groups 재조회 제거 |

**전체**: 41/41 단위 테스트 PASS. `test_facility_calc.py` 회귀 없음. 서버 재시작 정상.

### B2-fix — Integration 페이로드 사용 패치 (2026-05-18)

B2 통합(`get_facility_integration` 공유 헬퍼) 도입 후 발견된 4개 데이터 정합/성능 이슈를 일괄 처리.

| 이슈 | 위치 | 수정 |
|---|---|---|
| A. fitting-only Output 등록 누락 | `_profile_loader_mixin.py` `if not kind: continue` | `facility_integration.py` 에 `_FITTING_KIND_TO_ACTUATOR_KIND` 매핑 추가 — `window/side_window/door → opening`, `curtain → curtain` 자동 추론. fan 계열은 모호하여 None 유지 (slot 또는 명시 `actuator_kind` 필요) |
| B. vent 면적 이중 회계 | 동 파일, vent fallback 분기 | `vent_open_source == 'fittings'` 모드에서는 균등 분할 fallback 비활성화. envelope-only 모드에서만 `vent_open_m2 / len(vent_slots)` 적용 |
| C. GeoShape N+1 쿼리 | actuator 루프 내 `GeoShape.query.filter_by(device_id=...).first()` | 루프 진입 전 `output_uuids_all` 로 한 번에 `in_(...)` bulk fetch → `shape_lookup` dict |
| D. GeoFacility 재조회 (그룹 파싱) | 섹션 4 `session_scope + GeoFacility.query` | `facility_integration` 반환 dict 에 `actuators_slot_map`, `groups` 포함 → 섹션 4 는 `integ` 만 참조. 사용되지 않게 된 `GeoFacility`, `session_scope`, `AOT_DB_PATH` import 제거 |

**파일**:
- `aot/aot_flask/geo/facility_integration.py` — `_FITTING_KIND_TO_ACTUATOR_KIND` 추가, fitting kind 추론 2-pass, `actuators_slot_map`/`groups` 페이로드 포함
- `aot/functions/custom_functions/env_coordinator_impl/_profile_loader_mixin.py` — vent fallback 정책 분기, GeoShape bulk fetch, 그룹 파싱을 integ 페이로드로 전환, 미사용 import 정리

**호환성**:
- B1 HTTP 엔드포인트(`/api/geo/facility/<uuid>/integration`) 의 응답에 두 키(`actuators_slot_map`, `groups`)가 추가됨. 기존 필드는 그대로 — 프런트엔드 호환.
- 페이로드 `actuators_resolved` 항목의 `kind` 가 fitting-only 케이스에서 None → 추론된 값으로 채워질 수 있음. 기존 소비자가 `kind` 의 None 을 의미 있게 다루지 않았다면 무영향.
- GeoFacility 모델에 `groups` 컬럼이 아직 없으므로 `groups` 는 현재 빈 dict. 컬럼 추가 시 그대로 활용.

---

## 6. 향후 (이번 작업서 범위 밖 — 설계 §14.9)

- 면별 측창 등록 UI
- bay_index zone 제어
- circulation_fan/exhaust_fan ACH 모델
- 커튼 coverage 분리
- sensor zone wiring
- 모바일 designer
- end_behavior facility-derived 매핑

각 항목은 별도 PRD/작업서로 분리.
