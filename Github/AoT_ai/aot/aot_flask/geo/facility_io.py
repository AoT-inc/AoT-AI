# coding=utf-8
"""
Facility I/O Manager.
CRUD for GeoFacility records and their linked GeoShape outer/bay polygons.
"""
from datetime import datetime
from flask import current_app

from aot.databases.models import GeoShape, GeoFacility
from aot.aot_flask.extensions import db


class FacilityManager:
    """Manages GeoFacility records and their linked GeoShape polygons.

    Atomically synchronizes:
      - Outer polygon  → GeoShape (type='facility')
      - Facility specs → GeoFacility
      - Bay polygons   → GeoShape (type='facility_bay', parent_id=outer.id)

    @phase active
    """

    @staticmethod
    def list_facilities(geo_id=None, include_shape=True):
        """List facilities, optionally filtered by GeoMap unique_id.

        include_shape=True (default): outer_feature is attached so the map
        can render facility footprints + 3D extrusion without a second roundtrip.
        """
        try:
            query = GeoFacility.query
            if geo_id:
                query = query.filter_by(geo_id=geo_id)
            rows = query.order_by(GeoFacility.updated_at.desc()).all()
            return [FacilityManager._to_dict(r, include_shape=include_shape) for r in rows], None
        except Exception as e:
            current_app.logger.error(f"FacilityManager.list error: {e}")
            return None, str(e)

    @staticmethod
    def get_facility(facility_uuid):
        """Get one facility by unique_id with its outer polygon feature."""
        try:
            row = GeoFacility.query.filter_by(unique_id=facility_uuid).first()
            if not row:
                return None, "Facility not found"
            return FacilityManager._to_dict(row, include_shape=True), None
        except Exception as e:
            current_app.logger.error(f"FacilityManager.get error: {e}")
            return None, str(e)

    @staticmethod
    def save_facility(data, user_id=None):
        """Upsert facility (outer shape + spec + bay shapes) in one transaction.

        Payload keys:
          facility_uuid (optional) — present for update, absent for create
          geo_id (required)        — GeoMap.unique_id
          name, preset, structure, bay_count
          outer_geometry           — GeoJSON geometry of the outer polygon
          geometry_3d, envelope, actuators, computed, notes
          bays                     — list of {id, geometry, crop, sensor_zone, name}
        """
        facility_uuid = data.get('facility_uuid')
        geo_id = data.get('geo_id')
        outer_geometry = data.get('outer_geometry')
        bays_input = data.get('bays', []) or []
        site_shape_uuid = data.get('site_shape_uuid')

        if not geo_id:
            return None, "Missing geo_id"
        if not facility_uuid and not outer_geometry:
            return None, "Missing outer_geometry for new facility"

        # Resolve site → parent_id mapping (option Y: hierarchy via GeoShape.parent_id)
        parent_site_id = None
        if site_shape_uuid:
            site_shape = GeoShape.query.filter_by(
                unique_id=site_shape_uuid, type='site'
            ).first()
            if site_shape:
                parent_site_id = site_shape.id

        # Outer polygon feature builder (geo_shape.feature is NOT NULL)
        def _build_feature(geometry, name):
            return {
                'type': 'Feature',
                'geometry': geometry,
                'properties': {
                    'aot_type': 'facility',
                    'name': name or 'New Facility',
                }
            }

        try:
            # 1. Resolve or create facility + outer shape
            # Pattern: instantiate empty, set attrs, then add — matches geo_overlays.py
            # so SQLAlchemy reliably tracks JSON column writes before flush.
            if facility_uuid:
                facility = GeoFacility.query.filter_by(unique_id=facility_uuid).first()
                if not facility:
                    return None, "Facility not found"
                shape = GeoShape.query.filter_by(unique_id=facility.shape_uuid).first()
                if not shape:
                    if not outer_geometry:
                        return None, "Missing outer_geometry to recover deleted shape"
                    shape = GeoShape()
                    shape.type = 'facility'
                    shape.geo_id = geo_id
                    shape.feature = _build_feature(outer_geometry, data.get('name'))
                    db.session.add(shape)
                    db.session.flush()
                    current_app.logger.info(
                        f"[FacilityManager] auto-recovered shape {shape.unique_id} "
                        f"for facility {facility_uuid}"
                    )
            else:
                facility = GeoFacility()
                shape = GeoShape()
                shape.type = 'facility'
                shape.geo_id = geo_id
                shape.feature = _build_feature(outer_geometry, data.get('name'))
                db.session.add(shape)
                db.session.flush()
                current_app.logger.info(
                    f"[FacilityManager] created new shape {shape.unique_id} "
                    f"(geo_id={geo_id}, has_geometry={outer_geometry is not None})"
                )

            # Defensive: feature must never be None at this point
            if shape.feature is None:
                shape.feature = _build_feature(outer_geometry or {}, data.get('name'))

            # 2. Update outer polygon feature on existing shape (if geometry provided)
            if outer_geometry:
                shape.feature = _build_feature(outer_geometry, data.get('name'))
            shape.geo_id = geo_id
            shape.updated_at = datetime.utcnow()

            # Apply site hierarchy: only overwrite parent_id when explicitly sent.
            # `site_shape_uuid` absent in payload → keep existing parent_id (do nothing).
            # `site_shape_uuid` empty string → clear parent_id (user de-selected site).
            if 'site_shape_uuid' in data:
                shape.parent_id = parent_site_id  # None when uuid is empty/invalid

            # 3. Facility spec
            facility.shape_uuid = shape.unique_id
            facility.geo_id = geo_id
            facility.name = data.get('name', facility.name or 'New Facility')
            facility.preset = data.get('preset', 'standard_arch')
            facility.structure = data.get('structure', 'single')
            facility.bay_count = data.get('bay_count', 1)
            facility.geometry_3d = data.get('geometry_3d')
            facility.envelope = data.get('envelope')
            facility.actuators = data.get('actuators')
            facility.computed = data.get('computed')
            facility.notes = data.get('notes', '')
            facility.updated_at = datetime.utcnow()
            if user_id and not facility.created_by:
                facility.created_by = str(user_id)

            if facility.id is None:
                db.session.add(facility)
            db.session.flush()

            # 4. Rebuild bay shapes (connected only)
            outer_shape_id = shape.id
            old_bays = GeoShape.query.filter_by(
                geo_id=geo_id, type='facility_bay', parent_id=outer_shape_id
            ).all()
            for ob in old_bays:
                db.session.delete(ob)

            bays_meta = []
            if facility.structure == 'connected' and bays_input:
                for bay in bays_input:
                    bay_geom = bay.get('geometry')
                    if not bay_geom:
                        continue
                    bay_shape = GeoShape(
                        type='facility_bay',
                        geo_id=geo_id,
                        parent_id=outer_shape_id,
                        feature={
                            'type': 'Feature',
                            'geometry': bay_geom,
                            'properties': {
                                'aot_type': 'facility_bay',
                                'crop': bay.get('crop'),
                                'name': bay.get('name'),
                            }
                        }
                    )
                    db.session.add(bay_shape)
                    db.session.flush()
                    bays_meta.append({
                        'id': bay.get('id'),
                        'polygon_shape_uuid': bay_shape.unique_id,
                        'crop': bay.get('crop'),
                        'sensor_zone': bay.get('sensor_zone', []),
                        'name': bay.get('name'),
                    })
            elif facility.structure == 'single':
                bays_meta = [{
                    'id': 'main',
                    'polygon_shape_uuid': shape.unique_id,
                    'crop': data.get('crop'),
                    'sensor_zone': data.get('sensor_zone', []),
                    'name': data.get('name'),
                }]

            facility.bays = bays_meta

            db.session.commit()
            return {
                'ok': True,
                'facility_uuid': facility.unique_id,
                'shape_uuid': shape.unique_id,
                'bays': bays_meta,
            }, None

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"FacilityManager.save error: {e}")
            return None, str(e)

    @staticmethod
    def delete_facility(facility_uuid, confirm_name=None):
        """Delete a facility — Constitution Art.5 confirmation enforced.

        Removes GeoFacility, outer GeoShape, and all bay shapes
        (parent_id=outer.id, type='facility_bay').
        """
        try:
            facility = GeoFacility.query.filter_by(unique_id=facility_uuid).first()
            if not facility:
                return None, "Facility not found"

            if confirm_name is None or confirm_name != facility.name:
                return None, (
                    f"Confirmation required: reply with exact facility name "
                    f"'{facility.name}' to delete."
                )

            shape = GeoShape.query.filter_by(unique_id=facility.shape_uuid).first()
            if shape:
                bays = GeoShape.query.filter_by(parent_id=shape.id, type='facility_bay').all()
                for b in bays:
                    db.session.delete(b)
                db.session.delete(shape)

            db.session.delete(facility)
            db.session.commit()
            return {'ok': True, 'deleted': facility_uuid}, None
        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f"FacilityManager.delete error: {e}")
            return None, str(e)

    @staticmethod
    def _to_dict(f, include_shape=False):
        d = {
            'unique_id': f.unique_id,
            'shape_uuid': f.shape_uuid,
            'geo_id': f.geo_id,
            'name': f.name,
            'preset': f.preset,
            'structure': f.structure,
            'bay_count': f.bay_count,
            'geometry_3d': f.geometry_3d,
            'envelope': f.envelope,
            'actuators': f.actuators,
            'bays': f.bays,
            'computed': f.computed,
            'notes': f.notes,
            'created_at': f.created_at.isoformat() if f.created_at else None,
            'updated_at': f.updated_at.isoformat() if f.updated_at else None,
        }
        if include_shape and f.shape is not None:
            d['outer_feature'] = f.shape.feature
            d['parent_id'] = f.shape.parent_id
            # Resolve parent site (option Y) for client-side selector restore
            if f.shape.parent_id:
                site_shape = GeoShape.query.filter_by(id=f.shape.parent_id).first()
                if site_shape and site_shape.type == 'site':
                    d['parent_site_uuid'] = site_shape.unique_id
                    site_props = (site_shape.feature or {}).get('properties', {}) if isinstance(site_shape.feature, dict) else {}
                    d['parent_site_name'] = site_props.get('name', '')
        return d
