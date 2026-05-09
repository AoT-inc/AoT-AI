# coding=utf-8
"""
Geo Information Service Routes.
Unified Geo System.
"""
from flask import Blueprint, render_template, redirect, url_for, current_app, request, jsonify, Response, g
import requests
from datetime import datetime
import json
import os
import math
from flask_login import login_required, current_user
from aot.aot_flask.utils import utils_general
from aot.databases.models import GeoMap, GeoSetting, GeoLayer, GeoShape, Input, Output, PID, Trigger, Conditional, CustomController, Function, DeviceMeasurements
from aot.aot_flask.extensions import db, cache
from aot.utils.inputs import parse_input_information

# Additional imports for GIS Input logic
from sqlalchemy import or_
from aot.aot_flask.forms import forms_geo
from aot.aot_flask.utils import utils_geo

blueprint = Blueprint('routes_geo', __name__)

from aot.aot_flask.routes_static import inject_variables

# Minimal 1×1 transparent PNG — returned by the WMS proxy when the upstream
# WMS server responds with an XML/HTML service exception so that MapLibre can
# decode the tile without triggering "source image could not be decoded" errors.
_TRANSPARENT_1X1_PNG = (
    b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
    b'\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01'
    b'\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82'
)

@blueprint.route('/api/geo/init_design', methods=['GET'])
@login_required
def api_geo_init_design():
    """
    Auto-load the latest Design Map on page entry.
    Delegates to GeoDesignManager.
    """
    from aot.aot_flask.geo import GeoDesignManager
    result, error = GeoDesignManager.init_design_map(current_user.id)
    
    if error:
        return jsonify({'ok': False, 'message': error}), 500
        
    return jsonify(result)

@blueprint.route('/api/geo/designs/<string:map_uuid>', methods=['GET'])
@login_required
def api_geo_design_get(map_uuid):
    """Get GeoMap Metadata & State by UUID"""
    from aot.aot_flask.geo import GeoDesignManager
    result, error = GeoDesignManager.get_design_map(map_uuid)
    
    if error:
        status_code = 404 if "not found" in error else 500
        return jsonify({'ok': False, 'message': error}), status_code
        
    return jsonify(result)

@blueprint.route('/api/geo/designs/list', methods=['GET'])
@login_required
def api_geo_designs_list():
    """Get List of all Design Maps for selectors"""
    try:
        # [Optimization] Filter by category='design' in SQL to avoid heavy JSON parsing
        all_maps = GeoMap.query.filter_by(category='design').order_by(GeoMap.updated_at.desc()).all()
        result = []
        for m in all_maps:
            state = m.state_dict()
            # Basic metadata for dropdown
            center = state.get('center', [37.5665, 126.9780])
            result.append({
                'unique_id': m.unique_id,
                'name': m.name,
                'latitude': center[0] if isinstance(center, list) and len(center) >= 2 else 37.5665,
                'longitude': center[1] if isinstance(center, list) and len(center) >= 2 else 126.9780,
                'zoom': state.get('zoom', 13)
            })
        return jsonify(result)
    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500

@blueprint.route('/api/geo/designs/<map_uuid>', methods=['DELETE'])
@login_required
def api_geo_design_delete(map_uuid):
    """Delete GeoMap"""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'ok': False, 'message': 'Permission Denied'}), 403
        
    from aot.aot_flask.geo import GeoDesignManager
    result, error = GeoDesignManager.delete_design_map(map_uuid)
    
    if error:
        status_code = 404 if "not found" in error else 500
        return jsonify({'ok': False, 'message': error}), status_code
        
    return jsonify(result)

@blueprint.route('/api/geo/designs', methods=['POST'])
@login_required
def api_geo_design_save():
    """Create or Update GeoMap Metadata & State"""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'ok': False, 'message': 'Permission Denied'}), 403
    
    from aot.aot_flask.geo import GeoDesignManager
    data = request.get_json()
    result, error = GeoDesignManager.save_design_map(data, current_user.id)
    
    if error:
         status_code = 404 if "not found" in error else 500
         return jsonify({'ok': False, 'message': error}), status_code
         
    return jsonify(result)

@blueprint.route('/api/tools/kma_lookup', methods=['POST'])
@login_required
def api_tools_kma_lookup():
    """
    Find Nearest KMA Grid (nx, ny) for given Lat/Lon.
    Uses Nearest Neighbor Search on pre-processed JSON lookup.
    """
    try:
        data = request.get_json()
        user_lat = float(data.get('lat'))
        user_lon = float(data.get('lon'))
        
        # Path to lookup JSON
        json_path = os.path.join(current_app.static_folder, 'json', 'kma_grid_lookup.json')
        
        if not os.path.exists(json_path):
            return jsonify({'ok': False, 'message': 'Lookup data not found'}), 500
            
        with open(json_path, 'r', encoding='utf-8') as f:
            grid_data = json.load(f)
            
        # Nearest Neighbor Search
        min_dist = float('inf')
        nearest_point = None
        
        for point in grid_data:
            # Euclidean distance squared (lat diff^2 + lon diff^2)
            dist = (user_lat - point['lat'])**2 + (user_lon - point['lon'])**2
            
            if dist < min_dist:
                min_dist = dist
                nearest_point = point
                
        if nearest_point:
            return jsonify({
                'ok': True,
                'nx': nearest_point['nx'],
                'ny': nearest_point['ny'],
                'lat': nearest_point['lat'],
                'lon': nearest_point['lon']
            })
        else:
            return jsonify({'ok': False, 'message': 'No matching grid found'}), 404

    except Exception as e:
        return jsonify({'ok': False, 'message': str(e)}), 500

