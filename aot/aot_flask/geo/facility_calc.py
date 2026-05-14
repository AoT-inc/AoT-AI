# coding=utf-8
"""
Facility Capacity Calculator (PRD/DESIGN-GEO-FACILITY-001).

1차 산정 참고치 (±5~10%) — 기계설비 견적 단계용 reference values.
정밀 설계용이 아니며, 작물·지역·단열재 세부 정보 추가 시 정확도 향상 가능(차기).

@phase active
"""
import math
import logging

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------
# Material thermal/optical properties (DESIGN §5-1)
# ----------------------------------------------------------------
MATERIALS = {
    'vinyl_single':     {'u': 6.0, 'transmittance': 0.85},
    'vinyl_double':     {'u': 4.0, 'transmittance': 0.78},
    'po_film':          {'u': 6.5, 'transmittance': 0.85},
    'polycarbonate':    {'u': 3.0, 'transmittance': 0.78},
    'glass':            {'u': 5.8, 'transmittance': 0.85},
    'non_woven_fabric': {'u': 3.5, 'transmittance': 0.50},
    'pe_film':          {'u': 6.5, 'transmittance': 0.85},
    'air_cushion':      {'u': 2.8, 'transmittance': 0.75},
}
DEFAULT_MATERIAL = 'vinyl_double'

# ----------------------------------------------------------------
# Reference assumptions — PoC defaults, replaceable per-facility later
# ----------------------------------------------------------------
ASSUMPTIONS = {
    'delta_T_heating_K':     20.0,   # 외기-내부 온도차(한겨울 가정)
    'delta_T_cooling_K':     10.0,   # 한여름 가정
    'solar_radiation_W_m2':  500.0,  # 평균 일사
    'transpiration_W_m2':    100.0,  # 작물 증산 부하
    'r_airgap_m2K_W':        0.18,   # 정지 공기층 열저항
    'wind_factor_m_s':       1.5,    # 자연환기 환산 풍속
    'fan_default_m3h':       5000.0, # 매핑된 팬 1대 표준 용량
    'vent_height_m':         1.2,    # 측창 표준 높이
    'vent_length_ratio':     0.8,    # 측면 길이 대비 측창 길이 비
    'roof_vent_width_m':     0.8,    # 천창 표준 폭
}


# ----------------------------------------------------------------
# Geometry helpers — local equirectangular projection (small site)
# ----------------------------------------------------------------
def polygon_area_m2(geometry):
    """(Multi)Polygon area in square meters using local meter projection."""
    if not geometry:
        return 0.0
    gt = geometry.get('type')
    if gt == 'Polygon':
        rings = geometry.get('coordinates') or []
        return _ring_area_m2(rings[0]) if rings else 0.0
    if gt == 'MultiPolygon':
        polys = geometry.get('coordinates') or []
        total = 0.0
        for poly in polys:
            if poly:
                total += _ring_area_m2(poly[0])
        return total
    return 0.0


def polygon_perimeter_m(geometry):
    """(Multi)Polygon outer-ring perimeter in meters (sum across parts)."""
    if not geometry:
        return 0.0
    gt = geometry.get('type')
    if gt == 'Polygon':
        rings = geometry.get('coordinates') or []
        return _ring_perimeter_m(rings[0]) if rings else 0.0
    if gt == 'MultiPolygon':
        polys = geometry.get('coordinates') or []
        total = 0.0
        for poly in polys:
            if poly:
                total += _ring_perimeter_m(poly[0])
        return total
    return 0.0


def _ring_area_m2(coords):
    if len(coords) < 3:
        return 0.0
    lat0 = sum(c[1] for c in coords) / len(coords)
    m_per_deg_lat = 111320.0
    m_per_deg_lng = m_per_deg_lat * math.cos(math.radians(lat0))
    pts = [(c[0] * m_per_deg_lng, c[1] * m_per_deg_lat) for c in coords]
    s = 0.0
    n = len(pts)
    for i in range(n - 1):
        s += pts[i][0] * pts[i+1][1] - pts[i+1][0] * pts[i][1]
    return abs(s) / 2.0


