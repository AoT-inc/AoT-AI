# DESIGN — GIS 시설 도형 기반 파라메트릭 빌딩 시스템

## 문서 메타
- 문서 번호: DESIGN-GEO-FACILITY-001
- 작성일: 2026-05-03
- 상태: Draft
- 관련 문서: PRD-GEO-FACILITY-001
- 작업 디렉터리: `Build/5_docker`

---

## 1. 아키텍처 개요

```
┌──────────────────────────────────────────────────────────────────────┐
│                          GEO 설정 페이지                              │
│  /geo/design (기존)  ──[Facility Design 버튼]──▶  /geo/facility (신규) │
└──────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼ 저장
┌──────────────────────────────────────────────────────────────────────┐
│                          데이터 계층                                   │
│  geo_shape (기존)              geo_facility (신규)                    │
│  ┌────────────────┐            ┌────────────────────┐                │
│  │ type=facility  │ unique_id  │ shape_uuid (FK)    │                │
│  │ feature(JSON)  │ ◄────────  │ envelope, actuators│                │
│  │ parent_id (자기참조)         │ bays, computed     │                │
│  └────────────────┘            └────────────────────┘                │
│  ┌────────────────┐                                                   │
│  │ type=facility_bay │ parent_id → 외곽 facility shape                │
│  └────────────────┘                                                   │
└──────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼ 조회
┌──────────────────────────────────────────────────────────────────────┐
│                          대시보드 위젯                                 │
│  AoT_map (기존)        AoT_facility (신규)                            │
│  ─ 시설 폴리곤 표시    ─ A. SVG 미믹 단면                             │
│  ─ 상태색 오버레이     ─ B. 환경 요약 + 타임라인                      │
│                        ─ C. AI 권고 카드(승인 버튼)                   │
└──────────────────────────────────────────────────────────────────────┘
```

## 2. 데이터 모델

### 2-1. 신규 테이블 `geo_facility`

```python
# aot/databases/models/geo.py 에 추가
class GeoFacility(CRUDMixin, db.Model):
    """
    Represents a building-level facility with structural and operational metadata.
    Linked to GeoShape (type='facility') for outer polygon footprint.
    """
    __tablename__ = "geo_facility"
    __table_args__ = {'extend_existing': True}

    id           = db.Column(db.Integer, primary_key=True)
    unique_id    = db.Column(db.String(36), nullable=False, unique=True, default=set_uuid)

    # Linkage
    shape_uuid   = db.Column(db.String(36), nullable=False, index=True)  # → GeoShape.unique_id
    geo_id       = db.Column(db.String(64), nullable=False, index=True)  # → GeoMap.unique_id

    # Identity
    name         = db.Column(db.String(128), nullable=False)
    preset       = db.Column(db.String(64), default='standard_arch')
    structure    = db.Column(db.String(32), default='single')   # single | connected
    bay_count    = db.Column(db.Integer, default=1)

    # Sizing & shape (JSON)
    geometry_3d  = db.Column(JSON)
    # {span_width_m, eave_height_m, ridge_height_m, length_m, roof_type, orientation_deg}

    # Envelope (JSON: outer + inner + curtain)
    envelope     = db.Column(JSON)
    # {layer_count: 1|2,
    #  outer:{cover_material, side_vent:{enabled, height_m, length_ratio},
    #         roof_vent:{enabled, type, width_m}},
    #  inner:{cover_material, air_gap_m,
    #         side_vent:{enabled, control_mode}, roof_vent:{enabled, control_mode}},
    #  curtain:{thermal:bool, shade:bool}}

    # Actuators mapping (JSON, 12 slots)
    actuators    = db.Column(JSON)
    # {outer_side_vent_motor, outer_roof_vent_motor,
    #  inner_side_vent_motor, inner_roof_vent_motor,
    #  thermal_curtain, shade_curtain,
    #  irrigation_valve,
    #  circulation_fan, exhaust_fan,
    #  heater, cooler, heat_pump}

    # Bays (JSON list, length=1 for single, N for connected)
    bays         = db.Column(JSON)
    # [{id, polygon_shape_uuid, crop, sensor_zone:[input_unique_ids]}]

    # Computed capacity cache (JSON)
    computed     = db.Column(JSON)
    # {floor_m2, envelope_m2, volume_m3, glazing_m2,
    #  vent_open_m2, ach_m3h, heating_kw, cooling_kw}

    sort_order   = db.Column(db.Integer, default=0)
    notes        = db.Column(db.Text, default='')

    # Audit
    created_at   = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at   = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by   = db.Column(db.String(36), default='')

    # Relationship
    shape = db.relationship(
        "GeoShape",
        primaryjoin="foreign(GeoFacility.shape_uuid) == GeoShape.unique_id",
        backref=db.backref("facility", uselist=False)
    )
```

