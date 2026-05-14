# TASK — GIS 시설 도형 기반 파라메트릭 빌딩 시스템

## 문서 메타
- 문서 번호: TASK-GEO-FACILITY-001
- 작성일: 2026-05-03
- 상태: Draft
- 관련 문서: PRD-GEO-FACILITY-001, DESIGN-GEO-FACILITY-001
- 작업 디렉터리: `Build/5_docker`

---

## 1. 작업 개요

GIS 지도 위 시설 도형을 단순 폴리곤에서 **파라메트릭 빌딩 사양**으로 확장한다. 사용자가 GEO 페이지에서 시설을 등록하면 형상·외피·창호·액추에이터 사양과 함께 1차 용량 산출 결과가 저장되고, 대시보드 위젯에서 단면 미믹·환경 요약·AI 권고(승인 버튼 포함)를 통해 운영할 수 있게 한다.

## 2. 범위

### 2-1. In-Scope
- 신규 페이지 `/geo/facility` 및 진입 버튼(`/geo/design` 페이지 내)
- 신규 데이터 모델 `GeoFacility` (`geo_facility` 테이블) + Alembic 마이그레이션
- 신규 API 5종 (list/get/save/delete/compute)
- 신규 위젯 `AoT_facility` (대시보드 운영용)
- 신규 용량 산출 모듈 (`facility_calc.py`)
- 표준 온실 프리셋 1종(둥근 아치형, 7m × 측고 2m × 용마루 4m)
- 단동/연동 모두 지원 (Parent-Child)
- 외피 단층/이중 모두 지원, 자재 후보 외피 5종 + 내피 5종
- 액추에이터 12종 매핑(환기·커튼·관수·팬·냉난방)

### 2-2. Out-of-Scope (차기)
- 비닐하우스/창고 등 다른 시설 타입의 SVG 미믹 템플릿
- AI 추론 엔진 자체 구현(룰베이스 vs LLM 선택)
- 자동 액추에이터 실행(무인 운전)
- 3D glTF 외관 렌더링
- 작물별 ETc·정밀 단열 보정 등 ±3% 정밀 산출

## 3. Definition of Done

- [ ] DoD-1: `/geo/design` 페이지의 `GIS Settings` 버튼 왼쪽에 `Facility Design` 버튼이 노출된다.
- [ ] DoD-2: 클릭 시 `/geo/facility` 페이지로 이동한다.
- [ ] DoD-3: 사용자는 표준 온실 프리셋으로 단동·연동 시설을 등록할 수 있다.
- [ ] DoD-4: 등록 시 외곽 폴리곤은 `geo_shape (type='facility')`에, 사양은 `geo_facility`에 저장된다.
- [ ] DoD-5: 등록 직후 면적·체적·창호면적·환기량·난방/냉방 1차 부하가 자동 산출되어 미리보기에 노출된다.
- [ ] DoD-6: 산출 결과에는 *"기계설비 1차 산정 참고치 (±5~10%)"* 라벨이 함께 표시된다.
- [ ] DoD-7: `AoT_map` 위젯의 `show_facility_shape` 옵션이 신규 시설 외곽도 정상 표시한다(회귀 없음).
- [ ] DoD-8: `AoT_facility` 위젯이 대시보드에 등록 가능하며, 시설 선택 시 SVG 미믹·환경 요약·AI 권고 카드 3섹션이 렌더된다.
- [ ] DoD-9: 이중 외피인 경우 외피·내피 단면이 분리 표시되고 사이 공기층이 음영 처리된다.
- [ ] DoD-10: AI 권고 카드는 horizon별 3종(now/1h/6h) 표시되며, *승인하고 적용*·*수정*·*무시* 3개 버튼을 제공한다.
- [ ] DoD-11: Alembic 마이그레이션 1건으로 `geo_facility` 테이블이 생성·롤백된다.
- [ ] DoD-12: 단위·통합·회귀 테스트가 모두 통과한다.

## 4. 의존성

| 항목 | 상태 | 비고 |
|---|---|---|
| MapLibre GL JS 3.6.2 | 보유 | Pure 모드 사용 |
| Mycodo 위젯 프레임워크 | 보유 | `WIDGET_INFORMATION` 패턴 |
| `routes_geo.py` blueprint | 보유 | 라우트 추가 |
| `geo_overlays.py` GeoShape 시스템 | 보유 | type='facility' 기존 처리 |
| Alembic | 보유 | 마이그레이션 추가 |
| Output / Function 모델 | 보유 | 액추에이터 매핑 대상 |
| AI 추론 엔진 | 별도 | 본 작업 외, mock 응답으로 PoC 가능 |

## 5. 산출물

| 종류 | 경로 |
|---|---|
| 모델 | `aot/databases/models/geo.py` (수정) |
| 마이그레이션 | `alembic_db/alembic/versions/XXXX_add_geo_facility_table.py` |
| 페이지 라우트 | `aot/aot_flask/routes_geo.py` (수정) |
| 페이지 템플릿 | `aot/aot_flask/templates/pages/geo/geo_facility.html` |
| 페이지 JS | `aot/aot_flask/static/js/geo/aot-facility-design.js` |
| 진입 버튼 | `aot/aot_flask/templates/pages/geo/geo_design.html` (수정 line 343-349) |
| 용량 산출 | `aot/aot_flask/geo/facility_calc.py` |
| DB CRUD | `aot/aot_flask/geo/facility_io.py` |
| 위젯 | `aot/widgets/AoT_facility.py` |
| 위젯 JS | `aot/aot_flask/static/js/widget/AoT_facility/aot-facility-widget.js` |
| 테스트 | `tests/test_facility_calc.py`, `tests/test_facility_routes.py` |

## 6. 검증 방법

| 단계 | 방법 |
|---|---|
| 단위 | pytest로 `facility_calc.py` 산출식 검증 (자재별 U값 → 부하 결과) |
| 통합 | 시설 등록 API → DB 조회 → 위젯 렌더 흐름 자동화 |
| 회귀 | `AoT_map` 위젯의 facility 폴리곤 표시 정상 동작 (수동 + 스냅샷) |
| 마이그레이션 | `alembic upgrade head` → `alembic downgrade -1` 양방향 |
| 수동 UX | 단동 1개 + 연동 1개 등록, 외피 단층/이중 각각 등록, 12종 액추에이터 매핑 |

## 7. 위험 및 완화

| 위험 | 완화 |
|---|---|
| Alembic head 충돌 | 작업 직전 `alembic heads` 확인 후 down_revision 지정 |
| 시설 등록 시 GeoShape와 GeoFacility 정합성 | 트랜잭션 내 동시 INSERT, 실패 시 롤백 |
| 위젯 렌더 성능 | 미믹 SVG 정적 템플릿 캐시, 환경값만 갱신 |
| 액추에이터 미매핑 화면 노출 | `null` 슬롯은 미표시, 등록 시 경고만 |

## 8. 인수 기준 (요약)

PoC 표준 온실(단동 + 연동) 등록 → DB 저장 → AoT_map에서 폴리곤 보임 → AoT_facility 위젯에서 미믹/환경/AI 권고 3섹션 정상 → 권고 *승인* 클릭 시 매핑된 output에 명령 발행 → 1h 후 효과 검증 표시.