def _ring_perimeter_m(coords):
    if len(coords) < 2:
        return 0.0
    lat0 = sum(c[1] for c in coords) / len(coords)
    m_per_deg_lat = 111320.0
    m_per_deg_lng = m_per_deg_lat * math.cos(math.radians(lat0))
    p = 0.0
    for i in range(len(coords) - 1):
        dx = (coords[i+1][0] - coords[i][0]) * m_per_deg_lng
        dy = (coords[i+1][1] - coords[i][1]) * m_per_deg_lat
        p += math.sqrt(dx*dx + dy*dy)
    return p


def arch_section_area(span, rise):
    """Cross-section area of an arch roof modeled as half-ellipse (m²)."""
    a = span / 2.0
    b = max(rise, 0.0)
    return math.pi * a * b / 2.0


def arch_section_perimeter(span, rise):
    """Arc length of half-ellipse arch (m). Ramanujan approximation, halved."""
    a = span / 2.0
    b = max(rise, 0.0)
    if a <= 0 or b <= 0:
        return float(span)
    full = math.pi * (3*(a+b) - math.sqrt((3*a+b) * (a+3*b)))
    return full / 2.0


def roof_section_area(roof_type, span, rise):
    """Roof cross-section area dispatched by roof_type.

    arch  → half-ellipse: π·(span/2)·rise / 2
    gable → triangle:     span × rise / 2
    flat  → 0 (no extra height above eave)
    """
    rt = (roof_type or 'arch').lower()
    if rt == 'gable':
        return float(span) * max(rise, 0.0) / 2.0
    if rt == 'flat':
        return 0.0
    return arch_section_area(span, rise)


def roof_section_perimeter(roof_type, span, rise):
    """Roof surface length (along cross-section) dispatched by roof_type.

    arch  → half-ellipse arc length (Ramanujan)
    gable → 2 × √((span/2)² + rise²)  (two slopes of an isoceles triangle)
    flat  → span (flat top equals the span)
    """
    rt = (roof_type or 'arch').lower()
    if rt == 'gable':
        a = span / 2.0
        return 2.0 * math.sqrt(a*a + max(rise, 0.0)**2)
    if rt == 'flat':
        return float(span)
    return arch_section_perimeter(span, rise)


# ----------------------------------------------------------------
# Effective envelope properties (single vs double layer)
# ----------------------------------------------------------------
def effective_u(layer_count, outer_material, inner_material=None, r_airgap=None):
    """U_eff (W/m²K). Double layer: 1 / (1/U_o + R_gap + 1/U_i)."""
    u_outer = MATERIALS.get(outer_material, MATERIALS[DEFAULT_MATERIAL])['u']
    if int(layer_count or 1) != 2 or not inner_material:
        return u_outer
    u_inner = MATERIALS.get(inner_material, MATERIALS[DEFAULT_MATERIAL])['u']
    r_gap = r_airgap if r_airgap is not None else ASSUMPTIONS['r_airgap_m2K_W']
    r_total = 1.0/u_outer + r_gap + 1.0/u_inner
    return 1.0 / r_total


def effective_transmittance(layer_count, outer_material, inner_material=None):
    """Multiplicative transmittance for stacked layers."""
    t_outer = MATERIALS.get(outer_material, MATERIALS[DEFAULT_MATERIAL])['transmittance']
    if int(layer_count or 1) != 2 or not inner_material:
        return t_outer
    t_inner = MATERIALS.get(inner_material, MATERIALS[DEFAULT_MATERIAL])['transmittance']
    return t_outer * t_inner