### 2-2. 기존 `GeoShape` 활용

| 시설 요소 | `GeoShape.type` | `parent_id` |
|---|---|---|
| 외곽 폴리곤 | `facility` | NULL |
| 동별 분동선(연동) | `facility_bay` | 외곽 facility shape의 `id` |

→ 신규 컬럼 추가 없음, 기존 String 컬럼 그대로 사용.

### 2-3. Alembic 마이그레이션

- 파일명 규칙: `XXXX_add_geo_facility_table.py` (rev id는 작성 시 생성)
- `op.create_table('geo_facility', ...)` 1건
- `op.create_index('ix_geo_facility_shape_uuid', ...)`, `ix_geo_facility_geo_id`

## 3. API 라우트

### 3-1. 신규 페이지 라우트
`aot/aot_flask/routes_geo.py`에 추가:

```python
@blueprint.route('/geo/facility')
@login_required
def page_facility():
    """Facility Design page — register building-level facility specs."""
    if not utils_general.user_has_permission('edit_settings'):
        return redirect(url_for('routes_general.home'))

    # Pass design maps so the user can pick the parent map
    design_maps = GeoMap.query.filter_by(category='design')\
        .order_by(GeoMap.updated_at.desc()).all()
    facilities = GeoFacility.query.order_by(GeoFacility.updated_at.desc()).all()

    return render_template('pages/geo/geo_facility.html',
                           active_page='geo_facility',
                           map_configs=design_maps,
                           facilities=facilities,
                           geo_config=utils_geo.get_geo_config())
```

### 3-2. 신규 API 라우트
| Method | Path | 함수 | 설명 |
|---|---|---|---|
| GET    | `/api/geo/facility/list`           | `api_facility_list`     | 전체 시설 목록 |
| GET    | `/api/geo/facility/<uuid>`         | `api_facility_get`      | 단일 시설 조회 |
| POST   | `/api/geo/facility`                | `api_facility_save`     | 등록/수정 (upsert) |
| DELETE | `/api/geo/facility/<uuid>`         | `api_facility_delete`   | 삭제 (사용자 확인 필요) |
| POST   | `/api/geo/facility/compute`        | `api_facility_compute`  | 사양 → 용량 산출(미리보기, DB 미저장) |

### 3-3. 진입점 버튼 변경
[aot/aot_flask/templates/pages/geo/geo_design.html:343-349](aot/aot_flask/templates/pages/geo/geo_design.html:343):

```html
<!-- Section 1: Title (변경 후) -->
<div class="d-flex justify-content-between align-items-center mb-3">
    <h3>{{ _('Spatial Design Studio') }}</h3>
    <div class="d-flex">
        <button class="btn btn-outline-primary aot-pill-btn mr-2"
                onclick="window.location.href='/geo/facility'">
            {{ _('Facility Design') }}
        </button>
        <button class="btn btn-outline-primary aot-pill-btn" onclick="openGeoSettings()">
            {{ _('GIS Settings') }}
        </button>
    </div>
</div>
```

## 4. UI 구조

### 4-1. `/geo/facility` 페이지 레이아웃

```
┌──────────────────────────────────────────────────────────────────────┐
│  [← Spatial Design Studio]   Facility Design                          │
├──────────────────────────────────────────────────────────────────────┤
│  Step 1. Map  : [Map selector dropdown]                               │
│  Step 2. Shape: [Drawing canvas]   single / connected (N=__) toggle   │
│  Step 3. Spec : ┌─ Preset: [Standard Arch ▼]                          │
│                  │  Span 7m  Eave 2m  Ridge 4m  Length [____]        │
│                  │  ┌─ Envelope ──────────────────────────────────┐   │
│                  │  │ Layer count: ○1   ○2                        │   │
│                  │  │ Outer cover: [vinyl_double ▼]                │   │
│                  │  │   ☐ Side vent  ☐ Roof vent                  │   │
│                  │  │ Inner cover: [non_woven_fabric ▼]            │   │
│                  │  │   Control mode: ○synced  ○independent        │   │
│                  │  │ Curtain: ☐thermal  ☐shade                    │   │
│                  │  └────────────────────────────────────────────┘   │
│                  │  ┌─ Actuators (12 slots) ──────────────────────┐   │
│                  │  │ outer_side_vent_motor: [output picker ▼]    │   │
│                  │  │ ... (12 rows)                                │   │
│                  │  └────────────────────────────────────────────┘   │
│                  └────                                                │
│  Step 4. Preview: ┌────────────────────────────────────────────┐      │
│                    │  Floor 49 m²   Volume 147 m³               │      │
│                    │  Glazing 89 m²   Vent open 12.6 m²        │      │
│                    │  Heating ≈ 18 kW   Cooling ≈ 24 kW         │      │
│                    │  ⓘ 기계설비 1차 산정 참고치 (±5~10%)       │      │
│                    └────────────────────────────────────────────┘      │
│  Step 5.        : [Cancel]   [Save]                                   │
└──────────────────────────────────────────────────────────────────────┘
```

