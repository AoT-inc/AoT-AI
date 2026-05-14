# AoT 서비스 전체 아키텍처 문서

**문서 버전**: 1.0  
**작성일**: 2026-04-29  
**AoT 버전**: 26.0.7  
**상태**: 완료

---

## 목차

1. [개요](#1-개요)
2. [시스템 구성](#2-시스템-구성)
3. [레이어별 세부 사항](#3-레이어별-세부-사항)
4. [데이터베이스 구조](#4-데이터베이스-구조)
5. [API 엔드포인트](#5-api-엔드포인트)
6. [AI/ML 통합](#6-aiml-통합)
7. [GIS 기능](#7-gis-기능)

---

## 1. 개요

### 1.1 프로젝트 목적

AoT (Art of Things) v26.0.7는 Mycodo 기반 환경 제어 시스템으로, 다양한 센서 입력을 통해 환경을 감지하고 GPIO, 릴레이, 펌프, 모터 등 다양한 출력을 제어합니다.

### 1.2 주요 기능

- **환경 모니터링**: 온도, 습도, 토양 수분, 조명 등 100+ 센서 지원
- **자동 제어**: PID 제어, 타이머, 조건부 액션 등 40+ 함수
- **출력 제어**: GPIO, 릴레이, PWM, 모터 등 50+ 출력 장치
- **데이터 시각화**: 실시간 차트, 대시보드, 위젯
- **GIS 기능**: 지도 기반 공간 데이터 관리
- **AI 통합**: GPT-4o 연동, 추천 시스템, 지식 그래프

### 1.3 기술 스택

| 계층 | 기술 |
|------|------|
| Backend | Python 3.11, Flask 3.1.0, SQLAlchemy, Pyro5 (RPC) |
| Database | SQLite (설정/메타데이터), InfluxDB 2.7 (시계열 데이터) |
| Frontend | Bootstrap 4, TailwindCSS, Highcharts, jQuery, GridStack.js |
| Infrastructure | Docker, Waitress/Gunicorn |
| AI | GPT-4o, MCP (Model Context Protocol), Experience Knowledge Graph |

---

## 2. 시스템 구성

### 2.1 Docker Compose 구성

```
┌─────────────────────────────────────────────────────────────────┐
│                        Docker Compose                            │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐ │
│  │    aot-app      │  │   aot_daemon    │  │    influxdb     │ │
│  │  (Flask :80)    │──│  (Pyro5 :9081)  │──│  (:8086)        │ │
│  │   Web UI        │  │  Controllers    │  │  Time-series    │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘ │
└─────────────────────────────────────────────────────────────────┘
```

### 2.2 디렉토리 구조

```
5_docker/
├── aot/
│   ├── aot_daemon.py          # 백그라운드 데몬 (컨트롤러 관리)
│   ├── aot_flask/             # Flask 웹 애플리케이션
│   │   ├── app.py             # Application factory
│   │   ├── routes_*.py        # 30+ 라우트 모듈
│   │   ├── templates/         # Jinja2 템플릿
│   │   ├── static/            # JS, CSS, 이미지
│   │   └── utils/             # 유틸리티
│   ├── config/__init__.py     # 설정 (v26.0.7)
│   ├── databases/             # SQLAlchemy 모델
│   │   └── models/            # 50+ 테이블 모델
│   ├── controllers/          # 컨트롤러 스레드
│   ├── inputs/               # 센서 드라이버 (~100개)
│   ├── outputs/              # 출력 드라이버 (~50개)
│   ├── inputs_gis/           # GIS 입력 모듈 (~25개)
│   ├── devices/              # 공통 장치 드라이버
│   ├── actions/              # 액션 핸들러 (~40개)
│   ├── functions/            # 함수 모듈 (~40개)
│   ├── widgets/              # 대시보드 위젯 (~15개)
│   ├── ai/                  # AI 관련 모듈
│   │   └── services/        # AI 서비스 (~50개)
│   └── utils/               # 공통 유틸리티
├── docker/
│   ├── docker-compose.yml    # 서비스 구성
│   └── Dockerfile          # Python 3.11-slim
├── logs/                    # 로그 파일
├── influxdb_data/           # InfluxDB 데이터 볼륨
├── alembic_db/              # DB 마이그레이션
└── requirements.txt        # Python 의존성
```

---

## 3. 레이어별 세부 사항

### 3.1 Backend Layer - aot_daemon.py

**주요 클래스**: DaemonController

**기능**:
- Pyro5 RPC 서버로 Flask UI와 통신 (포트 9081)
- 컨트롤러 수명주기 관리 (activate/deactivate/restart)
- Periodic 태스크:
  - 통계 전송 (매 24시간)
  - 스케줄러 실행
  - 컨트롤러 상태 모니터링

### 3.2 Flask Application Layer

**Application Factory**: aot_flask/app.py

**주요 블루프린트**:
| 블루프린트 | 설명 |
|-----------|------|
| routes_main | 메인 대시보드 및 페이지 |
| routes_dashboard | 대시보드 위젯 관리 |
| routes_input | 센서 입력 관리 |
| routes_output | 출력 장치 관리 |
| routes_function | 함수 관리 |
| routes_data | 데이터 조회 |
| routes_admin | 관리자 기능 |
| routes_ai | AI 기능 |

### 3.3 Controller Layer

**컨트롤러 타입**:
| 타입 | 설명 |
|------|------|
| Input Controllers | 센서 데이터 수집 (~100개) |
| Output Controllers | 장치 제어 (~50개) |
| Function Controllers | 로직 실행 (~40개) |

### 3.4 Device Layer

**입력 장치**: 온도, 습도, CO2, 조도, 토양수분, 기압, 바람, 강우, pH, EC 등
**출력 장치**: GPIO, 릴레이, PWM, 모터, 솔레노이드밸브, 히터, 쿨러, 팬 등

---

## 4. 데이터베이스 구조

### 4.1 SQLite (aot.db)

**주요 테이블**:

| 테이블명 | 설명 |
|---------|------|
| input | 센서 입력 설정 |
| output | 출력 장치 설정 |
| function | 함수 설정 |
| measurements | 측정 데이터 |
| device_measurements | 장치-측정 관계 |
| conditional | 조건문 |
| method | 제어 방법 |
| pid | PID 제어 설정 |
| users | 사용자 |
| roles | 역할 |
| notes | 메모 |
| dashboard | 대시보드 |
| widget | 위젯 |
| geo_layer | GIS 레이어 |
| geo_shape | GIS 도형 |
| ai_agent | AI 에이전트 |
| ai_entry | AI 항목 |
| ai_feedback_event | AI 피드백 |
| ekg_* | Experience Knowledge Graph |

### 4.2 InfluxDB

**시계열 데이터**: 센서 측정값, 에너지 사용량

---

## 5. API 엔드포인트

### 5.1 REST API

| Method | Endpoint | 설명 |
|--------|----------|------|
| GET | /api/inputs | 입력 목록 |
| POST | /api/inputs | 입력 생성 |
| GET | /api/outputs | 출력 목록 |
| POST | /api/outputs | 출력 생성 |
| GET | /api/measurements | 측정 데이터 |
| GET | /api/dashboard | 대시보드 데이터 |

---

## 6. AI/ML 통합

### 6.1 AI 서비스 구조

```
ai/
├── services/
│   ├── ai_service_*.py       # 50+ AI 서비스
│   ├── ekg_service.py        # Experience Knowledge Graph
│   ├── mcp_service.py        # Model Context Protocol
│   └── recommendation_service.py
├── models/
│   ├── ai_agent.py
│   ├── ai_entry.py
│   ├── ai_feedback_event.py
│   └── ai_role_config.py
└── utils/
```

### 6.2 AI 기능

- **추천 시스템**: 환경 제어 최적화 추천
- **지식 그래프**: 경험 데이터 관리
- **MCP 연동**: 외부 AI 서비스 연동
- **피드백 루프**: 사용자 피드백 기반 학습

---

## 7. GIS 기능

### 7.1 GIS 프로바이더

| 프로바이더 | 유형 | 설명 |
|-----------|------|------|
| gis_vworld.py | WMTS/WMS | 한국국토정보원 |
| gis_maptiler_vector.py | Vector | MapTiler 벡터 타일 |
| gis_osm.py | XYZ | OpenStreetMap |
| gis_google.py | XYZ | Google Maps |

### 7.2 GIS 데이터 구조

- **geo_layer**: 지도 레이어 설정
- **geo_shape**: 도형 데이터 (포인트, 폴리곤)
- **geo_setting**: 레이어 설정

---

## 8. 파일 인벤토리

### 8.1 주요 파일 목록

| 경로 | 설명 |
|------|------|
| aot/aot_daemon.py | 메인 데몬 |
| aot/config/__init__.py | 설정 (v26.0.7) |
| aot/aot_flask/app.py | Flask 앱 |
| aot/databases/models/*.py | 50+ DB 모델 |
| aot/inputs/*.py | ~100 센서 드라이버 |
| aot/outputs/*.py | ~50 출력 드라이버 |
| aot/inputs_gis/*.py | ~25 GIS 모듈 |
| aot/actions/*.py | ~40 액션 핸들러 |
| aot/functions/*.py | ~40 함수 모듈 |
| aot/widgets/*.py | ~15 위젯 |
| aot/ai/services/*.py | ~50 AI 서비스 |

---

**문서 생성일**: 2026-04-29  
**생성자**: Claude Code (Architecture Analysis)