@blueprint.route('/api/geo/settings', methods=['GET', 'POST'])
@login_required
def api_geo_settings():
    """
    Geo Settings API for Modal integration.
    GET: Returns current settings JSON.
    POST: Updates settings via JSON or Form.
    """
    def _ensure_global_settings():
        inst = GeoSetting.query.first()
        if not inst:
            inst = GeoSetting()
            db.session.add(inst)
            db.session.commit()
        return inst

    global_settings = _ensure_global_settings()

    if request.method == 'POST':
        if not utils_general.user_has_permission('edit_settings'):
            return jsonify({'ok': False, 'message': 'Permission Denied'}), 403
            
        # Support both JSON and Form data
        if request.is_json:
            data = request.get_json()
        else:
            data = request.form

        # 1. Process Providers & Keys
        try:
            providers_state = json.loads(global_settings.providers) if global_settings.providers else {}
            # Merge search provider
            search_provider = data.get('search_provider')
            if search_provider is not None:
                 providers_state['search_provider'] = search_provider
            global_settings.providers = json.dumps(providers_state)
        except Exception as e:
            current_app.logger.error(f"Error processing geo providers: {e}")

        # 2. Geo Params
        numeric_fields = {
            'max_zoom': 25,
            'max_polygons_device': 1000,
            'max_polygons_site': 1000,
            'max_polygons_zone': 1000,
            'equipment_cull_zoom': 15
        }
        for field, default in numeric_fields.items():
            try:
                val = data.get(field)
                if val is not None:
                    setattr(global_settings, field, int(val))
            except:
                pass

        float_fields = {
            'default_lat': 37.5665,
            'default_lng': 126.9780,
            'default_zoom': 12.0
        }
        for field, default in float_fields.items():
            try:
                val = data.get(field)
                if val is not None:
                    attr_name = 'zoom' if field == 'default_zoom' else field
                    setattr(global_settings, attr_name, float(val))
            except:
                pass

        # Boolean: digital_zoom, smooth_zoom, tile_fade_animation, prefer_canvas
        bool_fields = ['digital_zoom', 'smooth_zoom', 'tile_fade_animation', 'prefer_canvas']
        for field in bool_fields:
            val = data.get(field)
            if val is not None:
                 setattr(global_settings, field, (str(val).lower() == 'true'))

        # 3. Theme Configuration
        try:
            theme_conf = global_settings.state_dict().get('theme_config', {}) or {}
            theme_keys = [
                'theme_site', 'theme_zone', 'theme_facility', 'theme_equipment', 'theme_device', 
                'theme_input', 'theme_output', 'theme_function',
                'theme_panel_bg', 'theme_panel_opacity',
                'theme_hide_label', 'theme_vis_input', 'theme_vis_output', 'theme_vis_function'
            ]
            for key in theme_keys:
                val = data.get(key)
                if val is not None:
                    clean_key = key.replace('theme_', '')
                    theme_conf[clean_key] = val
            global_settings.theme_config = json.dumps(theme_conf)
        except Exception as e:
            current_app.logger.error(f"Error saving theme config in API: {e}")

        db.session.commit()
        utils_geo.invalidate_geo_config_cache()
        
        return jsonify({'ok': True, 'message': 'Settings Saved'})

    # GET
    saved_state = global_settings.state_dict()
    geo_layers = GeoLayer.query.filter_by(is_activated=True).all()
    layers_data = [{'unique_id': l.unique_id, 'name': l.name, 'type': l.type} for l in geo_layers]

    # Build search_inputs: all GeoLayer records with search capability
    _SEARCH_CAPABLE_TYPES = ['gis_osm', 'gis_google', 'gis_gsi', 'gis_vworld']
    try:
        all_layers = GeoLayer.query.all()
        search_inputs = [
            {'unique_id': l.unique_id, 'name': l.name, 'type': l.type}
            for l in all_layers if l.type in _SEARCH_CAPABLE_TYPES
        ]
        # Add native types not yet registered as layers
        covered_types = {l['type'] for l in search_inputs}
        try:
            _dict_inputs = parse_input_information()
            for type_name in _SEARCH_CAPABLE_TYPES:
                if type_name not in covered_types and type_name in _dict_inputs:
                    search_inputs.append({
                        'unique_id': type_name,
                        'name': _dict_inputs[type_name].get('input_name', type_name),
                        'type': type_name
                    })
        except Exception:
            pass
        current_app.logger.warning(f"[GeoSettings] search_inputs={[i['type'] for i in search_inputs]}")
    except Exception as e:
        current_app.logger.error(f"[GeoSettings] search_inputs build failed: {e}")
        search_inputs = []

    current_search_provider = utils_geo.get_geo_config().get('search_provider')

    return jsonify({
        'ok': True,
        'saved_state': saved_state,
        'geo_layers': layers_data,
        'search_inputs': search_inputs,
        'search_provider': current_search_provider
    })

@blueprint.route('/api/geo/overlays/list', methods=['GET'])
@login_required
def api_geo_overlays_list():
    from aot.aot_flask.geo.geo_overlays import GeoOverlayManager
    return GeoOverlayManager.get_overlays()

@blueprint.route('/api/geo/overlays', methods=['GET', 'POST'])
@login_required
def api_geo_overlays():
    """Unified Overlays Interface (GET: load, POST: bulk save)"""
    from aot.aot_flask.geo import GeoOverlayManager
    
    if request.method == 'GET':
        map_uuid = request.args.get('map_uuid')
        parent_id = request.args.get('parent_id')
        target_type = request.args.get('type')
        device_id = request.args.get('device_id')
        
        result, error = GeoOverlayManager.get_overlays(map_uuid, target_type, parent_id, device_id=device_id)
        if error:
            return jsonify({'error': error}), 500
        return jsonify(result)
        
    else: # POST
        if not utils_general.user_has_permission('edit_settings'):
            return jsonify({'ok': False, 'message': 'Permission Denied'}), 403
            
        data = request.get_json()
        result, error = GeoOverlayManager.save_overlays(data)
        
        if error:
            return jsonify({'ok': False, 'message': error}), 500
            
        return jsonify(result)

@blueprint.route('/api/geo/overlays/delta', methods=['POST'])
@login_required
def api_geo_overlays_delta():
    """Efficient Delta Save for individual features"""
    from aot.aot_flask.geo.geo_overlays import GeoOverlayManager
    
    data = request.get_json()
    result, error = GeoOverlayManager.save_delta(data)
    
    if error:
        return jsonify({'ok': False, 'message': error}), 500
        
    return jsonify(result)

@blueprint.route('/api/geo/generate-pipes', methods=['POST'])
@login_required
def api_geo_generate_pipes():
    """
    Generate Branch Pipes on the Backend for stability.
    Payload: { parent_feature, ref_line, config, map_uuid }
    """
    from aot.aot_flask.geo.geo_overlays import GeoOverlayManager
    
    data = request.get_json()
    result, error = GeoOverlayManager.generate_pipes(data)
    
    if error:
        return jsonify({'ok': False, 'message': error}), 500
        
    return jsonify(result)


# ---------------------------------------------------------------------------
# Parcel Import Routes — 주소 → 필지 폴리곤 → Site 변환
# ---------------------------------------------------------------------------