# ----------------------------------------------------------------
# Main entry
# ----------------------------------------------------------------
def compute_capacity(spec):
    """Compute reference capacity from a facility spec dict.

    Returns dict of m²/m³/kW/ACH values plus a `_note` disclaimer.
    Falls back to dimensional estimate if outer_geometry missing.
    """
    geom_3d = spec.get('geometry_3d') or {}
    envelope = spec.get('envelope') or {}
    actuators = spec.get('actuators') or {}
    bay_count = max(int(spec.get('bay_count') or 1), 1)
    structure = spec.get('structure') or 'single'

    # ---- 1. Footprint ----
    footprint = spec.get('outer_geometry')
    floor_m2 = polygon_area_m2(footprint)
    perimeter_m = polygon_perimeter_m(footprint)

    span      = float(geom_3d.get('span_width_m') or 7)
    eave_h    = float(geom_3d.get('eave_height_m') or 2)
    ridge_h   = float(geom_3d.get('ridge_height_m') or 4)
    length    = float(geom_3d.get('length_m') or 30)
    spacing   = float(geom_3d.get('spacing_m') or 0)
    roof_type = (geom_3d.get('roof_type') or 'arch')
    rise      = max(ridge_h - eave_h, 0.0)

    if floor_m2 <= 0:
        if structure == 'connected':
            effective_span = span * bay_count
            floor_m2 = effective_span * length
            perimeter_m = 2 * (effective_span + length)
        else:
            # single (1 bay) OR detached single+bays row
            floor_m2 = (span * length) * bay_count
            perimeter_m = (2 * (span + length)) * bay_count

    bay_mul = max(int(bay_count or 1), 1)

    # ---- 2. Envelope decomposition (roof_type aware) ----
    roof_arc  = roof_section_perimeter(roof_type, span, rise)
    roof_sect = roof_section_area(roof_type, span, rise)

    # roof_runs = number of roof ridge lines along `length`
    # connected: one continuous envelope but bays still each have their own roof ridge
    # single (1 or N bays): each detached bay has its own roof
    roof_runs = bay_mul

    # gables (end walls):
    #   connected: 2 (only the two ends of the joined envelope)
    #   single + N detached bays: 2 per bay = 2N
    if structure == 'connected':
        gable_count = 2
    else:
        gable_count = 2 * bay_mul

    sidewall_m2 = perimeter_m * eave_h
    roof_m2     = roof_arc * length * roof_runs
    gable_m2    = roof_sect * gable_count
    envelope_m2 = sidewall_m2 + roof_m2 + gable_m2

    # ---- 3. Volume ----
    roof_vol_per_bay = roof_sect * length
    volume_m3 = floor_m2 * eave_h + roof_vol_per_bay * roof_runs

    # ---- 4. U_eff & transmittance ----
    layer_count = int(envelope.get('layer_count') or 1)
    outer = envelope.get('outer') or {}
    inner = envelope.get('inner') or {}
    outer_mat = outer.get('cover_material') or DEFAULT_MATERIAL
    inner_mat = inner.get('cover_material')
    air_gap   = inner.get('air_gap_m')

    u_eff = effective_u(layer_count, outer_mat, inner_mat, r_airgap=None)
    t_eff = effective_transmittance(layer_count, outer_mat, inner_mat)

    # ---- 5. Vent open area ----
    side_len = max(length, 0.0)
    vent_open_m2 = 0.0
    o_side = (outer.get('side_vent') or {})
    o_roof = (outer.get('roof_vent') or {})
    if o_side.get('enabled'):
        vent_open_m2 += 2 * side_len * ASSUMPTIONS['vent_height_m'] * ASSUMPTIONS['vent_length_ratio']
    if o_roof.get('enabled'):
        vent_open_m2 += side_len * ASSUMPTIONS['roof_vent_width_m'] * bay_mul

    if layer_count == 2:
        i_side = (inner.get('side_vent') or {})
        i_roof = (inner.get('roof_vent') or {})
        # independent inner vents add additional opening; synced share outer's
        if i_side.get('enabled') and i_side.get('control_mode') == 'independent':
            vent_open_m2 += 2 * side_len * ASSUMPTIONS['vent_height_m'] * ASSUMPTIONS['vent_length_ratio']
        if i_roof.get('enabled') and i_roof.get('control_mode') == 'independent':
            vent_open_m2 += side_len * ASSUMPTIONS['roof_vent_width_m'] * bay_mul

    # ---- 6. Glazing — assume transparent envelope (greenhouse PoC) ----
    glazing_m2 = envelope_m2

    # ---- 7. Heating load (kW) ----
    heating_kw = envelope_m2 * u_eff * ASSUMPTIONS['delta_T_heating_K'] / 1000.0

    # ---- 8. Cooling load (kW) ----
    cooling_W = (roof_m2 * ASSUMPTIONS['solar_radiation_W_m2'] * t_eff
                 + floor_m2 * ASSUMPTIONS['transpiration_W_m2'])
    cooling_kw = cooling_W / 1000.0

    # ---- 9. ACH ----
    ach_natural = 0.0
    if volume_m3 > 0 and vent_open_m2 > 0:
        ach_natural = (vent_open_m2 * ASSUMPTIONS['wind_factor_m_s'] / volume_m3) * 3600.0

    forced_m3h = 0.0
    for fan_key in ('circulation_fan', 'exhaust_fan'):
        if actuators.get(fan_key):
            forced_m3h += ASSUMPTIONS['fan_default_m3h']
    ach_forced = (forced_m3h / volume_m3) if volume_m3 > 0 else 0.0
    ach_total = ach_natural + ach_forced

    return {
        'floor_m2':       round(floor_m2, 2),
        'envelope_m2':    round(envelope_m2, 2),
        'sidewall_m2':    round(sidewall_m2, 2),
        'roof_m2':        round(roof_m2, 2),
        'gable_m2':       round(gable_m2, 2),
        'volume_m3':      round(volume_m3, 2),
        'glazing_m2':     round(glazing_m2, 2),
        'vent_open_m2':   round(vent_open_m2, 2),
        'u_effective':    round(u_eff, 3),
        'transmittance':  round(t_eff, 3),
        'heating_kw':     round(heating_kw, 2),
        'cooling_kw':     round(cooling_kw, 2),
        'ach_natural':    round(ach_natural, 2),
        'ach_forced':     round(ach_forced, 2),
        'ach_total':      round(ach_total, 2),
        'ach_m3h':        round(ach_total * volume_m3, 0) if volume_m3 else 0,
        '_note':          '1차 산정 참고치 (±5~10%)',
    }


