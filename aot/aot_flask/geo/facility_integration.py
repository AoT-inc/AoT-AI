# coding=utf-8
"""
facility_integration.py — get_facility_integration(): shared IEC integration helper.

Called by:
  - routes_geo.py  → GET /api/geo/facility/<uuid>/integration  (B1 HTTP endpoint)
  - _profile_loader_mixin.py → _reload_profiles() section 1   (B2 profile builder)

Returns the same normalized dict in both contexts so the HTTP route is just a thin
JSON wrapper around this function.
"""
from aot.databases.models import Output, Input
from .facility_io import FacilityManager
from .facility_calc import compute_capacity

# Fitting.kind → ActuatorProfile.kind 추론 (slot_key 미설정 시 fallback).
# 모호한 케이스(fan: circulation/exhaust/intake)는 None 으로 두어
# 로더가 slot 또는 명시 actuator_kind 를 사용하도록 한다.
_FITTING_KIND_TO_ACTUATOR_KIND = {
    'window':      'opening',
    'side_window': 'opening',
    'door':        'opening',
    'curtain':     'curtain',
}


def get_facility_integration(facility_uuid):
    """Build the unified IEC payload for *facility_uuid*.

    Returns ``(result_dict, error_str)``.  On success ``error_str`` is None.

    result_dict keys
    ----------------
    facility_uuid, name, geometry_3d, envelope, fittings,
    actuators_resolved, sensors_resolved, vent_openings, capacity_meta, computed.

    actuators_resolved
    ------------------
    One entry per Output uuid (union of slot_map + fitting.actuator_id bindings):
      output_uuid, output_name, output_type, slot_key, kind, capabilities,
      fitting_ids[], vent_openings_area_m2, vent_openings_count.

    G1 policy: vent area in vent_openings_area_m2 is derived from fittings when
    fittings are present; computed.vent_open_source indicates the authority.
    """
    # Lazy import to avoid circular dependency at module load time.
    from aot.functions.custom_functions.env_coordinator_impl._function_info import (
        _FACILITY_SLOT_KIND, _KIND_CAPABILITIES,
    )

    facility, error = FacilityManager.get_facility(facility_uuid)
    if error:
        return None, error

    fittings_raw = facility.get('fittings') or []
    fittings = fittings_raw if isinstance(fittings_raw, list) else []
    slot_map_raw = facility.get('actuators')
    slot_map = slot_map_raw if isinstance(slot_map_raw, dict) else {}

    # --- 1. Compute capacity (authoritative numbers + vent_openings per G1) ---
    spec_for_calc = {
        'outer_geometry': (facility.get('outer_feature') or {}).get('geometry'),
        'bay_count':   facility.get('bay_count') or 1,
        'structure':   facility.get('structure') or 'single',
        'geometry_3d': facility.get('geometry_3d') or {},
        'envelope':    facility.get('envelope') or {},
        'actuators':   slot_map,
        'fittings':    fittings,
    }
    try:
        computed = compute_capacity(spec_for_calc)
    except Exception:
        computed = {}

    # --- 2. Resolve Output devices (single bulk query) ---
    output_uuids = set()
    for u in slot_map.values():
        if u:
            output_uuids.add(u)
    for f in fittings:
        if f.get('actuator_id'):
            output_uuids.add(f['actuator_id'])

    out_rows = (Output.query.filter(Output.unique_id.in_(output_uuids)).all()
                if output_uuids else [])
    out_lookup = {r.unique_id: r for r in out_rows}

    # --- 3. Build actuators_resolved ---
    # First pass: slot_map entries carry the authoritative slot_key → kind mapping.
    actuators_resolved = {}
    for slot_key, output_uuid in slot_map.items():
        if not output_uuid:
            continue
        kind = _FACILITY_SLOT_KIND.get(slot_key)
        row = out_lookup.get(output_uuid)
        actuators_resolved[output_uuid] = {
            'output_uuid':           output_uuid,
            'output_name':           (row.name if row else None) or 'Output',
            'output_type':           (row.output_type if row else ''),
            'slot_key':              slot_key,
            'kind':                  kind,
            'capabilities':          _KIND_CAPABILITIES.get(kind, []) if kind else [],
            'fitting_ids':           [],
            'vent_openings_area_m2': 0.0,
            'vent_openings_count':   0,
        }

    # Index vent_openings by actuator_id for fast area aggregation.
    vent_openings = computed.get('vent_openings') or []
    openings_by_actuator = {}
    for op in vent_openings:
        aid = op.get('actuator_id')
        if aid:
            openings_by_actuator.setdefault(aid, []).append(op)

    # Second pass: attach fitting ids; synthesize slot-less Output entries.
    # G1 정책: slot_key 가 없어도 fitting.kind 로부터 ActuatorProfile.kind 를
    # 추론할 수 있으면 채워서 로더가 등록할 수 있도록 한다.
    for f in fittings:
        aid = f.get('actuator_id')
        if not aid:
            continue
        if aid not in actuators_resolved:
            row = out_lookup.get(aid)
            inferred_kind = _FITTING_KIND_TO_ACTUATOR_KIND.get(f.get('kind'))
            actuators_resolved[aid] = {
                'output_uuid':           aid,
                'output_name':           (row.name if row else None) or 'Output',
                'output_type':           (row.output_type if row else ''),
                'slot_key':              None,
                'kind':                  inferred_kind,
                'capabilities':          (_KIND_CAPABILITIES.get(inferred_kind, [])
                                          if inferred_kind else []),
                'fitting_ids':           [],
                'vent_openings_area_m2': 0.0,
                'vent_openings_count':   0,
            }
        else:
            # 이미 slot 으로 등록된 액추에이터에 추가 fitting 이 붙은 경우 —
            # kind 가 None 이면 fitting kind 로 보강.
            entry = actuators_resolved[aid]
            if not entry.get('kind'):
                inferred = _FITTING_KIND_TO_ACTUATOR_KIND.get(f.get('kind'))
                if inferred:
                    entry['kind'] = inferred
                    entry['capabilities'] = _KIND_CAPABILITIES.get(inferred, [])
        actuators_resolved[aid]['fitting_ids'].append(f.get('id'))

    # Third pass: aggregate vent area per actuator from G1-resolved vent_openings.
    for aid, ops in openings_by_actuator.items():
        if aid in actuators_resolved:
            actuators_resolved[aid]['vent_openings_area_m2'] = round(
                sum(o['area_m2'] for o in ops), 3)
            actuators_resolved[aid]['vent_openings_count'] = len(ops)

    # --- 4. Resolve sensors_resolved ---
    sensor_fittings = [f for f in fittings if f.get('kind') == 'sensor']
    input_uuids = {f['input_id'] for f in sensor_fittings if f.get('input_id')}
    inp_rows = (Input.query.filter(Input.unique_id.in_(input_uuids)).all()
                if input_uuids else [])
    inp_lookup = {r.unique_id: r for r in inp_rows}

    sensors_resolved = []
    for f in sensor_fittings:
        iid = f.get('input_id')
        row = inp_lookup.get(iid) if iid else None
        sensors_resolved.append({
            'fitting_id':   f.get('id'),
            'name':         f.get('name') or '',
            'position':     f.get('position'),
            'input_uuid':   iid,
            'input_name':   (row.name if row else None),
            'input_device': (row.device if row else None),
        })

    # --- 5. Capacity-meta summary ---
    capacity_meta = {
        'volume_m3':             computed.get('volume_m3'),
        'envelope_m2':           computed.get('envelope_m2'),
        'u_effective':           computed.get('u_effective'),
        'transmittance':         computed.get('transmittance'),
        'vent_open_m2':          computed.get('vent_open_m2'),
        'vent_open_source':      computed.get('vent_open_source'),
        'vent_open_fittings_m2': computed.get('vent_open_fittings_m2'),
        'vent_open_envelope_m2': computed.get('vent_open_envelope_m2'),
    }

    # actuators_slot_map / groups: 그룹 파서가 두 번 DB 를 치지 않도록
    # raw 슬롯 매핑과 그룹 정의를 같이 실어 보낸다.
    groups_raw = facility.get('groups')
    return {
        'facility_uuid':       facility_uuid,
        'name':                facility.get('name'),
        'geometry_3d':         facility.get('geometry_3d'),
        'envelope':            facility.get('envelope'),
        'fittings':            fittings,
        'actuators_resolved':  list(actuators_resolved.values()),
        'actuators_slot_map':  dict(slot_map),
        'sensors_resolved':    sensors_resolved,
        'vent_openings':       vent_openings,
        'capacity_meta':       capacity_meta,
        'groups':              groups_raw if isinstance(groups_raw, dict) else {},
        'computed':            computed,
    }, None