def _get_vworld_credentials():
    """등록된 VWorld GIS Input에서 api_key / domain 을 읽는다.
    활성화된 레이어를 우선하고, 없으면 비활성 레이어도 확인한다."""
    import json as _json
    layer = (GeoLayer.query.filter_by(type='gis_vworld', is_activated=True).first()
             or GeoLayer.query.filter_by(type='gis_vworld').first())
    if not layer:
        return None, None
    try:
        opts = _json.loads(layer.options) if layer.options else {}
    except Exception:
        opts = {}
    return opts.get('api_key', ''), opts.get('vworld_domain', '')


@blueprint.route('/api/geo/parcel/from_address', methods=['POST'])
@login_required
def api_geo_parcel_from_address():
    """단일 주소로 VWorld 필지 폴리곤을 조회한다.
    API Key는 등록된 VWorld GIS Input에서 자동으로 가져온다."""
    data = request.get_json()
    address = data.get('address', '').strip()
    if not address:
        return jsonify({'ok': False, 'error': 'address required'}), 400
    api_key, domain = _get_vworld_credentials()
    if not api_key:
        return jsonify({'ok': False, 'error': 'VWorld GIS Input이 등록되지 않았거나 API Key가 없습니다.'}), 400
    from aot.inputs_gis.gis_vworld import InputModule as VWorldInput
    result = VWorldInput.parcel_from_address(address, api_key, domain)
    return jsonify(result)


@blueprint.route('/api/geo/parcel/from_csv', methods=['POST'])
@login_required
def api_geo_parcel_from_csv():
    """CSV 파일의 주소 목록으로 필지 폴리곤을 일괄 조회한다.
    API Key는 등록된 VWorld GIS Input에서 자동으로 가져온다."""
    import io
    import csv as csv_mod
    f = request.files.get('file')
    if not f:
        return jsonify({'ok': False, 'error': 'file required'}), 400
    api_key, domain = _get_vworld_credentials()
    if not api_key:
        return jsonify({'ok': False, 'error': 'VWorld GIS Input이 등록되지 않았거나 API Key가 없습니다.'}), 400
    content = f.read().decode('utf-8-sig')
    reader = csv_mod.reader(io.StringIO(content))
    addresses = [row[0].strip() for row in reader if row and row[0].strip()]
    from aot.inputs_gis.gis_vworld import InputModule as VWorldInput
    result = VWorldInput.parcels_from_addresses(addresses, api_key, domain)
    return jsonify(result)


@blueprint.route('/api/geo/parcel/save_as_site', methods=['POST'])
@login_required
def api_geo_parcel_save_as_site():
    """GeoJSON Feature를 GeoShape(Site)로 저장하고, 라벨용 label_aux도 함께 생성한다."""
    import json as _json
    data = request.get_json()
    feature = data.get('feature')
    name = data.get('name', '대지')
    map_uuid = data.get('map_uuid')
    if not feature:
        return jsonify({'ok': False, 'error': 'feature required'}), 400

    import uuid as _uuid
    if 'properties' not in feature or feature['properties'] is None:
        feature['properties'] = {}
    feature['properties']['name'] = name
    feature['properties']['category'] = 'site'
    feature['properties']['aot_type'] = 'site'
    # [Fix] node_id 부여 — cleanupOrphanLabels가 label.parent_node_id ↔ site.node_id로
    # 부모를 찾기 때문에, node_id가 없으면 라벨이 매 로드마다 orphan으로 삭제된다.
    site_node_id = feature['properties'].get('node_id') or str(_uuid.uuid4())
    feature['properties']['node_id'] = site_node_id

    geo_id = map_uuid or '__parcel_import__'

    shape = GeoShape()
    shape.type = 'site'
    shape.feature = feature
    shape.geo_id = geo_id

    from aot.aot_flask.extensions import db as _db
    _db.session.add(shape)
    _db.session.flush()  # shape.unique_id 확보 (commit 전)

    # ── label_aux GeoShape 자동 생성 ──────────────────────────────────────
    # 폴리곤 무게중심(centroid) 계산: shapely 없이 좌표 평균으로 근사
    def _centroid(geom):
        try:
            gtype = geom.get('type', '')
            if gtype == 'Polygon':
                ring = geom['coordinates'][0]
            elif gtype == 'MultiPolygon':
                ring = geom['coordinates'][0][0]
            else:
                return None
            lng = sum(p[0] for p in ring) / len(ring)
            lat = sum(p[1] for p in ring) / len(ring)
            return [lng, lat]
        except Exception:
            return None

    centroid = _centroid(feature.get('geometry') or {})
    if centroid:
        label_feature = {
            'type': 'Feature',
            'geometry': {'type': 'Point', 'coordinates': centroid},
            'properties': {
                'aot_type': 'label_aux',
                'label_name': name,
                'label_area': '',
                'is_label': True,
                'parent_type': 'site',                # 사이트 색상(#DF5353) 적용
                'parent_node_id': site_node_id,       # 부모 Site의 node_id와 일치
                'node_id': str(_uuid.uuid4()),        # 라벨 자체의 node_id (rename 시 dirty 추적용)
            },
        }
        label_shape = GeoShape()
        label_shape.type = 'label_aux'
        label_shape.feature = label_feature
        label_shape.geo_id = geo_id
        _db.session.add(label_shape)

    _db.session.commit()
    return jsonify({'ok': True, 'id': shape.unique_id, 'name': name})


# ---------------------------------------------------------------------------
# [New] GIS Proxy Routes (Specific)
# ---------------------------------------------------------------------------

@blueprint.route('/api/geo/proxy/rainviewer/meta', methods=['GET'])
@login_required
@cache.cached(timeout=300, query_string=True, unless=lambda: hasattr(g, '_proxy_error') and g._proxy_error)
def api_geo_proxy_rainviewer_meta():
    """
    Proxy RainViewer Metadata to avoid client-side CORS/Network issues.
    [Update 2026-02-21] RainViewer public API v2 has been largely discontinued by upstream.
    Returning 404 or empty data gracefully if upstream is down.
    """
    try:
        url = 'https://api.rainviewer.com/public/weather-maps.json'
        # Short timeout: (connect=1s, read=2s) so NGINX never sees a 504.
        resp = requests.get(url, timeout=(1, 2), verify=False)

        if resp.status_code != 200:
            g._proxy_error = True
            current_app.logger.warning(f'[RainViewer Meta] Upstream {resp.status_code}')
            return jsonify({'radar': {'past': [], 'nowcast': []}}), 200

        return jsonify(resp.json())
    except requests.exceptions.Timeout:
        g._proxy_error = True
        current_app.logger.warning('[RainViewer Meta] Upstream timeout')
        return jsonify({'radar': {'past': [], 'nowcast': []}}), 200
    except Exception as e:
        g._proxy_error = True
        current_app.logger.warning(f'[RainViewer Meta] Error: {e}')
        return jsonify({'radar': {'past': [], 'nowcast': []}}), 200