### 4-2. 위젯 `AoT_facility.py` 본체

```
┌────────────────────────────────────────────┐
│ Facility: [GH-001 표준온실 ▼]              │
├────────────────────────────────────────────┤
│ § A. SVG 미믹 단면                         │
│  ┌────────────────────────────────────┐    │
│  │   ☀ 외기 12°C  ↘ 4m/s  일사 320W/m²│    │
│  │   ════════╮                         │    │
│  │   ════════╯  ← 외피 (실선=현재)     │    │
│  │   ─ ─ ─ ─ ╮  ← 내피 (점선=AI권고)   │    │
│  │   ─ ─ ─ ─ ╯                         │    │
│  │   │ 측창 50%▲│       │작물│         │    │
│  │   └────────────────────────┘        │    │
│  └────────────────────────────────────┘    │
├────────────────────────────────────────────┤
│ § B. 환경 요약 + 타임라인                   │
│  내부 24.1°C  습도 72%  CO2 480ppm          │
│  [▁▂▃▄▆█▇▆▅▄▃ — 6h 과거 + 12h 예보]         │
├────────────────────────────────────────────┤
│ § C. AI 권고 카드                           │
│  ┌──────────────────────────────────┐       │
│  │ 🔴 즉시 (지금)  신뢰도 84%      │       │
│  │ 측창 50%→20%, 천창 30%→0%        │       │
│  │ 근거: 외기 12°C, 풍속 4m/s       │       │
│  │ 예상: 1h 후 22.5°C 도달          │       │
│  │ [승인하고 적용] [수정] [무시]    │       │
│  └──────────────────────────────────┘       │
│  ┌─ 🟡 1시간 내 ─────┐                      │
│  ┌─ 🟢 6시간 내 ─────┐                      │
└────────────────────────────────────────────┘
```

### 4-3. 위젯 `WIDGET_INFORMATION` 골격

`aot/widgets/AoT_facility.py`:
```python
WIDGET_INFORMATION = {
    'widget_name_unique': 'AoT_facility',
    'widget_name': 'AoT 시설',
    'widget_library': 'SVG + MapLibre fill-extrusion (optional)',
    'no_class': True,
    'head_html': WIDGET_HEAD_HTML,   # SVG mimic CSS + AoT_facility.js
    'body_html': WIDGET_BODY_HTML,   # selector + 3 sections
    'message': '시설의 단면 미믹·환경 요약·AI 권고를 한 위젯에서 제공합니다.',
    'widget_width': 20,
    'widget_height': 20,
    'generate_page_variables': widget_variables,
    'execute_at_modification': execute_at_modification,
    'custom_options': [
        # facility selector, refresh period, AI advice toggle, 등
    ],
    'widget_dashboard_head': WIDGET_HEAD_HTML,
    'widget_dashboard_body': WIDGET_BODY_HTML,
    'widget_dashboard_js_ready_end': """ ... """,
}
```

## 5. 용량 산출 로직 (`aot/aot_flask/geo/facility_calc.py` 신규)

### 5-1. 자재 테이블(내장, 편집 가능)

| 자재 | U (W/m²K) | 투과율 |
|---|---|---|
| vinyl_single      | 6.0 | 0.85 |
| vinyl_double      | 4.0 | 0.78 |
| po_film           | 6.5 | 0.85 |
| polycarbonate     | 3.0 | 0.78 |
| glass             | 5.8 | 0.85 |
| non_woven_fabric  | 3.5 | 0.50 |
| pe_film           | 6.5 | 0.85 |
| air_cushion       | 2.8 | 0.75 |

### 5-2. 산출식

