# coding=utf-8
"""
_profile_loader_mixin.py — ProfileLoaderMixin: _reload_profiles().
"""

import json

from aot.databases.models import Actions, GeoShape, Output
from aot.utils.database import db_retrieve_table_daemon

from aot.functions.utils.env_control.effect_functions import build_effect_model
from aot.functions.utils.env_control.group_expander import expand_group_commands
from aot.functions.utils.env_control.types import (
    ActuatorGroup, ActuatorProfile, CmdConstraints, ManualLockState,
)

from ._function_info import _FACILITY_SLOT_KIND, _KIND_CAPABILITIES

_K_PRIMARY = {
    'opening':      'K_OPENING_T',
    'cooler':       'K_COOLER_T',
    'heater':       'K_HEATER_T',
    'fogger':       'K_FOG_RH',
    'co2_injector': 'K_CO2_INJ',
    'shade':        'K_SHADE_T',
    'curtain':      'K_CURTAIN_T',
    'lighting':     'K_LIGHT_PPFD',
}


class ProfileLoaderMixin:
    """Mixin: actuator profile loading from facility, paired outputs, and manual actions."""

    def _reload_profiles(self):
        """Hybrid loader: facility-derived profiles + manual env_actuator action profiles.

        Order:
          1. If geo_facility_id_device_id is set → load GeoFacility, iterate
             facility.actuators and build ActuatorProfile per slot with GIS metadata.
          2. Scan actuator_paired Output devices.
          3. Iterate env_actuator Actions and build/merge profiles.
          4. Parse ActuatorGroup definitions from GeoFacility.groups.
          5. Remove followers from _profiles (coordinator only routes leaders).
        """
        profiles = []
        channel_map = {}
        by_id = {}  # actuator_id → profile
        n_facility = 0
        # D1/D2: 초기화 (통합 데이터 없을 때 빈 상태 유지)
        self._vent_openings            = []
        self._facility_orientation_deg = 0.0
        self._sensors_resolved         = []
        n_manual_new = 0
        n_manual_merged = 0

        # ── 1. Facility-driven profiles (B2: via get_facility_integration) ─────
        # Uses the same normalized payload as the B1 HTTP endpoint so that
        # G1-accurate vent areas (fittings-authoritative) and fitting-level
        # actuator bindings are automatically reflected here.
        facility_uuid = self.geo_facility_id_device_id or ''
        integ = None  # 섹션 4(그룹 파싱) 에서도 재사용
        if facility_uuid:
            from aot.aot_flask.geo.facility_integration import get_facility_integration
            from aot.aot_flask.geo.facility_geo_helpers import shape_azimuth_area

            try:
                integ, integ_err = get_facility_integration(facility_uuid)
            except Exception as _e:
                integ, integ_err = None, str(_e)

            if integ_err:
                self.logger.warning(
                    '_reload_profiles: integration load failed for "%s": %s',
                    facility_uuid, integ_err)
                integ = None

            if integ:
                # D1: 캐시 — 사이클마다 wind_biased_opening() 에 재사용
                self._vent_openings = integ.get('vent_openings') or []
                self._facility_orientation_deg = float(
                    ((integ.get('geometry_3d') or {}).get('orientation_deg')) or 0.0
                )
                # D2: 캐시 — _collect_internal() 에서 위치 가중 측정값 보완
                self._sensors_resolved = integ.get('sensors_resolved') or []

                capacity_meta_base = integ.get('capacity_meta') or {}
                capacity_meta = {
                    'volume_m3':   float(capacity_meta_base.get('volume_m3') or 0.0),
                    'u_effective': float(capacity_meta_base.get('u_effective') or 0.0),
                    'envelope_m2': float(capacity_meta_base.get('envelope_m2') or 0.0),
                    'vent_open_m2':      float(capacity_meta_base.get('vent_open_m2') or 0.0),
                    'vent_open_source':  capacity_meta_base.get('vent_open_source') or 'none',
                }
                gis_resolved = 0
                facility_name = integ.get('name') or facility_uuid
                actuators_list = integ.get('actuators_resolved') or []
                vent_source = capacity_meta.get('vent_open_source') or 'none'

                # 이슈 B: fittings 권위 모드에서는 vent_open_m2 균등 분할 fallback
                # 을 끈다 (이중 회계 방지). envelope-only 모드일 때만 균등 분할.
                if vent_source != 'fittings':
                    vent_slots = [
                        a for a in actuators_list
                        if a.get('kind') == 'opening' and a.get('slot_key')
                        and 'vent' in (a.get('slot_key') or '')
                    ]
                    vent_fallback_per_slot = (
                        (capacity_meta['vent_open_m2'] / len(vent_slots))
                        if vent_slots else 0.0)
                else:
                    vent_fallback_per_slot = 0.0

                # 이슈 C: GeoShape N+1 → 한 번에 bulk fetch.
                output_uuids_all = [ar.get('output_uuid') for ar in actuators_list
                                    if ar.get('output_uuid')]
                shape_lookup: dict = {}
                try:
                    if output_uuids_all:
                        shape_rows = GeoShape.query.filter(
                            GeoShape.device_id.in_(output_uuids_all)).all()
                        shape_lookup = {s.device_id: s for s in shape_rows}
                except Exception as exc:
                    self.logger.debug(
                        '_reload_profiles: GeoShape bulk fetch failed: %s', exc)

                for ar in actuators_list:
                    output_uuid = ar.get('output_uuid')
                    kind        = ar.get('kind')
                    if not output_uuid or not kind:
                        continue

                    # G1 area: use per-actuator vent_openings_area_m2 when > 0,
                    # otherwise fall back to envelope-derived estimates.
                    g1_area = float(ar.get('vent_openings_area_m2') or 0.0)
                    slot_key = ar.get('slot_key') or ''
                    if g1_area > 0:
                        area_m2 = g1_area
                    elif 'vent' in slot_key:
                        area_m2 = vent_fallback_per_slot
                    elif slot_key == 'thermal_curtain':
                        area_m2 = capacity_meta['envelope_m2']
                    elif slot_key == 'shade_curtain':
                        area_m2 = float(
                            (integ.get('computed') or {}).get('roof_m2') or 0.0)
                    else:
                        area_m2 = 0.0

                    # GIS azimuth: still resolved from GeoShape (fitting surface_normals
                    # require a coordinate-system convention not yet standardised here).
                    azimuth_deg = None
                    shape = shape_lookup.get(output_uuid)
                    if shape and shape.feature:
                        az_shp, ar_shp = shape_azimuth_area(shape.feature)
                        if az_shp is not None:
                            azimuth_deg = az_shp
                            gis_resolved += 1
                        if ar_shp is not None and ar_shp > 0 and area_m2 == 0.0:
                            # Only override area from GIS when integration produced 0.
                            area_m2 = ar_shp

                    effect_model = build_effect_model(kind, {})
                    profile = ActuatorProfile(
                        actuator_id=output_uuid,
                        kind=kind,
                        capabilities=ar.get('capabilities') or _KIND_CAPABILITIES.get(kind, []),
                        cost_fn=lambda env, pct, _c=5.0: _c,
                        response_sec=60.0,
                        safe_default=0.0,
                        manual_lock=ManualLockState(),
                        effect_model=effect_model,
                        cmd_constraints=CmdConstraints(),
                        geo_facility_id=facility_uuid,
                        slot_key=slot_key or None,
                        azimuth_deg=azimuth_deg,
                        area_m2=area_m2,
                        capacity_meta=capacity_meta,
                    )
                    profiles.append(profile)
                    by_id[output_uuid] = profile
                    channel_map[output_uuid] = 0
                    n_facility += 1

                self.logger.info(
                    '_reload_profiles: %d facility-derived actuator(s) from "%s" '
                    '(gis_resolved=%d/%d, vent_source=%s)',
                    n_facility, facility_name, gis_resolved, n_facility,
                    capacity_meta.get('vent_open_source', 'n/a'))

        # ── 2. actuator_paired Outputs (자동 발견) ────────────────────────────
        n_paired = 0
        try:
            from aot.aot_flask.geo.facility_geo_helpers import shape_azimuth_area
            from aot.outputs.actuator_paired import KIND_TO_PROFILE_KIND
            paired_outputs = Output.query.filter_by(output_type='actuator_paired').all()
        except Exception:
            paired_outputs = []
            KIND_TO_PROFILE_KIND = {}

        for out in paired_outputs:
            out_uuid = out.unique_id
            if out_uuid in by_id:
                continue

            try:
                from aot.databases.models import OutputChannel
                ch = OutputChannel.query.filter_by(output_id=out_uuid, channel=0).first()
                ch_opts = json.loads(ch.custom_options or '{}') if ch else {}
            except Exception:
                ch_opts = {}

            actuator_kind = ch_opts.get('actuator_kind') or 'side_vent'
            profile_kind = KIND_TO_PROFILE_KIND.get(actuator_kind)
            if not profile_kind:
                continue

            azimuth_deg = ch_opts.get('azimuth_deg')
            area_m2     = ch_opts.get('area_m2')
            cost        = float(ch_opts.get('cost', 5.0) or 5.0)
            k_override  = float(ch_opts.get('k_override', 0.0) or 0.0)

            if azimuth_deg is None or area_m2 is None:
                try:
                    shape = GeoShape.query.filter_by(device_id=out_uuid).first()
                except Exception:
                    shape = None
                if shape and shape.feature:
                    az_shp, ar_shp = shape_azimuth_area(shape.feature)
                    if azimuth_deg is None and az_shp is not None:
                        azimuth_deg = az_shp
                    if area_m2 is None and ar_shp is not None and ar_shp > 0:
                        area_m2 = ar_shp

            k = {}
            if k_override:
                k_key = _K_PRIMARY.get(profile_kind)
                if k_key:
                    k[k_key] = k_override

            effect_model = build_effect_model(profile_kind, k)
            profile = ActuatorProfile(
                actuator_id=out_uuid,
                kind=profile_kind,
                capabilities=_KIND_CAPABILITIES.get(profile_kind, []),
                cost_fn=lambda env, pct, _c=cost: _c,
                response_sec=60.0,
                safe_default=0.0,
                manual_lock=ManualLockState(),
                effect_model=effect_model,
                cmd_constraints=CmdConstraints(),
                slot_key='actuator_paired',
                azimuth_deg=azimuth_deg,
                area_m2=area_m2,
            )
            profiles.append(profile)
            by_id[out_uuid] = profile
            channel_map[out_uuid] = 0
            n_paired += 1

        if n_paired:
            self.logger.info(
                '_reload_profiles: %d paired-actuator output(s) auto-discovered', n_paired)

        # ── 3. Manual env_actuator actions (merge or append) ─────────────────
        actions = db_retrieve_table_daemon(Actions).filter(
            Actions.function_id == self.unique_id,
            Actions.action_type == 'env_actuator',
        ).all()

        for action in actions:
            try:
                opts = json.loads(action.custom_options or '{}')
            except Exception:
                continue

            output_val = opts.get('output', '')
            if not output_val:
                continue
            parts = str(output_val).split(',')
            device_id  = parts[0].strip() if parts else ''
            channel_id = parts[1].strip() if len(parts) > 1 else None

            kind = opts.get('kind', '') or ''
            cost = float(opts.get('cost', 5.0) or 5.0)
            k_override = float(opts.get('k_override', 0.0) or 0.0)

            if not device_id or not kind:
                continue

            ch_obj = 0
            if channel_id:
                try:
                    ch_obj = self.get_output_channel_from_channel_id(channel_id)
                except Exception:
                    ch_obj = 0

            k = {}
            if k_override:
                k_key = _K_PRIMARY.get(kind)
                if k_key:
                    k[k_key] = k_override

            effect_model = build_effect_model(kind, k)

            existing = by_id.get(device_id)
            if existing:
                existing.cost_fn = (lambda env, pct, _c=cost: _c)
                existing.effect_model = effect_model
                channel_map[device_id] = ch_obj
                n_manual_merged += 1
            else:
                profile = ActuatorProfile(
                    actuator_id=device_id,
                    kind=kind,
                    capabilities=_KIND_CAPABILITIES.get(kind, []),
                    cost_fn=lambda env, pct, _c=cost: _c,
                    response_sec=60.0,
                    safe_default=0.0,
                    manual_lock=ManualLockState(),
                    effect_model=effect_model,
                    cmd_constraints=CmdConstraints(),
                )
                profiles.append(profile)
                by_id[device_id] = profile
                channel_map[device_id] = ch_obj
                n_manual_new += 1

        # ── 4. P2-4: 복합 액추에이터 그룹 파싱 ───────────────────────────────────
        # 이슈 D: integ 페이로드의 groups + actuators_slot_map 을 사용하여
        # GeoFacility 재조회를 제거. integ 가 None 이면 그룹도 비어 있음.
        groups: list = []
        if facility_uuid and integ:
            try:
                fac_groups = integ.get('groups') or {}
                raw_acts   = integ.get('actuators_slot_map') or {}
                if isinstance(fac_groups, dict) and fac_groups:
                    for gid, gcfg in fac_groups.items():
                        mode        = gcfg.get('mode', 'symmetric')
                        leader_slot = gcfg.get('leader', '')
                        member_slots = gcfg.get('members', [leader_slot])
                        thr         = float(gcfg.get('threshold_pct', 50.0))
                        leader_id   = raw_acts.get(leader_slot, '')
                        member_ids  = [raw_acts.get(s, '') for s in member_slots
                                       if raw_acts.get(s, '')]
                        if leader_id and len(member_ids) >= 2:
                            groups.append(ActuatorGroup(
                                group_id=gid, mode=mode,
                                leader_id=leader_id, member_ids=member_ids,
                                threshold_pct=thr,
                            ))
                    if groups:
                        self.logger.info(
                            '_reload_profiles: %d 그룹 로드됨', len(groups))
            except Exception:
                self.logger.exception(
                    '_reload_profiles: 그룹 파싱 실패 — 그룹 없이 계속')

        self._groups = groups

        # ── 5. 팔로워 전용 프로파일 제거 (coordinator 는 리더만 처리) ─────────────
        follower_ids: set = set()
        for grp in groups:
            follower_ids.update(grp.follower_ids())
        leader_profiles = [p for p in profiles if p.actuator_id not in follower_ids]

        self._profiles    = leader_profiles
        self._channel_map = channel_map
        self._actuator_idx = {p.actuator_id: i for i, p in enumerate(leader_profiles)}
        self.logger.info(
            '_reload_profiles: total=%d (facility=%d, paired=%d, '
            'manual_new=%d, manual_merged=%d, groups=%d)',
            len(leader_profiles), n_facility, n_paired,
            n_manual_new, n_manual_merged, len(groups))