@blueprint.route('/api/geo/proxy/isric', methods=['GET'])
@login_required
# Cache only successful responses (exclude errors)
@cache.cached(timeout=300, query_string=True, unless=lambda: hasattr(g, '_proxy_error') and g._proxy_error)
def api_geo_proxy_isric():
    """
    Proxy for ISRIC SoilGrids API to avoid CORS.
    Pass query params: lon, lat, property, depth, value
    """
    try:
        # Whitelisted params to forward
        params = {k: v for k, v in request.args.items() if k in ['lon', 'lat', 'property', 'depth', 'value']}

        # Validations
        if not params.get('lon') or not params.get('lat'):
            return jsonify({'error': 'Missing coordinates'}), 400

        # Round to 4 decimal places (~11m) to reduce ISRIC upstream load
        try:
            params['lat'] = round(float(params['lat']), 4)
            params['lon'] = round(float(params['lon']), 4)
        except (ValueError, TypeError):
            return jsonify({'error': 'Invalid coordinates'}), 400

        url = 'https://rest.isric.org/soilgrids/v2.0/properties/query'

        # Verify=False might be needed for some older ISRIC SSL certs, but usually True is fine.
        # Use timeout of 15 seconds to prevent 500 error from slow upstream
        resp = requests.get(url, params=params, timeout=15)
        
        if resp.status_code != 200:
            g._proxy_error = True  # Mark as error to skip caching
            return jsonify({'error': f"Upstream error: {resp.status_code}", 'text': resp.text}), resp.status_code
            
        return jsonify(resp.json())
        
    except Exception as e:
        g._proxy_error = True  # Mark as error to skip caching
        current_app.logger.error(f"ISRIC Proxy Error: {e}")
        return jsonify({'error': str(e)}), 500

@blueprint.route('/api/geo/proxy/openweather', methods=['GET'])
@login_required
@cache.cached(timeout=300, query_string=True, unless=lambda: hasattr(g, '_proxy_error') and g._proxy_error)
def api_geo_proxy_openweather():
    """
    Proxy for OpenWeatherMap API.
    """
    try:
        # Whitelisted params
        params = {k: v for k, v in request.args.items() if k in ['lat', 'lon', 'appid', 'units']}
        
        if not params.get('lat') or not params.get('lon') or not params.get('appid'):
            return jsonify({'error': 'Missing required parameters'}), 400
            
        url = 'https://api.openweathermap.org/data/2.5/weather'
        resp = requests.get(url, params=params, timeout=5)
        
        if resp.status_code != 200:
             g._proxy_error = True
             return jsonify({'error': f"Upstream error: {resp.status_code}", 'text': resp.text}), 502
             
        return jsonify(resp.json())
    except Exception as e:
        g._proxy_error = True
        current_app.logger.error(f"OpenWeather Proxy Error: {e}")
        return jsonify({'error': str(e)}), 500

@blueprint.route('/api/geo/proxy/openmeteo', methods=['GET'])
@login_required
@cache.cached(timeout=300, query_string=True, unless=lambda: hasattr(g, '_proxy_error') and g._proxy_error)
def api_geo_proxy_openmeteo():
    """
    Proxy for Open-Meteo API (Used by NASA GIBS legends).
    """
    try:
        # Whitelisted params
        # OpenMeteo uses 'latitude', 'longitude', 'current', 'hourly', 'daily', etc.
        params = request.args.to_dict()
        
        if not params.get('latitude') or not params.get('longitude'):
             return jsonify({'error': 'Missing coordinates'}), 400
             
        # Base URL
        url = 'https://api.open-meteo.com/v1/forecast'
        
        # [Fix] SSL verification disabled for server environments with certificate issues
        resp = requests.get(url, params=params, timeout=10, verify=False)
        
        if resp.status_code != 200:
            g._proxy_error = True
            current_app.logger.warning(f'[OpenMeteo Proxy] Upstream {resp.status_code}')
            # Return 200 so the browser doesn't log a network error; the legend
            # value-box JS handles missing fields by showing "--".
            return jsonify({'error': f'Upstream error: {resp.status_code}'}), 200

        # [Fix] Handle JSON parsing errors gracefully
        try:
            return jsonify(resp.json())
        except Exception as je:
            g._proxy_error = True
            current_app.logger.error(f"OpenMeteo JSON parse error: {je}, response: {resp.text[:200]}")
            return jsonify({'error': 'Failed to parse response'}), 200
    except requests.exceptions.Timeout:
        g._proxy_error = True
        current_app.logger.error("OpenMeteo Proxy Timeout")
        return jsonify({'error': 'Upstream timeout'}), 200
    except Exception as e:
        g._proxy_error = True
        current_app.logger.error(f"OpenMeteo Proxy Error: {e}")
        return jsonify({'error': str(e)}), 200

@blueprint.route('/api/geo/proxy/rainviewer/timestamps', methods=['GET'])
@login_required
@cache.cached(timeout=300, query_string=True, unless=lambda: hasattr(g, '_proxy_error') and g._proxy_error)
def api_geo_proxy_rainviewer_timestamps():
    """
    Proxy for RainViewer Radar Timestamps API.
    Returns list of available radar timestamps for animation.
    Cache: 5 minutes (300s) TTL.
    Upstream: https://api.rainviewer.com/v2/radar/timestamps.json
    """
    try:
        url = 'https://api.rainviewer.com/v2/radar/timestamps.json'
        resp = requests.get(url, timeout=10, verify=False)

        if resp.status_code != 200:
            g._proxy_error = True
            current_app.logger.warning(f"RainViewer Timestamps API error: {resp.status_code}")
            return jsonify({
                'error': 'RainViewer service unavailable',
                'status': resp.status_code,
                'timestamps': []
            }), 502

        try:
            data = resp.json()
            # Ensure timestamps array exists
            if not isinstance(data, list):
                data = {'timestamps': data.get('timestamps', []) or [], 'version': data.get('version', 'v2')}
            return jsonify({'ok': True, 'timestamps': data if isinstance(data, list) else data.get('timestamps', []), 'version': data.get('version', 'v2') if isinstance(data, dict) else 'v2'})
        except Exception as je:
            g._proxy_error = True
            current_app.logger.error(f"RainViewer JSON parse error: {je}")
            return jsonify({'ok': False, 'error': 'Failed to parse response', 'timestamps': []}), 500

    except requests.exceptions.Timeout:
        g._proxy_error = True
        current_app.logger.error("RainViewer Proxy Timeout")
        return jsonify({'ok': False, 'error': 'Upstream timeout', 'timestamps': []}), 504
    except Exception as e:
        g._proxy_error = True
        current_app.logger.error(f"RainViewer Proxy Error: {e}")
        return jsonify({'ok': False, 'error': str(e), 'timestamps': []}), 500