# ----------------------------------------------------------------
# Self-check (run: python facility_calc.py)
# ----------------------------------------------------------------
if __name__ == '__main__':
    standard_single = {
        'structure': 'single',
        'bay_count': 1,
        'geometry_3d': {
            'span_width_m': 7, 'eave_height_m': 2, 'ridge_height_m': 4,
            'length_m': 30, 'roof_type': 'arch'
        },
        'envelope': {
            'layer_count': 1,
            'outer': {'cover_material': 'vinyl_double',
                      'side_vent': {'enabled': True},
                      'roof_vent': {'enabled': False}},
            'inner': None,
            'curtain': {'thermal': False, 'shade': False},
        },
        'actuators': {'circulation_fan': 'fake-output-uuid'},
    }

    standard_double = dict(standard_single)
    standard_double['envelope'] = {
        'layer_count': 2,
        'outer': {'cover_material': 'vinyl_double',
                  'side_vent': {'enabled': True},
                  'roof_vent': {'enabled': False}},
        'inner': {'cover_material': 'non_woven_fabric',
                  'air_gap_m': 0.5,
                  'side_vent': {'enabled': True, 'control_mode': 'synced'},
                  'roof_vent': {'enabled': False, 'control_mode': 'synced'}},
        'curtain': {'thermal': False, 'shade': False},
    }

    print("=== Standard greenhouse (7m × 30m, single layer vinyl_double) ===")
    r1 = compute_capacity(standard_single)
    for k, v in r1.items():
        print(f"  {k:18} {v}")

    print("\n=== Same, double layer (vinyl_double + non_woven_fabric) ===")
    r2 = compute_capacity(standard_double)
    for k, v in r2.items():
        print(f"  {k:18} {v}")

    ratio = r2['heating_kw'] / r1['heating_kw'] if r1['heating_kw'] else 0
    print(f"\nHeating load ratio (double / single): {ratio:.2f}  (target ≈ 0.55~0.65)")
