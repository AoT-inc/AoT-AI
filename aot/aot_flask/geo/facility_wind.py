# coding=utf-8
"""
facility_wind.py — 자연환기 풍압 시뮬레이션 (D1).

개구부(vent_openings)별 풍압계수(Cp)와 유효 환기량을 계산한다.
물리 모델: 개구부 세계좌표 법선 × 풍향벡터 내적 → Cp → Q = Cd·A·V·√|Cp|

좌표 규약
---------
- 지도 2D: X = 동(East), Y = 북(North)
- facility orientation_deg: 시계방향(북 기준) — Three.js Y축 회전과 동일
- 기상 wind_dir_deg: 기상 표준(0=북풍·북에서 불어옴, 90=동풍)

개구부 face 레이블 → 로컬 법선(orientation=0 기준)
  'south' → 세계 (0, -1)   'north' → (0, +1)
  'east'  → (+1, 0)         'west'  → (-1, 0)
  'roof'  → (0,  0) [수직   사용하지 않음 — 별도 처리]

@phase active
"""
import math
from typing import Optional

# ── 물리 상수 ────────────────────────────────────────────────────────────────
Cd  = 0.60   # 개구부 방류계수 (discharge coefficient, windows/vents)
RHO = 1.20   # 공기 밀도 kg/m³ (20°C, 해면 기준)

# 풍압계수 기준값 (직사각형 온실 경험식, ASHRAE 2009)
Cp_WINDWARD = 0.60   # 풍상면(windward): 양압
Cp_LEEWARD  = 0.30   # 풍하면(leeward):  부압

# 로컬 face → 2D 단위 법선 (orientation_deg=0 기준, 외향)
# X=동, Y=북 지도 좌표계
_FACE_LOCAL_NORMAL = {
    'north': (0.0,  1.0),
    'south': (0.0, -1.0),
    'east':  (1.0,  0.0),
    'west':  (-1.0, 0.0),
}


def _rotate_2d(nx, ny, angle_deg_cw):
    """시계방향 angle_deg_cw 만큼 2D 벡터 회전 (지도 방위 기준)."""
    rad = math.radians(angle_deg_cw)
    cos_a, sin_a = math.cos(rad), math.sin(rad)
    return (nx * cos_a + ny * sin_a,
            -nx * sin_a + ny * cos_a)


def _world_normal(face: Optional[str], orientation_deg: float):
    """face 레이블 + orientation_deg → 세계 좌표 2D 법선 (단위벡터)."""
    local = _FACE_LOCAL_NORMAL.get(face or '')
    if local is None:
        return None  # 'roof' 등 수직면 제외
    return _rotate_2d(local[0], local[1], orientation_deg)


def _wind_from_vector(wind_dir_deg: float):
    """기상 풍향 → 풍원 방향 단위벡터 (from 방향, 기상 표준).

    wind_dir_deg=0  (북풍, 북에서 불어옴) → (0, 1) : 북쪽을 가리킴
    wind_dir_deg=90 (동풍)               → (1, 0)
    """
    rad = math.radians(wind_dir_deg)
    return (math.sin(rad), math.cos(rad))