```
floor_area      = polygon.area_m2()
perimeter       = polygon.perimeter_m()
roof_arch_len   = arch_length(span, ridge_h - eave_h)        # 아치형
envelope_area   = perimeter * eave_height + roof_arch_len * length
volume          = floor_area * eave_height + arch_volume(...)

# 이중 외피 U값
if layer_count == 2:
    R_total = 1/U_outer + R_airgap(air_gap_m) + 1/U_inner
    U_eff   = 1 / R_total
else:
    U_eff   = U_outer

heating_load_kw = (envelope_area * U_eff * delta_T) / 1000
cooling_load_kw = (roof_glazing * solar_gain_factor + transpiration) / 1000
ach_natural     = vent_open_area * wind_factor / volume * 3600
ach_forced      = sum(fan_capacity_m3h) / volume
ach_total       = ach_natural + ach_forced
```

### 5-3. 정확도

`±5~10% 근사치` 라벨 명시. 작물·지역·단열재 세부정보 추가 시 ±3%까지 향상 가능(차기 범위).

## 6. AI 입력·출력 패키지

### 6-1. AI 입력 (위젯 → AI)

```yaml
ai_input:
  facility:
    id, name, preset, structure
    geometry_3d
    envelope: { layer_count, outer, inner, curtain }
    actuators: { ... 12종 mapping }
    crop: { type, growth_stage, optimal_temp_range }
  current:
    timestamp
    indoor: { temp, humidity, co2, soil_moisture }
    actuators_state: { 각 액추에이터 현재 개도/ON-OFF }
  weather:
    observed_6h: [...]
    forecast_24h: [...]
    sun: { sunrise, sunset, current_altitude }
  history:
    last_24h_actions: [...]   # 사용자 승인 기록
```

### 6-2. AI 출력 (AI → 위젯)

```yaml
ai_output:
  recommendations:
    - horizon: now | 1h | 6h
      actions: [{actuator, target_value, current_value}]
      reasoning: "외기 12°C, 풍속 4m/s, ..."
      confidence: 0.84
      expected_effect: "1h 후 22.5°C"
      priority: 1   # 자연환기 우선
  alerts: [...]
  predictions:
    indoor_temp_24h: [...time series...]
```

### 6-3. 승인 흐름

```
[권고 표시(점선)] → 사용자 클릭 → POST /api/facility/<id>/apply
   payload: { advice_id, approved_actions: [...] }
   처리: output 명령 발행 + 로그 기록 + 1h 후 effect 검증 스케줄
```

## 7. 파일 구조 변경 요약

### 7-1. 신규 파일

| 경로 | 종류 |
|---|---|
| `aot/widgets/AoT_facility.py` | 신규 위젯 |
| `aot/aot_flask/templates/pages/geo/geo_facility.html` | GEO 페이지 템플릿 |
| `aot/aot_flask/static/js/geo/aot-facility-design.js` | 페이지 JS |
| `aot/aot_flask/static/js/widget/AoT_facility/aot-facility-widget.js` | 위젯 JS |
| `aot/aot_flask/geo/facility_calc.py` | 용량 산출 로직 |
| `aot/aot_flask/geo/facility_io.py` | DB CRUD 매니저 |
| `alembic_db/alembic/versions/XXXX_add_geo_facility_table.py` | 마이그레이션 |

### 7-2. 수정 파일

| 경로 | 변경 |
|---|---|
| `aot/databases/models/geo.py` | `GeoFacility` 클래스 추가 |
| `aot/databases/models/__init__.py` | `GeoFacility` export 추가 |
| `aot/aot_flask/routes_geo.py` | `page_facility()` + 5개 API 추가 |
| `aot/aot_flask/templates/pages/geo/geo_design.html` (line 343-349) | `Facility Design` 버튼 추가 |

## 8. 위험·완화

| 위험 | 영향 | 완화 |
|---|---|---|
| Alembic 마이그레이션 충돌 | DB 시작 실패 | 별도 rev id, head 파악 후 적용 |
| `AoT_map` 위젯의 `show_facility_shape` 회귀 | 시설 표시 누락 | 신규 facility 등록은 GeoShape에도 동시 INSERT |
| 액추에이터 매핑 누락 | 미믹·AI 권고 빈칸 | `null` 슬롯은 표시 생략, 사용자에게 경고 toast |
| 용량 산출 정확도 오인 | 운영자 오판 | "참고치 ±5~10%" 라벨 항상 노출 |

## 9. 테스트 전략

- **단위**: `facility_calc.py` 산출식, `facility_io.py` CRUD
- **통합**: 시설 등록 → DB 저장 → 위젯 조회 흐름
- **회귀**: `AoT_map` 위젯에서 `show_facility_shape` 토글 시 신규 시설 외곽 폴리곤 정상 표시
- **마이그레이션**: 신규 테이블 생성 + 롤백 가능
