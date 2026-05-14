# coding=utf-8
"""
Geo Domain Models.
Unifies MapConfig, MapOverlay, MapGlobalSettings, and GIS Inputs under the 'Geo' domain.
"""
from datetime import datetime
import json
from sqlalchemy import JSON
from aot.databases import CRUDMixin, set_uuid
from aot.aot_flask.extensions import db

# ------------------------------------------------------------------------------
# GeoMap (Previously MapConfig)
# Represents a saved map view/instance.
# ------------------------------------------------------------------------------
class GeoMap(CRUDMixin, db.Model):
    """
    Represents a saved map view or instance in the Geo domain.

    GeoMap stores map provider settings, center/zoom state, API keys, and styling
    options. Devices can optionally own a map for dedicated display. Supports OSM
    and satellite tile providers.

    @phase active
    """
    __tablename__ = "geo_map"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, unique=True, primary_key=True)
    unique_id = db.Column(db.String(36), nullable=False, unique=True, default=set_uuid)
    name = db.Column(db.String(128), nullable=False, default='New Map')
    category = db.Column(db.String(64), nullable=True, index=True, default='design')
    sort_order = db.Column(db.Integer, default=0)

    # Center/zoom
    latitude = db.Column(db.Float, default=None)
    longitude = db.Column(db.Float, default=None)
    zoom = db.Column(db.Integer, default=12)
    is_device_owned = db.Column(db.Boolean, default=False)

    # Provider details
    provider = db.Column(db.String(32), default='osm')
    style_url = db.Column(db.Text, default='')
    api_key = db.Column(db.Text, default='')
    use_satellite = db.Column(db.Boolean, default=False)
    providers = db.Column(db.Text, default='{}')
    state_json = db.Column(db.Text, default='{}')

    # Interaction
    map_locked = db.Column(db.Boolean, default=False)

    # Audit
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.String(36), default='')

    def __repr__(self):
        return "<GeoMap(id={0}, name='{1}')>".format(self.id, self.name)

    def state_dict(self):
        if not self.state_json:
            return {}
        try:
            value = json.loads(self.state_json)
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def update_state(self, updates):
        if not updates:
            return False
        state = self.state_dict()
        changed = False
        for key, value in updates.items():
            if value is None:
                continue
            if state.get(key) == value:
                continue
            state[key] = value
            changed = True
        if changed:
            try:
                self.state_json = json.dumps(state, ensure_ascii=False)
            except Exception:
                self.state_json = json.dumps(state)
        return changed


# ------------------------------------------------------------------------------
# GeoSetting (Previously MapGlobalSettings)
# Global configurations for the Geo system.
# ------------------------------------------------------------------------------
class GeoSetting(CRUDMixin, db.Model):
    """
    Singleton global configuration record for the Geo mapping system.

    GeoSetting stores default provider credentials, zoom limits, tile animation
    preferences, default map center coordinates, and theme configuration for
    site/zone/facility/equipment colors.

    @phase active
    """
    __tablename__ = "geo_setting"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, unique=True, primary_key=True)
    providers = db.Column(db.Text, default='{}')
    keys = db.Column(db.Text, default='{}')
    zoom = db.Column(db.Float, default=12.0)
    max_zoom = db.Column(db.Integer, default=25)
    digital_zoom = db.Column(db.Boolean, default=True)
    smooth_zoom = db.Column(db.Boolean, default=True)

    default_lat = db.Column(db.Float, default=37.5665)
    default_lng = db.Column(db.Float, default=126.9780)
    tile_fade_animation = db.Column(db.Boolean, default=True)
    prefer_canvas = db.Column(db.Boolean, default=False)

    max_polygons_device = db.Column(db.Integer, default=1000)
    max_polygons_site = db.Column(db.Integer, default=1000)
    max_polygons_zone = db.Column(db.Integer, default=1000)

    equipment_cull_zoom = db.Column(db.Integer, default=15)

    # Unit preferences
    length_unit = db.Column(db.String(8), nullable=False, default='m')  # mm|cm|m|in|ft

    # Theme Configuration (JSON)
    # Stores colors for Site, Zone, Facility, Equipment, etc.
    theme_config = db.Column(db.Text, default='{}')

    def _loads(self, value):
        if not value:
            return {}
        try:
            return json.loads(value)
        except Exception:
            return {}

    def state_dict(self):
        return {
            'providers': self._loads(self.providers),
            'keys': self._loads(self.keys),
            'zoom': self.zoom,
            'max_zoom': self.max_zoom,
            'digital_zoom': self.digital_zoom,
            'smooth_zoom': self.smooth_zoom,
            'default_lat': self.default_lat,
            'default_lng': self.default_lng,
            'tile_fade_animation': self.tile_fade_animation,
            'prefer_canvas': self.prefer_canvas,
            'max_polygons_device': self.max_polygons_device,
            'max_polygons_site': self.max_polygons_site,
            'max_polygons_zone': self.max_polygons_zone,
            'equipment_cull_zoom': self.equipment_cull_zoom if self.equipment_cull_zoom is not None else 15,
            'length_unit': self.length_unit or 'm',
            'theme_config': self._loads(self.theme_config)
        }


