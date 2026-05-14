# PLAN — GIS 시설 도형 기반 파라메트릭 빌딩 시스템

## 문서 메타
- 문서 번호: PLAN-GEO-FACILITY-001
- 작성일: 2026-05-03
- 상태: Draft
- 관련 문서: PRD-GEO-FACILITY-001, DESIGN-GEO-FACILITY-001, TASK-GEO-FACILITY-001
- 작업 디렉터리: `Build/5_docker`

---

## 1. 단계 개요

```
P1. 데이터 계층     →  P2. 백엔드 라우트  →  P3. GEO 설정 페이지
                                                       │
                                                       ▼
P6. 회귀·인수 검증  ←  P5. 위젯              ←  P4. 용량 산출 + 미리보기
```

각 단계는 이전 단계의 산출물을 입력으로 받는다. P3·P4는 일부 병렬 가능(P3 UI 골격 + P4 계산 모듈).

## 2. 단계별 상세

### P1. 데이터 계층 (DB)

**산출물**
- `aot/databases/models/geo.py`에 `GeoFacility` 클래스 추가
- `aot/databases/models/__init__.py`에 export
- Alembic 마이그레이션 1건 생성

**작업 항목**
1. `GeoFacility` SQLAlchemy 모델 정의 (DESIGN §2-1 스키마)
2. `__init__.py`에 import/export 추가
3. `alembic revision -m "add_geo_facility_table"` 생성
4. `op.create_table('geo_facility', ...)` + 인덱스 작성
5. 다운그레이드 함수 `op.drop_table` 작성

**검증**
- `alembic upgrade head` → 테이블 존재 확인
- `alembic downgrade -1` → 테이블 제거 확인
- `alembic upgrade head` 재적용 정상

**완료 조건**: GeoFacility ORM이 import 가능, 테이블이 생성·롤백 가능.

---

### P2. 백엔드 라우트·CRUD·매니저

**산출물**
- `aot/aot_flask/geo/facility_io.py` (CRUD 매니저)
- `aot/aot_flask/routes_geo.py` 수정 (라우트 추가)

**작업 항목**
1. `FacilityManager` 클래스 작성 (CRUD: list/get/save/delete)
2. `save()` 내부에서 GeoShape(type='facility') + GeoFacility를 트랜잭션으로 동시 저장
3. 연동 시 동별 분동선은 GeoShape(type='facility_bay', parent_id=외곽shape.id)로 INSERT
4. `routes_geo.py`에 `page_facility()` 라우트 추가
5. API 5종 추가:
   - `GET /api/geo/facility/list`
   - `GET /api/geo/facility/<uuid>`
   - `POST /api/geo/facility`
   - `DELETE /api/geo/facility/<uuid>` (Constitution Art.5 — 사용자 확인 필수)
   - `POST /api/geo/facility/compute` (DB 미저장 미리보기)
6. 권한 체크(`edit_settings`) 적용

**검증**
- curl로 API 5종 응답 확인
- list → get → save → delete 시나리오 통과
- 트랜잭션 실패 시 GeoShape·GeoFacility 모두 롤백

**완료 조건**: API 5종 모두 정상 응답, 데이터 정합성 유지.

---

### P3. GEO 설정 페이지

**산출물**
- `aot/aot_flask/templates/pages/geo/geo_facility.html`
- `aot/aot_flask/static/js/geo/aot-facility-design.js`
- `aot/aot_flask/templates/pages/geo/geo_design.html` (line 343-349 수정)

**작업 항목**
1. 진입 버튼 추가 (geo_design.html line 343-349) — DESIGN §3-3 그대로
2. `geo_facility.html` 5단계 레이아웃 작성 (DESIGN §4-1)
3. MapLibre 지도 + Drawing tool 통합 (기존 `aot-maplibre-draw.js` 재사용)
4. 단동/연동 토글 + 동 수 입력 → 외곽 폴리곤 분할 라인 자동 생성
5. 외피·창호·커튼 폼 위젯
6. 액추에이터 12종 매핑 (output picker × 12)
7. 저장 버튼 → `POST /api/geo/facility` 호출

**검증**
- 페이지 진입 정상, 폼 입력 정상
- 단동·연동 각각 1개씩 등록 성공
- DB에 GeoShape + GeoFacility 정상 INSERT

**완료 조건**: 등록 시나리오 5단계가 매끄럽게 동작.

---

### P4. 용량 산출 + 실시간 미리보기

**산출물**
- `aot/aot_flask/geo/facility_calc.py`
- 자재 테이블 내장(편집 가능 구조)
- `/api/geo/facility/compute` 통합