# ---------------------------------------------------------------------------
# [New] GIS Proxy Routes (Generic)
# ---------------------------------------------------------------------------

@blueprint.route('/api/geo/proxy/wms/<unique_id>', methods=['GET'])
@login_required
def api_geo_proxy_wms(unique_id):
    """
    Server-side WMS tile proxy.

    Fetches a WMS GetMap tile on behalf of the browser to bypass CORS restrictions
    on third-party WMS services (e.g. VWorld) that do not send CORS headers.

    MapLibre uses this URL template:
        /api/geo/proxy/wms/<unique_id>?BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256
    """
    try:
        import re as _re
        from aot.utils.inputs import parse_input_information
        from aot.utils.modules import load_module_from_file
        from aot.aot_flask.utils.utils_geo import MockInputDev

        # Channel-exploded layer IDs are suffixed with _{channel_id} (e.g. uuid_5).
        # Strip the suffix to find the base layer, then inject the channel selection.
        channel_id = None
        layer = GeoLayer.query.filter_by(unique_id=unique_id).first()
        if not layer:
            m = _re.match(r'^(.+)_(\d+)$', unique_id)
            if m:
                base_uid, channel_id = m.group(1), int(m.group(2))
                layer = GeoLayer.query.filter_by(unique_id=base_uid).first()
        if not layer:
            return Response('Layer not found', status=404)

        dict_inputs = parse_input_information()
        layer_def = dict_inputs.get(layer.type, {})
        if not layer_def.get('file_path'):
            return Response('Layer type has no InputModule', status=404)

        mod, _ = load_module_from_file(layer_def['file_path'], 'inputs')
        if not mod or not hasattr(mod, 'InputModule'):
            return Response('InputModule not found', status=404)

        inst = mod.InputModule(MockInputDev(layer))

        # If a channel suffix was present, override the active channel selection so
        # get_url() / get_leaflet_options() return the correct LAYERS parameter.
        if channel_id is not None:
            try:
                import json as _json
                saved_opts = _json.loads(layer.options) if layer.options else {}
            except Exception:
                saved_opts = {}
            saved_opts['active_channels'] = [channel_id]
            inst.custom_options = saved_opts
            inst.get_custom_option = lambda opt, default=None: saved_opts.get(opt, default)

        base_url = inst.get_url()
        leaflet_opts = inst.get_leaflet_options()

        # Build WMS params from InputModule options + browser-forwarded tile params
        bbox = request.args.get('BBOX', '')
        width = request.args.get('WIDTH', '256')
        height = request.args.get('HEIGHT', '256')

        if not bbox:
            return Response('Missing BBOX parameter', status=400)

        wms_params = {
            'SERVICE': 'WMS',
            'REQUEST': 'GetMap',
            'VERSION': leaflet_opts.get('version', '1.3.0'),
            'LAYERS': leaflet_opts.get('layers', ''),
            'STYLES': leaflet_opts.get('styles', ''),
            'FORMAT': leaflet_opts.get('format', 'image/png'),
            'TRANSPARENT': 'TRUE' if leaflet_opts.get('transparent', True) else 'FALSE',
            'WIDTH': width,
            'HEIGHT': height,
            'BBOX': bbox,
        }

        # CRS/SRS depends on WMS version (1.3.0 uses CRS, 1.1.x uses SRS)
        if wms_params['VERSION'].startswith('1.3'):
            wms_params['CRS'] = 'EPSG:3857'
        else:
            wms_params['SRS'] = 'EPSG:3857'

        # Forward provider-specific params from leaflet_options that are not
        # standard WMS keys. This covers MapServer's 'map' param (ISRIC SoilGrids),
        # API keys, domain overrides, etc.
        _WMS_STANDARD = {
            'service', 'request', 'version', 'layers', 'styles', 'format',
            'transparent', 'width', 'height', 'bbox', 'crs', 'srs',
        }
        for k, v in leaflet_opts.items():
            if k.lower() not in _WMS_STANDARD and v not in (None, '', False):
                wms_params[k] = v

        sep = '&' if '?' in base_url else '?'
        resp = requests.get(base_url, params=wms_params, timeout=15,
                            headers={'Referer': request.host_url})

        content_type = resp.headers.get('Content-Type', 'image/png')
        if resp.status_code != 200 or 'xml' in content_type or 'html' in content_type:
            current_app.logger.warning(
                f'[WMS Proxy] Upstream error {resp.status_code} for {unique_id}: {resp.text[:200]}'
            )
            # Return a transparent tile so MapLibre does not throw
            # "source image could not be decoded" errors for WMS exceptions.
            return Response(
                _TRANSPARENT_1X1_PNG,
                status=200,
                content_type='image/png',
                headers={'Cache-Control': 'no-cache'}
            )

        return Response(
            resp.content,
            status=200,
            content_type=content_type,
            headers={'Cache-Control': 'public, max-age=300'}
        )

    except Exception as e:
        current_app.logger.error(f'[WMS Proxy] Exception for {unique_id}: {e}')
        return Response(str(e), status=500)


# ---------------------------------------------------------------------------
# GIS Tile Proxy Routes (Generic) - NASA GIBS 타일 프록시
# ---------------------------------------------------------------------------