# ------------------------------------------------------------------------------
# GeoShape (Previously MapOverlay)
# Represents a drawn shape or overlay on a GeoMap.
# ------------------------------------------------------------------------------
class GeoShape(CRUDMixin, db.Model):
    """
    Represents a GeoJSON shape drawn on a GeoMap.

    GeoShape stores a GeoJSON feature with optional metadata, linked to a GeoMap
    via geo_id. Shapes are hierarchical (site, zone, device, feature) and can
    be associated with physical devices or grouped into layers.

    @phase active
    """
    __tablename__ = "geo_shape"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, unique=True, primary_key=True)
    unique_id = db.Column(db.String(36), nullable=False, unique=True, default=set_uuid)
    
    # Links to GeoMap (unified to 'geo_id' as per migration plan)
    geo_id = db.Column(db.String(64), nullable=False, index=True)
    
    device_id = db.Column(db.String(64), nullable=True, index=True)
    
    # Hierarchy
    type = db.Column(db.String(32), nullable=False, default='feature', index=True) # site, zone, feature
    channel_id = db.Column(db.String(64), nullable=True, index=True)
    parent_id = db.Column(db.Integer, db.ForeignKey('geo_shape.id'), nullable=True, index=True)
    
    @property
    def level_id(self):
        mapping = {'site': 1, 'zone': 2, 'device': 3, 'feature': 3}
        return mapping.get(self.type, 3)
    
    layer_group = db.Column(db.String(64), nullable=True)
    sort_order = db.Column(db.Integer, default=0)
    
    # GeoJSON
    feature = db.Column(JSON, nullable=False)
    meta_json = db.Column(JSON, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    map = db.relationship("GeoMap",
                          primaryjoin="foreign(GeoShape.geo_id) == GeoMap.unique_id",
                          backref=db.backref("shapes", cascade="all, delete-orphan"))

    def __repr__(self):
        return "<GeoShape(id={0}, type='{1}', geo_id='{2}')>".format(self.id, self.type, self.geo_id)


# ------------------------------------------------------------------------------
# GeoLayer (Previously GIS Input)
# External GIS data sources (Tiles, WMS, etc.)
# ------------------------------------------------------------------------------
class GeoLayer(CRUDMixin, db.Model):
    """
    Represents an external GIS layer (tile, WMS, OSM) overlaid on a GeoMap.

    GeoLayer stores provider type (e.g., gis_osm, gis_esri) and JSON options
    containing URLs, API keys, or styling configuration for external mapping services.

    @phase active
    """
    __tablename__ = "geo_layer"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, unique=True, primary_key=True)
    unique_id = db.Column(db.String(36), nullable=False, unique=True, default=set_uuid)
    
    name = db.Column(db.String(128), nullable=False, default='New Layer')
    is_activated = db.Column(db.Boolean, default=True)
    
    # 'device' in Input -> 'type' or 'source_type' here.
    # To keep consistent with other models using 'type', let's use 'type'.
    # e.g. 'gis_osm', 'gis_esri'
    type = db.Column(db.String(64), nullable=False, default='gis_osm')
    
    # Custom options (JSON string for URLs, keys, etc.)
    options = db.Column(db.Text, default='{}')
    
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def position_y(self):
        try:
             opts = json.loads(self.options) if self.options else {}
             return opts.get('position_y', 0)
        except:
             return 0

    def __repr__(self):
        return "<GeoLayer(id={0}, name='{1}')>".format(self.id, self.name)