**작업 항목**
1. 자재별 U·투과율 테이블 정의(DESIGN §5-1, 8종)
2. 면적·체적·창호면적 계산 함수
3. 환기량(자연 + 강제) 계산 함수
4. 난방·냉방 1차 부하 계산 함수
5. 이중 외피 U_eff 계산 (R_total 누적)
6. 미리보기 API: 사양 JSON → 산출 JSON 응답(DB 미저장)
7. 페이지 JS에서 입력 변경 시 debounce(500ms) → compute API 호출
8. *"기계설비 1차 산정 참고치 (±5~10%)"* 라벨 노출

**검증**
- 단위 테스트: 자재별 U값 → 산출 결과 일치
- 단층 vs 이중: 이중 시 U_eff ≈ 단층의 0.6배
- 페이지 입력 → 미리보기 갱신 < 100ms

**완료 조건**: 미리보기 박스가 실시간 갱신되며 산출치가 합리적 범위.

---

### P5. 위젯 `AoT_facility`

**산출물**
- `aot/widgets/AoT_facility.py`
- `aot/aot_flask/static/js/widget/AoT_facility/aot-facility-widget.js`
- 시설 단면 SVG 템플릿 (표준 온실 1종)

**작업 항목**
1. `WIDGET_INFORMATION` dict 작성 (`AoT_map.py` 패턴)
2. `custom_options`: 시설 선택, refresh 주기, AI advice 토글
3. `widget_dashboard_body` 작성 (3섹션)
4. SVG 미믹 템플릿: 표준 온실 단면(외피 + 작물 + 측창/천창 슬롯)
5. 이중 외피 분기 — `layer_count==2`일 때 내피 단면 추가, 공기층 음영
6. 액추에이터 현재 상태(실선) + AI 권고 상태(점선) 동시 표시
7. AI 권고 카드 3종(now/1h/6h) — mock JSON으로 PoC
8. 승인 버튼 → `POST /api/facility/<id>/apply` (mock 처리, 실제 output 발행은 차기)

**검증**
- 위젯 등록 → 시설 선택 → 3섹션 렌더 정상
- 단동·연동·이중외피 각각 케이스 시각 확인
- `AoT_map`에서 같은 시설의 외곽 폴리곤이 정상 표시(회귀)

**완료 조건**: 위젯이 PoC 시설 1개에 대해 3섹션 정상 표시.

---

### P6. 회귀·인수 검증

**산출물**
- 자동화 테스트 (`tests/test_facility_calc.py`, `tests/test_facility_routes.py`)
- 수동 인수 시나리오 결과 기록

**작업 항목**
1. pytest 단위 테스트 작성 — 산출식, CRUD
2. 통합 테스트 — 등록 → 조회 → 위젯 렌더
3. `AoT_map` 회귀 — `show_facility_shape` ON/OFF, 신규 시설 외곽 표시
4. Alembic 양방향 마이그레이션 검증
5. 수동 인수 시나리오:
   - 단동 표준 온실 등록·수정·삭제
   - 연동(N=3) 표준 온실 등록
   - 이중 외피 단동 등록
   - 액추에이터 12종 모두 매핑
   - 위젯에서 AI 권고 *승인* 클릭 → 매핑된 output에 mock 명령 발행 확인

**완료 조건**: DoD-1 ~ DoD-12 모두 충족.

---

## 3. 단계별 산출 우선순위

| 우선순위 | 단계 | 사유 |
|---|---|---|
| 1 (필수, 직렬) | P1 → P2 | 데이터 계층 없으면 이후 단계 불가능 |
| 2 (필수, 직렬) | P3 또는 P5 | 사용자 가시 산출물 우선 |
| 3 (병렬 가능) | P4 | P3 폼이 있어야 통합되지만 단독 모듈로 선개발 가능 |
| 4 (마지막) | P6 | 모든 단계 완료 후 종합 검증 |

## 4. 추정 단계별 분량 (참고)

| 단계 | 신규 파일 | 수정 파일 | 핵심 함수 |
|---|---|---|---|
| P1 | 1 (마이그레이션) | 2 | `GeoFacility` 클래스 |
| P2 | 1 (`facility_io.py`) | 1 | `FacilityManager` + 5 API |
| P3 | 2 (HTML, JS) | 1 | 페이지 워크플로 |
| P4 | 1 (`facility_calc.py`) | 0 | 산출 함수 6종 |
| P5 | 2 (위젯, JS) | 0 | `WIDGET_INFORMATION` + SVG 템플릿 |
| P6 | 2 (테스트) | 0 | 단위·통합·회귀 |

## 5. 합의 후 진행 절차

1. PRD/DESIGN/TASK/PLAN 4개 문서 작성 → docs/dev 저장 (현재 단계)
2. 포맨 v2 DB에 4개 문서 등록
3. 사용자 검토·수정·승인
4. **승인 후** P1부터 코드 구현 시작 (단계별 사용자 승인 옵션 제공 가능)

코드 구현은 본 PLAN 승인 후 별도 승인을 다시 받아 진행한다.