@blueprint.route('/api/geo/tile_proxy', methods=['GET'])
@login_required
def api_geo_tile_proxy():
    """
    Generic tile proxy endpoint for NASA GIBS and other tile services.
    Receives target URL via query parameter and returns the tile image.
    
    Query Parameters:
        url: The target tile URL to proxy (required)
    """
    try:
        target_url = request.args.get('url')
        
        if not target_url:
            return Response("Missing 'url' parameter", status=400)
        
        # Validate URL to prevent SSRF
        if not target_url.startswith(('http://', 'https://')):
            return Response("Invalid URL protocol", status=400)
        
        # Only allow specific tile servers (SSRF guard)
        # Each entry: (domain_suffix, referer, origin)
        ALLOWED_TILE_SERVERS = [
            ('gibs.earthdata.nasa.gov', 'https://gibs.earthdata.nasa.gov/', 'https://gibs.earthdata.nasa.gov'),
            ('map.pstatic.net',         'https://map.naver.com/',            'https://map.naver.com'),
            ('daumcdn.net',             'https://map.kakao.com/',             'https://map.kakao.com'),
        ]

        from urllib.parse import urlparse
        parsed = urlparse(target_url)
        matched = next(
            (entry for entry in ALLOWED_TILE_SERVERS if parsed.netloc.endswith(entry[0])),
            None
        )

        if not matched:
            current_app.logger.warning(f'[Tile Proxy] Blocked unauthorized domain: {parsed.netloc}')
            return Response("Unauthorized tile server", status=403)

        _, referer, origin = matched
        headers = {
            'Referer': referer,
            'Origin': origin,
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
            'Accept': 'image/webp,image/png,image/*,*/*;q=0.8',
            'Accept-Language': 'ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.7',
        }

        # Fetch the tile
        import requests
        resp = requests.get(target_url, headers=headers, timeout=10)

        if resp.status_code != 200:
            current_app.logger.warning(f'[Tile Proxy] Non-200 status: {resp.status_code} for {target_url}')
            return Response(
                _TRANSPARENT_1X1_PNG,
                status=200,
                mimetype='image/png'
            )
        
        # Determine content type
        content_type = resp.headers.get('Content-Type', 'image/png')
        
        return Response(
            resp.content,
            status=200,
            content_type=content_type,
            headers={'Cache-Control': 'public, max-age=3600'}
        )
        
    except requests.Timeout:
        current_app.logger.error(f'[Tile Proxy] Timeout for {target_url}')
        return Response("Tile request timeout", status=504)
    except requests.RequestException as e:
        current_app.logger.error(f'[Tile Proxy] Request failed: {e}')
        return Response(f"Proxy error: {str(e)}", status=502)
    except Exception as e:
        current_app.logger.error(f'[Tile Proxy] Exception: {e}')
        return Response(str(e), status=500)



@blueprint.route('/api/geo/devices', methods=['GET'])
@login_required
def api_geo_devices_list():
    """Returns a unified list of all available devices for mapping."""
    try:
        map_uuid = request.args.get('map_uuid')
        device_ids_raw = request.args.get('device_ids')
        
        device_ids = None
        if device_ids_raw:
            device_ids = [d.strip() for d in device_ids_raw.split(',') if d.strip()]

        include_all_param = request.args.get('include_all')
        include_all = (include_all_param == 'true' or include_all_param == 'True' or include_all_param is True)
        
        # If explicitly requested, or if no device_ids provided, default to show all
        if include_all_param is None:
            include_all = (not device_ids)

        # [Fix] Explicitly log the filtering mode
        current_app.logger.info(f"[AoT API] Fetching devices for map_uuid: {map_uuid} include_all: {include_all} device_ids_count: {len(device_ids) if device_ids else 0}")

        # [Optimization] Use shared logic from utils_geo to ensure consistency
        # collect_devices handles all types (Input, Output, Function, etc.) and styling (Icon, Color, Status)
        # If device_ids is provided, it prioritizes them. If None/Empty, include_all=True takes over.
        devices = utils_geo.collect_devices(device_ids, include_all=include_all, map_uuid=map_uuid)
        
        # [New] Fetch all measurements for Popups
        all_measurements_map = utils_geo.get_all_measurements_for_map(devices)
        
        return jsonify({
            'ok': True, 
            'devices': devices,
            'all_measurements_map': all_measurements_map
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'ok': False, 'message': str(e)}), 500

@blueprint.context_processor
def inject_dictionary():
    context = inject_variables()
    
    # Inject Unified Geo Config
    if 'geo_config' not in context:
        context['geo_config'] = utils_geo.get_geo_config()
        # Alias for backward compatibility if needed, but we aim for unified 'geo_config'
        # context['gis_global_config'] = context['geo_config'] 
        
    return context

@blueprint.route('/geo/design')
@login_required
def page_design():
    """
    Geo Design Tool.
    Interactive map editor for Sites, Zones, and Devices.
    """
    if not utils_general.user_has_permission('edit_settings'):
        return redirect(url_for('routes_general.home'))
    
    # GeoMap configs - [Optimization] Filter for Design Maps only in SQL
    design_maps = GeoMap.query.filter_by(category='design').order_by(GeoMap.updated_at.desc()).all()

    # [Auto-Create] Default Map if none exist
    if not design_maps:
        import json
        default_state = {
            'category': 'design',
            'layers': []
        }
        # Create default map
        new_map = GeoMap(
            name="My design",
            state_json=json.dumps(default_state),
            created_by=str(current_user.id) # user_id is integer usually, cast to string for safety
        )
        db.session.add(new_map)
        db.session.commit()
        
        # Refresh list
        design_maps = [new_map]
    
    _SEARCH_CAPABLE_TYPES = ['gis_osm', 'gis_google', 'gis_gsi', 'gis_vworld']
    all_layers = GeoLayer.query.all()
    design_search_inputs = [
        {'unique_id': l.unique_id, 'name': l.name, 'type': l.type}
        for l in all_layers if l.type in _SEARCH_CAPABLE_TYPES
    ]

    from flask import make_response
    resp = make_response(render_template('pages/geo/geo_design.html',
                           active_page='geo_design',
                           map_configs=design_maps,
                           geo_config=utils_geo.get_geo_config(),
                           design_search_inputs=design_search_inputs))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    resp.headers['Pragma'] = 'no-cache'
    return resp


# ============================================================
# Facility Routes (PRD/DESIGN-GEO-FACILITY-001)
# ============================================================

@blueprint.route('/geo/facility')
@login_required
def page_facility():
    """Facility Design page — register building-level facility specs."""
    if not utils_general.user_has_permission('edit_settings'):
        return redirect(url_for('routes_general.home'))

    from aot.databases.models import GeoFacility
    design_maps = GeoMap.query.filter_by(category='design')\
        .order_by(GeoMap.updated_at.desc()).all()
    facilities = GeoFacility.query.order_by(GeoFacility.updated_at.desc()).all()

    return render_template(
        'pages/geo/geo_facility.html',
        active_page='geo_facility',
        map_configs=design_maps,
        facilities=facilities,
        geo_config=utils_geo.get_geo_config()
    )