# ------------------------------------------------------------------------------
# GeoFacility
# Building-level facility metadata linked to GeoShape (type='facility').
# ------------------------------------------------------------------------------
class GeoFacility(CRUDMixin, db.Model):
    """
    Building-level facility metadata linked to a GeoShape outer polygon.

    Stores parametric building specs (geometry, envelope, actuators), bay
    breakdown for connected greenhouses, and a cached capacity computation
    (heating/cooling/ventilation reference values, ±5~10%).

    @phase active
    """
    __tablename__ = "geo_facility"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, unique=True, primary_key=True)
    unique_id = db.Column(db.String(36), nullable=False, unique=True, default=set_uuid)

    # Linkage
    shape_uuid = db.Column(db.String(36), nullable=False, index=True)  # → GeoShape.unique_id
    geo_id = db.Column(db.String(64), nullable=False, index=True)      # → GeoMap.unique_id

    # Identity
    name = db.Column(db.String(128), nullable=False, default='New Facility')
    preset = db.Column(db.String(64), default='standard_arch')
    structure = db.Column(db.String(32), default='single')   # single | connected
    bay_count = db.Column(db.Integer, default=1)

    # JSON specs
    geometry_3d = db.Column(JSON, nullable=True)
    envelope = db.Column(JSON, nullable=True)
    actuators = db.Column(JSON, nullable=True)
    bays = db.Column(JSON, nullable=True)
    computed = db.Column(JSON, nullable=True)

    sort_order = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, default='')

    # Audit
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by = db.Column(db.String(36), default='')

    # 3D asset override (render_mode='asset' → parametric builder skipped)
    model_asset_uuid = db.Column(db.String(36), nullable=True, index=True)
    model_transform = db.Column(JSON, nullable=True)   # {position:[x,y,z], rotation:[rx,ry,rz], scale:[sx,sy,sz]}
    render_mode = db.Column(db.String(16), nullable=False, default='parametric')  # 'parametric' | 'asset'

    # Relationship
    shape = db.relationship(
        "GeoShape",
        primaryjoin="foreign(GeoFacility.shape_uuid) == GeoShape.unique_id",
        backref=db.backref("facility", uselist=False)
    )

    def __repr__(self):
        return "<GeoFacility(id={0}, name='{1}', shape_uuid='{2}')>".format(
            self.id, self.name, self.shape_uuid)


# ------------------------------------------------------------------------------
# GeoModelAsset
# User-registered 3D model assets (primitives, extruded polygons, imported GLTF).
# ------------------------------------------------------------------------------
class GeoModelAsset(CRUDMixin, db.Model):
    """
    User-registered 3D model asset for facility preview override.

    Supports three kinds:
      - 'primitive'        : parametric box/cylinder/sphere/cone/plane
      - 'extruded_polygon' : 2-D polygon + extrude height
      - 'imported_gltf'    : uploaded .glb / .gltf file

    All length values inside spec_json are stored in metres (SI).
    authored_unit records the unit the user used when creating the asset
    (reference only — conversions are done in the UI layer).

    @phase active
    """
    __tablename__ = "geo_model_asset"
    __table_args__ = {'extend_existing': True}

    id = db.Column(db.Integer, unique=True, primary_key=True)
    unique_id = db.Column(db.String(36), nullable=False, unique=True, default=set_uuid)
    owner_user_id = db.Column(db.Integer, nullable=True, index=True)

    name = db.Column(db.String(128), nullable=False, default='New Asset')
    kind = db.Column(db.String(32), nullable=False, default='primitive')  # primitive|extruded_polygon|imported_gltf
    spec_json = db.Column(JSON, nullable=True)
    authored_unit = db.Column(db.String(8), nullable=False, default='m')  # mm|cm|m|in|ft
    tags = db.Column(db.Text, nullable=True)          # comma-separated

    # Thumbnail (server-side render)
    preview_png = db.Column(db.Text, nullable=True)   # relative path under static/
    preview_status = db.Column(db.String(16), nullable=False, default='pending')  # pending|ok|failed

    # Uploaded file (imported_gltf only)
    source_file = db.Column(db.Text, nullable=True)   # relative path under static/uploads/model_assets/

    sort_order = db.Column(db.Integer, default=0)
    notes = db.Column(db.Text, default='')

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    def __repr__(self):
        return "<GeoModelAsset(id={0}, kind='{1}', name='{2}')>".format(
            self.id, self.kind, self.name)