def compute_natural_ventilation(
    vent_openings: list,
    wind_speed_ms: float,
    wind_dir_deg: float,
    orientation_deg: float = 0.0,
    volume_m3: float = 1.0,
    opening_pct: float = 100.0,
) -> dict:
    """개구부별 풍압 환기량 계산 (D1 핵심 함수).

    Parameters
    ----------
    vent_openings   : compute_capacity() 의 vent_openings[] 리스트
    wind_speed_ms   : 풍속 m/s
    wind_dir_deg    : 기상 표준 풍향 (0=북풍, 90=동풍, 180=남풍, 270=서풍)
    orientation_deg : 시설 방위각 (시계방향, 북 기준) — facility.geometry_3d.orientation_deg
    volume_m3       : 시설 체적 (ACH 환산용)
    opening_pct     : 개구부 개방률 0~100% (운영 상태 반영)

    Returns
    -------
    {
      'effective_ach'   : float,           # 자연환기 ACH (1/h)
      'inflow_m3h'      : float,
      'outflow_m3h'     : float,
      'openings'        : [                # 개구부별 상세
          {
            'id'         : str,
            'face'       : str,            # 로컬 face 레이블
            'world_face' : str,            # 세계좌표 방향 레이블
            'area_m2'    : float,
            'cp'         : float,          # 풍압계수 (양=풍상, 음=풍하)
            'flow_m3h'   : float,          # 시간당 통기량 (방향 무관 절대값)
            'direction'  : str,            # 'in' | 'out' | 'calm'
            'actuator_id': str | None,
          }
        ],
      'method'  : 'cp_pressure',
      'inputs'  : { wind_speed_ms, wind_dir_deg, orientation_deg, opening_pct },
    }
    """
    open_ratio = max(0.0, min(1.0, opening_pct / 100.0))
    wind_vec   = _wind_from_vector(wind_dir_deg)  # 풍원 방향 단위벡터

    results = []
    total_inflow_m3s  = 0.0
    total_outflow_m3s = 0.0

    for vo in vent_openings:
        face = vo.get('face')
        area = float(vo.get('area_m2') or 0.0) * open_ratio
        if area <= 0:
            results.append({**_null_opening(vo), 'direction': 'calm'})
            continue

        wn = _world_normal(face, orientation_deg)
        if wn is None:
            # 지붕 개구부 — 단순 고정 환기율 (풍속 비례, 방향 무관)
            flow_m3s = Cd * area * wind_speed_ms * 0.20  # 지붕계수 0.20
            results.append({
                'id':          vo.get('id'),
                'face':        face,
                'world_face':  'roof',
                'area_m2':     round(area, 3),
                'cp':          0.20,
                'flow_m3h':    round(flow_m3s * 3600, 1),
                'direction':   'mixed',
                'actuator_id': vo.get('actuator_id'),
            })
            total_inflow_m3s  += flow_m3s * 0.5
            total_outflow_m3s += flow_m3s * 0.5
            continue

        # 풍압계수: cos(α) = n · wind_from_vector  (내적)
        cos_alpha = wn[0] * wind_vec[0] + wn[1] * wind_vec[1]

        if cos_alpha > 1e-4:
            # 풍상면 — 양압, 내부로 유입
            cp        = Cp_WINDWARD * cos_alpha
            direction = 'in'
        elif cos_alpha < -1e-4:
            # 풍하면 — 부압(흡인), 내부에서 유출
            cp        = -Cp_LEEWARD * abs(cos_alpha)  # 음수
            direction = 'out'
        else:
            # 풍향과 평행 (90°) → 압력 거의 없음
            cp        = 0.0
            direction = 'calm'

        # Q = Cd · A · V · √|Cp|
        flow_m3s = Cd * area * wind_speed_ms * math.sqrt(abs(cp)) if cp != 0 else 0.0

        if direction == 'in':
            total_inflow_m3s  += flow_m3s
        elif direction == 'out':
            total_outflow_m3s += flow_m3s

        results.append({
            'id':          vo.get('id'),
            'face':        face,
            'world_face':  _label_world_face(wn),
            'area_m2':     round(area, 3),
            'cp':          round(cp, 3),
            'flow_m3h':    round(flow_m3s * 3600, 1),
            'direction':   direction,
            'actuator_id': vo.get('actuator_id'),
        })

    # 교차환기 유효량 = min(inflow, outflow) — 보존 법칙
    effective_m3s = min(total_inflow_m3s, total_outflow_m3s)
    effective_ach = (effective_m3s * 3600 / volume_m3) if volume_m3 > 0 else 0.0

    return {
        'effective_ach':  round(effective_ach, 2),
        'inflow_m3h':     round(total_inflow_m3s  * 3600, 1),
        'outflow_m3h':    round(total_outflow_m3s * 3600, 1),
        'openings':       results,
        'method':         'cp_pressure',
        'inputs': {
            'wind_speed_ms':   wind_speed_ms,
            'wind_dir_deg':    wind_dir_deg,
            'orientation_deg': orientation_deg,
            'opening_pct':     opening_pct,
        },
    }


def wind_biased_opening(vent_openings, wind_dir_deg, orientation_deg=0.0):
    """각 개구부의 풍향 기여도(0.0~1.0) 반환 — env_coordinator 명령 가중치용.

    windward 개구부 → 높은 비중(최대 1.0)
    leeward 개구부  → 낮은 비중(최소 0.0, 완전히 닫을 필요 없음 → 0.2 하한)

    반환: {actuator_id: weight_0_to_1}  (actuator_id가 없는 항목은 제외)
    """
    wind_vec = _wind_from_vector(wind_dir_deg)
    weights  = {}

    for vo in vent_openings:
        aid  = vo.get('actuator_id')
        if not aid:
            continue
        face = vo.get('face')
        wn   = _world_normal(face, orientation_deg)
        if wn is None:
            weights[aid] = 0.5  # 지붕: 중립
            continue

        cos_alpha = wn[0] * wind_vec[0] + wn[1] * wind_vec[1]
        # [-1, 1] → [0.2, 1.0]  (leeward 최소 20% 유지 — 과압 방지)
        weight = 0.2 + 0.8 * max(0.0, cos_alpha)
        # 동일 actuator에 여러 opening → 최대값 채택
        weights[aid] = max(weights.get(aid, 0.0), round(weight, 3))

    return weights


# ── 내부 헬퍼 ────────────────────────────────────────────────────────────────
def _null_opening(vo):
    return {
        'id':          vo.get('id'),
        'face':        vo.get('face'),
        'world_face':  vo.get('face'),
        'area_m2':     float(vo.get('area_m2') or 0),
        'cp':          0.0,
        'flow_m3h':    0.0,
        'actuator_id': vo.get('actuator_id'),
    }


def _label_world_face(wn):
    """세계좌표 법선 → 가장 가까운 방위 레이블."""
    nx, ny = wn
    if abs(ny) >= abs(nx):
        return 'north' if ny > 0 else 'south'
    return 'east' if nx > 0 else 'west'