@blueprint.route('/api/geo/facility/list', methods=['GET'])
@login_required
def api_facility_list():
    """List all facilities, optionally filtered by ?geo_id=<map_uuid>."""
    from aot.aot_flask.geo import FacilityManager
    geo_id = request.args.get('geo_id')
    result, error = FacilityManager.list_facilities(geo_id=geo_id)
    if error:
        return jsonify({'ok': False, 'message': error}), 500
    return jsonify({'ok': True, 'facilities': result})


@blueprint.route('/api/geo/facility/compute', methods=['POST'])
@login_required
def api_facility_compute():
    """Preview capacity computation for given facility spec (no DB write)."""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'ok': False, 'message': 'Permission Denied'}), 403

    data = request.get_json() or {}
    try:
        from aot.aot_flask.geo.facility_calc import compute_capacity
    except ImportError:
        return jsonify({
            'ok': False,
            'message': 'facility_calc module not available yet (P4 pending)'
        }), 501

    try:
        result = compute_capacity(data)
        return jsonify({'ok': True, 'computed': result})
    except Exception as e:
        current_app.logger.error(f"facility/compute error: {e}")
        return jsonify({'ok': False, 'message': str(e)}), 500


@blueprint.route('/api/geo/facility/<facility_uuid>', methods=['GET'])
@login_required
def api_facility_get(facility_uuid):
    """Get one facility by unique_id."""
    from aot.aot_flask.geo import FacilityManager
    result, error = FacilityManager.get_facility(facility_uuid)
    if error:
        status = 404 if 'not found' in error.lower() else 500
        return jsonify({'ok': False, 'message': error}), status
    return jsonify({'ok': True, 'facility': result})


@blueprint.route('/api/geo/facility', methods=['POST'])
@login_required
def api_facility_save():
    """Create or update a facility (atomic outer + spec + bays)."""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'ok': False, 'message': 'Permission Denied'}), 403

    from aot.aot_flask.geo import FacilityManager
    data = request.get_json() or {}
    result, error = FacilityManager.save_facility(data, user_id=current_user.id)
    if error:
        status = 404 if 'not found' in error.lower() else 400
        return jsonify({'ok': False, 'message': error}), status
    return jsonify(result)


@blueprint.route('/api/geo/facility/<facility_uuid>', methods=['DELETE'])
@login_required
def api_facility_delete(facility_uuid):
    """Delete a facility — requires confirm_name in payload (Constitution Art.5)."""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'ok': False, 'message': 'Permission Denied'}), 403

    from aot.aot_flask.geo import FacilityManager
    payload = request.get_json(silent=True) or {}
    confirm_name = payload.get('confirm_name') or request.args.get('confirm_name')

    result, error = FacilityManager.delete_facility(facility_uuid, confirm_name=confirm_name)
    if error:
        if 'not found' in error.lower():
            return jsonify({'ok': False, 'message': error}), 404
        if 'confirmation' in error.lower():
            return jsonify({'ok': False, 'message': error}), 400
        return jsonify({'ok': False, 'message': error}), 500
    return jsonify(result)


@blueprint.route('/api/aot/facility/<facility_uuid>/runtime', methods=['GET'])
@login_required
def api_facility_runtime(facility_uuid):
    """Real-time runtime snapshot for the 3D facility widget.

    Returns actuator states (mapped outputs) + indoor/outdoor environment.
    MVP: actuator state resolves against Output table; environment is mock
    until sensor zone wiring is implemented (Phase 2).
    """
    from aot.databases.models import GeoFacility, Output
    facility = GeoFacility.query.filter_by(unique_id=facility_uuid).first()
    if not facility:
        return jsonify({'ok': False, 'message': 'Facility not found'}), 404

    actuator_states = {}
    actuators = facility.actuators or {}
    for slot_key, output_uuid in actuators.items():
        if not output_uuid:
            continue
        try:
            output = Output.query.filter_by(unique_id=output_uuid).first()
            if output:
                actuator_states[slot_key] = {
                    'output_uuid': output_uuid,
                    'name': output.name,
                    'on': bool(getattr(output, 'is_on', False)),
                    'percent': None,
                }
        except Exception:
            pass

    # Environment: mock until sensor-zone wiring (Phase 2)
    runtime = {
        'ok': True,
        'facility_uuid': facility_uuid,
        'actuator_states': actuator_states,
        'outdoor': {
            'temp_c': None,
            'humidity_pct': None,
            'wind_ms': None,
            'wind_deg': None,
            'solar_wm2': None,
        },
        'indoor': {
            'temp_c': None,
            'humidity_pct': None,
            'co2_ppm': None,
        },
        '_mock': True,
    }
    return jsonify(runtime)


@blueprint.route('/geo/layer') # Renamed from /geo/input
@blueprint.route('/geo/input') # Alias for compatibility
@login_required
def page_layer():
    """
    Geo Layer Manager.
    Manages external GIS inputs (Layers).
    """
    if not utils_general.user_has_permission('edit_settings'):
        return redirect(url_for('routes_general.home'))
    
    geo_layers = sorted(GeoLayer.query.all(), key=lambda l: l.position_y)
    dict_inputs = parse_input_information()

    form_add = forms_geo.GISInputAdd()
    form_mod = forms_geo.GISInputMod()

    def get_custom_option(layer_obj, option_id):
        import json
        try:
            options = json.loads(layer_obj.options) if layer_obj.options else {}
            return options.get(option_id)
        except:
            return None

    from flask_wtf.csrf import generate_csrf
    return render_template('pages/geo_input.html',
                           active_page='geo_layer',
                           geo_layers=geo_layers,
                           gis_inputs=geo_layers,
                           dict_inputs=dict_inputs,
                           form_add_gis=form_add,
                           form_mod_gis=form_mod,
                           get_custom_option=get_custom_option,
                           csrf_token=generate_csrf)

@blueprint.route('/geo/layer/submit', methods=['POST'])
@blueprint.route('/geo/input/submit', methods=['POST'])
@login_required
def page_layer_submit():
    """Submit form for Geo Layer page"""
    messages = {
        "success": [],
        "info": [],
        "warning": [],
        "error": []
    }
    
    if not utils_general.user_has_permission('edit_controllers'):
        messages["error"].append("Your permissions do not allow this action")
        return jsonify(data={'messages': messages})
        
    form_add = forms_geo.GISInputAdd()
    form_mod = forms_geo.GISInputMod()
    
    target_input_id = None
    action_type = None

    if form_add.input_add.data:
        messages = utils_geo.geo_layer_add(form_add)
        # Assuming we can get the new ID? 
        # utils_geo.geo_layer_add currently returns only messages. 
        # Ideally we should modify it to return ID, but for activation focus we skip "add" DOM update for now (reload fallback)
        action_type = 'input_add'
        
    elif form_mod.input_mod.data:
        # Check standard modification
        messages = utils_geo.geo_layer_mod(form_mod, request.form)
        target_input_id = form_mod.input_id.data
        action_type = 'input_mod'
        
    elif form_mod.input_delete.data:
        target_input_id = form_mod.input_id.data
        messages = utils_geo.geo_layer_del(target_input_id)
        action_type = 'input_delete'

    # [Fix] Handle Activation/Deactivation (Standard AoT Input Logic)
    elif 'input_activate' in request.form:
        target_input_id = form_mod.input_id.data
        messages = utils_geo.geo_layer_activate(target_input_id, True)
        action_type = 'input_activate'
    elif 'input_deactivate' in request.form:
        target_input_id = form_mod.input_id.data
        messages = utils_geo.geo_layer_activate(target_input_id, False)
        action_type = 'input_deactivate'

    # Check global message settings
    from aot.databases.models import Misc
    misc = Misc.query.first()
    if misc:
        if misc.hide_alert_success:
            messages['success'] = []
        if misc.hide_alert_info:
            messages['info'] = []
        if misc.hide_alert_warning:
            messages['warning'] = []

    # [Fix] Return input_id and action for JS DOM update
    return jsonify(data={
        'messages': messages,
        'input_id': target_input_id,
        'action': action_type
    })

@blueprint.route('/geo/input/layout', methods=['POST'])
@blueprint.route('/geo/layer/layout', methods=['POST'])
@login_required
def page_layer_save_layout():
    """Save GridStack Layout for Geo Inputs"""
    if not utils_general.user_has_permission('edit_settings'):
        return jsonify({'error': 'Permission Denied'}), 403

    try:
        layout_data = request.get_json()
        if not layout_data:
            return jsonify(result='error', message='No data')
        
        # Format: [{'id': 'uuid', 'y': 0, 'x': 0, ...}, ...]
        # Note: GridStack serialization returns 'id' if we set gs-id properly.
        
        for item in layout_data:
            layer_id = item.get('id')
            pos_y = item.get('y')
            
            if layer_id is not None and pos_y is not None:
                layer = GeoLayer.query.filter_by(unique_id=layer_id).first()
                if layer:
                    try:
                        opts = json.loads(layer.options) if layer.options else {}
                    except:
                        opts = {}
                    
                    if opts.get('position_y') != pos_y:
                        opts['position_y'] = int(pos_y)
                        layer.options = json.dumps(opts)
                        
        db.session.commit()
        return jsonify(result='success')

    except Exception as e:
        return jsonify(result='error', message=str(e))

@blueprint.route('/geo/settings', methods=['GET'])
@blueprint.route('/geo/setting', methods=['GET', 'POST'])
@login_required
def page_settings():
    """
    Geo Settings - Redirect to Geo Design.
    Legacy page is now integrated as a modal in Geo Design.
    """
    if not utils_general.user_has_permission('view_settings'):
        return redirect(url_for('routes_general.home'))
    
    # 301 Redirect to Geo Design page where the settings are now a modal
    return redirect(url_for('routes_geo.page_design'), code=301)
    
    # Functionality moved to api_geo_settings and geo_design modal
    pass

@blueprint.route('/location/entry')
@login_required
def location_entry():
    """
    Location Option Picker.
    Simplified map for selecting device location.
    """
    return render_template('pages/location_option/entry.html')

# --- Helper Utilities ---
def _next_map_name(base_label="Map"):
    """Generate next incremental map name."""
    existing = GeoMap.query.filter(GeoMap.name.ilike(f"{base_label}%")).all()
    max_idx = 0
    for m in existing:
        try:
            suffix = m.name.replace(base_label, '').strip()
            if suffix:
                num = int(suffix)
                if num > max_idx:
                    max_idx = num
        except Exception:
            continue
    return f"{base_label} {max_idx + 1}"


# =============================================================================
# GeoJSON API Routes (for Pure MapLibre Widget)
# =============================================================================

def _shape_feature_dict(shape):
    """Return the GeoShape.feature column as a dict (JSON column may be str)."""
    feat = shape.feature
    if isinstance(feat, dict):
        return feat
    if isinstance(feat, str) and feat:
        try:
            return json.loads(feat)
        except Exception:
            return {}
    return {}


def _shapes_to_geojson(shape_type, default_color):
    """Build a FeatureCollection from GeoShape rows of the given type.

    GeoShape stores the GeoJSON Feature in the `feature` JSON column. The
    hierarchy field is `type` ('site', 'zone', 'feature', 'facility', ...),
    and there is no `name` / `category` column on GeoShape — the human-readable
    name lives inside feature.properties.
    """
    shapes = GeoShape.query.filter_by(type=shape_type).all()
    features = []
    for shape in shapes:
        try:
            feat = _shape_feature_dict(shape)
            geometry = feat.get('geometry')
            if not geometry:
                continue
            props = dict(feat.get('properties') or {})
            props.setdefault('id', shape.unique_id)
            props.setdefault('name', props.get('name') or '')
            props['category'] = shape_type
            props.setdefault('color', props.get('fill') or default_color)
            features.append({
                'type': 'Feature',
                'id': shape.unique_id,
                'geometry': geometry,
                'properties': props,
            })
        except Exception:
            continue
    return {'type': 'FeatureCollection', 'features': features}


@blueprint.route('/api/geo/sites', methods=['GET'])
@login_required
def api_geo_sites():
    """Get all sites as GeoJSON for MapLibre overlay."""
    try:
        return jsonify(_shapes_to_geojson('site', '#DF5353'))
    except Exception as e:
        current_app.logger.exception("api_geo_sites failed")
        return jsonify({'error': str(e)}), 500


@blueprint.route('/api/geo/zones', methods=['GET'])
@login_required
def api_geo_zones():
    """Get all zones as GeoJSON for MapLibre overlay."""
    try:
        return jsonify(_shapes_to_geojson('zone', '#28a745'))
    except Exception as e:
        current_app.logger.exception("api_geo_zones failed")
        return jsonify({'error': str(e)}), 500


@blueprint.route('/api/geo/shapes/<string:category>', methods=['GET'])
@login_required
def api_geo_shapes_by_category(category):
    """Get shapes by hierarchy type (site, zone, facility, feature, ...)."""
    try:
        return jsonify(_shapes_to_geojson(category, '#995aff'))
    except Exception as e:
        current_app.logger.exception("api_geo_shapes_by_category failed")
        return jsonify({'error': str(e)}), 500
