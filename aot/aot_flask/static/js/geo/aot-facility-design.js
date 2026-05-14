// aot-facility-design.js — Facility Design page (PRD/DESIGN-GEO-FACILITY-001)
(function () {
  'use strict';

  const ACTUATOR_SLOTS = [
    { key: 'outer_side_vent_motor', label: 'Outer side vent motor' },
    { key: 'outer_roof_vent_motor', label: 'Outer roof vent motor' },
    { key: 'inner_side_vent_motor', label: 'Inner side vent motor' },
    { key: 'inner_roof_vent_motor', label: 'Inner roof vent motor' },
    { key: 'thermal_curtain', label: 'Thermal curtain' },
    { key: 'shade_curtain', label: 'Shade curtain' },
    { key: 'irrigation_valve', label: 'Irrigation valve' },
    { key: 'circulation_fan', label: 'Circulation fan' },
    { key: 'exhaust_fan', label: 'Exhaust fan' },
    { key: 'heater', label: 'Heater' },
    { key: 'cooler', label: 'Cooler' },
    { key: 'heat_pump', label: 'Heat pump' }
  ];

  const State = {
    map: null,
    outerGeometry: null,
    facilityUuid: null,
    availableOutputs: [],
    center: null,           // [lng, lat] — facility center on the map
    orientationDeg: 0,      // 0~359, rotation around center
    placeMode: false,       // true while waiting for a single click to set center
    sites: [],              // site features for the active map
    selectedSiteUuid: null, // GeoShape unique_id of the selected site
    _baseStyleLayerIds: []  // snapshot of base style layer IDs for layer panel
  };

  const SITE_SRC = 'map-sites';
  const SITE_LYR_FILL = 'map-sites-fill';
  const SITE_LYR_LINE = 'map-sites-line';

  // CARTO Voyager raster fallback (used when AOT_GEO_CONFIG has no usable layer)
  const FALLBACK_RASTER_STYLE = {
    version: 8,
    sources: {
      basemap: {
        type: 'raster',
        tiles: [
          'https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
          'https://b.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
          'https://c.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png',
          'https://d.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png'
        ],
        tileSize: 256,
        maxzoom: 19,
        attribution: '© OpenStreetMap contributors © CARTO'
      }
    },
    layers: [{ id: 'basemap', type: 'raster', source: 'basemap' }]
  };

  /**
   * Resolve a MapLibre style spec from window.AOT_GEO_CONFIG (same source of truth
   * as /geo/design). Tries:
   *   1. config.layers[*]: first enabled raster (xyz/wms/tile)
   *   2. config.providers.osm or .raster URL pattern
   *   3. CARTO Voyager fallback (cached above)
   */
  function resolveBaseStyle() {
    const cfg = window.AOT_GEO_CONFIG || {};
    const layers = Array.isArray(cfg.layers) ? cfg.layers : [];

    // 1. First active raster layer (xyz/wms/tile)
    for (const L of layers) {
      if (L && L.enabled === false) continue;
      const t = String(L.type || '').toLowerCase();
      const opts = L.options || L;
      const url = opts.url || opts.tileUrl || opts.tiles || L.url;
      if (url && (t.includes('xyz') || t.includes('tile') || t.includes('raster') || t.includes('osm'))) {
        return rasterStyleFromUrl(Array.isArray(url) ? url : [url], opts.attribution || L.attribution);
      }
    }

    // 2. providers fallback
    const providers = cfg.providers || {};
    for (const key of ['osm', 'raster', 'base', 'default']) {
      const p = providers[key];
      const url = (p && (p.url || p.tileUrl)) || null;
      if (url) {
        return rasterStyleFromUrl([url], (p && p.attribution) || '');
      }
    }

    // 3. fallback
    console.warn('[facility] AOT_GEO_CONFIG has no usable raster layer; using CARTO Voyager fallback.');
    return FALLBACK_RASTER_STYLE;
  }

  function rasterStyleFromUrl(tiles, attribution) {
    return {
      version: 8,
      sources: {
        basemap: {
          type: 'raster',
          tiles: tiles,
          tileSize: 256,
          maxzoom: 19,
          attribution: attribution || ''
        }
      },
      layers: [{ id: 'basemap', type: 'raster', source: 'basemap' }]
    };
  }

  document.addEventListener('DOMContentLoaded', async function () {
    const vars = JSON.parse(document.getElementById('facility-page-vars').textContent);
    State.facilityUuid = vars.facility_uuid || null;

    initMap();
    renderActuatorRows();
    bindEventHandlers();
    await loadOutputs();

    if (State.facilityUuid) {
      await loadFacility(State.facilityUuid);
    }
    // After map style/sources ready, populate facility-prod + sites for the active map.
    State.map.on('load', () => {
      const sel = document.getElementById('map-selector');
      const initialGeoId = (sel && sel.value) || null;
      if (initialGeoId) {
        loadSavedFacilities(initialGeoId);
        loadSites(initialGeoId);
      }
    });
    debouncedCompute();
  });

  // =========================================================
  // Map
  // =========================================================
  function initMap() {
    const cfg = window.AOT_GEO_CONFIG || {};
    const initLat  = parseFloat(cfg.default_lat)  || 37.5665;
    const initLng  = parseFloat(cfg.default_lng)  || 126.9780;
    const initZoom = parseFloat(cfg.zoom)         || 13;

    State.map = new maplibregl.Map({
      container: 'facility-map-canvas',
      style: resolveBaseStyle(),
      center: [initLng, initLat],
      zoom: initZoom,
      maxZoom: 19,             // basemap tiles end at z=19
      pitch: 45,               // start in 3D camera so extrusion is visible
      bearing: 0,
      doubleClickZoom: false   // legacy; no-op since draw mode removed
    });
    State.map.addControl(
      new maplibregl.NavigationControl({ showCompass: true, visualizePitch: true }),
      'top-left'
    );

    State.map.on('load', async () => {
      try {
      // ============================================================
      // facility-prod: All saved facilities for this map (3D footprints)
      // ============================================================
      // Capture base style layer IDs BEFORE adding any facility/site layers so that
      // FacilityLayerPanel correctly identifies which layers belong to the base style.
      // If captured after, facility-prod layers are mistakenly treated as base layers
      // and are not restored after a base-map style switch — causing fill-extrusion
      // to re-appear as visible after the switch.
      State._baseStyleLayerIds = (State.map.getStyle().layers || []).map(l => l.id);

      State.map.addSource('facility-prod', { type: 'geojson', data: emptyFC() });
      State.map.addLayer({
        id: 'facility-prod-fill', type: 'fill', source: 'facility-prod',
        paint: { 'fill-color': '#82898f', 'fill-opacity': 0.15 }
      });
      State.map.addLayer({
        id: 'facility-prod-line', type: 'line', source: 'facility-prod',
        paint: { 'line-color': '#5c656b', 'line-width': 1.5 }
      });
      State.map.addLayer({
        id: 'facility-prod-3d', type: 'fill-extrusion', source: 'facility-prod',
        layout: { visibility: 'none' },   // hidden: Three.js overlay replaces this
        paint: {
          'fill-extrusion-color': '#82898f',
          'fill-extrusion-height': ['coalesce', ['get', 'height_m'], 4],
          'fill-extrusion-base':   ['coalesce', ['get', 'base_m'], 0],
          'fill-extrusion-opacity': 0.55
        }
      });

      // ============================================================
      // map-sites: Site shapes belonging to the active map (toggle layer)
      // ============================================================

      State.map.addSource(SITE_SRC, { type: 'geojson', data: emptyFC() });
      State.map.addLayer({
        id: SITE_LYR_FILL, type: 'fill', source: SITE_SRC,
        paint: { 'fill-color': '#f5a623', 'fill-opacity': 0.15 }
      });
      State.map.addLayer({
        id: SITE_LYR_LINE, type: 'line', source: SITE_SRC,
        paint: { 'line-color': '#e07b00', 'line-width': 2, 'line-dasharray': [2, 1] }
      });

      // ============================================================
      // facility-preview: Currently-edited facility (highlight color)
      // ============================================================
      State.map.addSource('facility-preview', { type: 'geojson', data: emptyFC() });
      State.map.addLayer({
        id: 'facility-preview-fill', type: 'fill', source: 'facility-preview',
        paint: { 'fill-color': '#3388ff', 'fill-opacity': 0.18 }
      });
      State.map.addLayer({
        id: 'facility-preview-line', type: 'line', source: 'facility-preview',
        paint: { 'line-color': '#1565c0', 'line-width': 2.5 }
      });
      State.map.addLayer({
        id: 'facility-preview-3d', type: 'fill-extrusion', source: 'facility-preview',
        layout: { visibility: 'none' },   // hidden: Three.js overlay replaces this
        paint: {
          'fill-extrusion-color': '#3388cc',
          'fill-extrusion-height': ['coalesce', ['get', 'height_m'], 4],
          'fill-extrusion-base':   ['coalesce', ['get', 'base_m'], 0],
          'fill-extrusion-opacity': 0.7
        }
      });

      // 지도레이어 패널 초기화 (geo/design과 동일 기능)
      if (window.FacilityLayerPanel) FacilityLayerPanel.init(State);

      // Hover popup for saved facilities
      State.map.on('click', 'facility-prod-fill', onProdFacilityClick);
      State.map.on('mouseenter', 'facility-prod-fill', () => {
        State.map.getCanvas().style.cursor = 'pointer';
      });
      State.map.on('mouseleave', 'facility-prod-fill', () => {
        if (!State.placeMode) State.map.getCanvas().style.cursor = '';
      });

      // Register Three.js 3D overlay — hides fill-extrusion boxes, uses real mesh
      if (window.AoTFacilityMap3D) {
        AoTFacilityMap3D.attach(State.map, []);
      }

      // Push preloaded geometry to preview source
      if (State.outerGeometry) {
        rebuildOuterGeometry();
      }
      } catch (e) {
        console.error('[facility] map load handler error:', e);
      }
    });

    // Click/dblclick listeners — registered immediately (no race with 'load')
    State.map.on('click', onMapClick);
    State.map.on('dblclick', onMapDblClick);

    document.getElementById('map-selector').addEventListener('change', (e) => {
      const opt = e.target.selectedOptions[0];
      if (!opt) return;
      const lat = parseFloat(opt.dataset.lat);
      const lng = parseFloat(opt.dataset.lng);
      const zoom = parseFloat(opt.dataset.zoom) || 13;
      if (!isNaN(lat) && !isNaN(lng)) {
        State.map.flyTo({ center: [lng, lat], zoom });
      }
      // Reload saved facilities + sites for the newly selected map
      loadSavedFacilities(opt.value);
      loadSites(opt.value);
    });

    const siteSel = document.getElementById('site-selector');
    if (siteSel) siteSel.addEventListener('change', (e) => onSiteChange(e.target.value));
  }

  function emptyFC() {
    return { type: 'FeatureCollection', features: [] };
  }

  function setOuterGeometry(geom, props) {
    State.outerGeometry = geom;
    const fc = geom
      ? { type: 'FeatureCollection', features: [{ type: 'Feature', geometry: geom, properties: props || {} }] }
      : emptyFC();
    if (State.map && State.map.getSource('facility-preview')) {
      State.map.getSource('facility-preview').setData(fc);
    }
    _update3DPreview();
  }

  // =========================================================
  // Saved facilities (facility-prod source)
  // =========================================================
  async function loadSavedFacilities(geoId) {
    if (!State.map || !State.map.getSource('facility-prod')) return;
    if (!geoId) {
      State.map.getSource('facility-prod').setData(emptyFC());
      return;
    }
    try {
      const url = '/api/geo/facility/list?geo_id=' + encodeURIComponent(geoId);
      const res = await fetch(url, { credentials: 'same-origin' });
      const json = await res.json();
      if (!json.ok) return;
      const prodFacilities = (json.facilities || [])
        .filter(f => f.unique_id !== State.facilityUuid);  // exclude facility under edit
      const features = prodFacilities.map(toProdFeature).filter(Boolean);
      State.map.getSource('facility-prod').setData({
        type: 'FeatureCollection', features: features
      });
      _load3DProdFacilities(prodFacilities);
    } catch (e) {
      console.warn('[facility] loadSavedFacilities failed:', e);
    }
  }

  function toProdFeature(f) {
    const geom = f.outer_feature && f.outer_feature.geometry;
    if (!geom) return null;
    const g3d = f.geometry_3d || {};
    return {
      type: 'Feature',
      geometry: geom,
      properties: {
        facility_uuid: f.unique_id,
        name: f.name,
        preset: f.preset,
        structure: f.structure,
        bay_count: f.bay_count,
        height_m: g3d.ridge_height_m || 4,
        eave_h: g3d.eave_height_m || 2,
        base_m: 0
      }
    };
  }

  function onProdFacilityClick(e) {
    const ft = e.features && e.features[0];
    if (!ft) return;
    const p = ft.properties || {};
    const structureLabel = p.structure === 'connected'
      ? ' · connected ×' + p.bay_count
      : ' · single';
    const html =
      '<div style="font-size:13px"><strong>' + (p.name || '(unnamed)') + '</strong>' +
      '<br><small>' + (p.preset || '') + structureLabel + '</small>' +
      '<br><a href="?facility_uuid=' + p.facility_uuid + '">Edit</a></div>';
    new maplibregl.Popup({ closeOnClick: true })
      .setLngLat(e.lngLat)
      .setHTML(html)
      .addTo(State.map);
  }

  // =========================================================
  // Sites for the active map (Phase B — site selector)
  // =========================================================
  async function loadSites(geoId) {
    const sel = document.getElementById('site-selector');
    if (!sel) return;
    State.sites = [];
    State.selectedSiteUuid = null;
    sel.innerHTML = '';
    updateSiteLayerData();

    if (!geoId) {
      sel.disabled = true;
      sel.innerHTML = '<option value="" disabled selected>Select a Map first</option>';
      return;
    }
    try {
      const url = '/api/geo/overlays?map_uuid=' + encodeURIComponent(geoId) + '&type=site';
      const res = await fetch(url, { credentials: 'same-origin' });
      const json = await res.json();
      const features = (json && json.features) || [];
      State.sites = features;
      updateSiteLayerData();

      if (features.length === 0) {
        sel.disabled = true;
        sel.innerHTML = '<option value="" disabled selected>No sites in this map</option>';
        return;
      }
      sel.disabled = false;
      const placeholder = document.createElement('option');
      placeholder.value = '';
      placeholder.textContent = '— Select a Site —';
      placeholder.selected = true;
      sel.appendChild(placeholder);
      features.forEach((f) => {
        const props = f.properties || {};
        const opt = document.createElement('option');
        opt.value = props.unique_id || props.db_id || '';
        opt.textContent = props.name || ('Site #' + (props.db_id || ''));
        sel.appendChild(opt);
      });
    } catch (e) {
      console.warn('[facility] loadSites failed:', e);
      sel.disabled = true;
      sel.innerHTML = '<option value="" disabled selected>Failed to load sites</option>';
    }
  }

  function onSiteChange(siteIdValue) {
    State.selectedSiteUuid = siteIdValue || null;
    if (!siteIdValue) return;
    const ft = State.sites.find((f) => {
      const p = f.properties || {};
      return String(p.unique_id) === siteIdValue || String(p.db_id) === siteIdValue;
    });
    if (!ft || !ft.geometry || !State.map) return;
    try {
      const bounds = geometryBounds(ft.geometry);
      if (bounds) State.map.fitBounds(bounds, { padding: 80, duration: 500, maxZoom: 18 });
    } catch (e) { /* ignore */ }
  }

  // =========================================================
  // Map-sites source update (called after loadSites)
  // =========================================================
  function updateSiteLayerData() {
    if (!State.map || !State.map.getSource) return;
    const src = State.map.getSource(SITE_SRC);
    if (!src) return;
    const feats = (State.sites || []).filter(f => f && f.geometry);
    src.setData({ type: 'FeatureCollection', features: feats });
  }

  // =========================================================
  // Place-on-Map mode + parametric rectangle generation
  // =========================================================
  function startPlaceMode() {
    State.placeMode = true;
    if (State.map) {
      State.map.getCanvas().style.cursor = 'crosshair';
      // dragPan steals 'click' on tiny mouse movement — disable for the placement click
      State.map.dragPan.disable();
      State.map.boxZoom.disable();
      State.map.scrollZoom.disable();
      State.map.touchZoomRotate.disable();
    }
    showToast('Click on the map to set the facility center');
  }

  function finishPlaceMode() {
    State.placeMode = false;
    if (State.map) {
      State.map.getCanvas().style.cursor = '';
      State.map.dragPan.enable();
      State.map.boxZoom.enable();
      State.map.scrollZoom.enable();
      State.map.touchZoomRotate.enable();
    }
  }

  function onMapClick(e) {
    if (!State.placeMode) return;
    State.center = [e.lngLat.lng, e.lngLat.lat];
    rebuildOuterGeometry();
    finishPlaceMode();
    debouncedCompute();
  }

  function onMapDblClick(e) {
    // No-op — kept for backward compat with previous draw-mode listeners
  }

  /** Build outer GeoJSON from form: dimensions + center + orientation + structure/bays/spacing. */
  function rebuildOuterGeometry() {
    if (!State.center) return;
    const span = parseFloat(document.getElementById('span-width').value) || 7;
    const length = parseFloat(document.getElementById('length-m').value) || 30;
    const ridgeH = parseFloat(document.getElementById('ridge-height').value) || 4;
    const eaveH  = parseFloat(document.getElementById('eave-height').value) || 2;
    const struct = (document.querySelector('input[name="structure"]:checked') || {}).value || 'single';
    const bayCount = Math.max(parseInt(document.getElementById('bay-count').value, 10) || 1, 1);
    const spacing = parseFloat((document.getElementById('spacing-m') || {}).value) || 0;
    const deg = Number.isFinite(State.orientationDeg) ? State.orientationDeg : 0;

    let geom;
    if (struct === 'single' && bayCount > 1) {
      // N detached single-bay greenhouses arranged in a row with `spacing` between
      geom = buildMultiRectGeoJSON(State.center, span, length, bayCount, spacing, deg);
    } else {
      // Single (1 bay) OR Connected (one envelope spanning all bays)
      const W = struct === 'connected' ? span * bayCount : span;
      geom = buildRotatedRectGeoJSON(State.center, W, length, deg);
    }
    setOuterGeometry(geom, { height_m: ridgeH, eave_h: eaveH, base_m: 0 });
  }

  /** One rotated rectangle (Polygon) at center. */
  function buildRotatedRectGeoJSON(center, W_m, L_m, deg) {
    const ring = rotatedRectRing(center, 0, 0, W_m, L_m, deg);
    return { type: 'Polygon', coordinates: [ring] };
  }

  /** N rotated rectangles arranged along the span axis (MultiPolygon).
   * The group is rotated together by `deg`, so each bay shares the same orientation.
   */
  function buildMultiRectGeoJSON(center, span, length, count, spacing, deg) {
    const totalSpan = span * count + spacing * (count - 1);
    const halfTotal = totalSpan / 2;
    const polygons = [];
    for (let i = 0; i < count; i++) {
      const offX = -halfTotal + span / 2 + i * (span + spacing);
      const ring = rotatedRectRing(center, offX, 0, span, length, deg);
      polygons.push([ring]);
    }
    return { type: 'MultiPolygon', coordinates: polygons };
  }

  /** Build a single ring (closed) for a rectangle whose local center is offset
   * by (offX, offY) from `center`, then rotate the whole thing by `deg` around `center`. */
  function rotatedRectRing(center, offX, offY, W_m, L_m, deg) {
    const cLng = center[0], cLat = center[1];
    const halfW = W_m / 2, halfL = L_m / 2;
    const localCorners = [
      [offX - halfW, offY - halfL],
      [offX + halfW, offY - halfL],
      [offX + halfW, offY + halfL],
      [offX - halfW, offY + halfL]
    ];
    const theta = (deg || 0) * Math.PI / 180;
    const cosT = Math.cos(theta), sinT = Math.sin(theta);
    const M_PER_DEG_LAT = 111320.0;
    const M_PER_DEG_LNG = M_PER_DEG_LAT * Math.cos(cLat * Math.PI / 180);
    const ring = localCorners.map(function (c) {
      const dx = c[0], dy = c[1];
      const rx = dx * cosT - dy * sinT;
      const ry = dx * sinT + dy * cosT;
      return [cLng + rx / M_PER_DEG_LNG, cLat + ry / M_PER_DEG_LAT];
    });
    ring.push(ring[0]);
    return ring;
  }

  /** Collect every coordinate of a (Multi)Polygon's outer ring(s). */
  function geometryAllCoords(geom) {
    if (!geom) return [];
    if (geom.type === 'Polygon') {
      return (geom.coordinates && geom.coordinates[0]) || [];
    }
    if (geom.type === 'MultiPolygon') {
      const all = [];
      const polys = geom.coordinates || [];
      for (let i = 0; i < polys.length; i++) {
        const ring = polys[i] && polys[i][0];
        if (ring && ring.length) {
          for (let j = 0; j < ring.length; j++) all.push(ring[j]);
        }
      }
      return all;
    }
    return [];
  }

  function polygonCentroid(geom) {
    const coords = geometryAllCoords(geom);
    if (coords.length < 2) return null;
    let sx = 0, sy = 0, n = 0;
    // ring is closed (last == first); skip duplicate
    for (let i = 0; i < coords.length - 1; i++) {
      sx += coords[i][0]; sy += coords[i][1]; n++;
    }
    return n > 0 ? [sx / n, sy / n] : null;
  }

  /** Compute bounds covering all polygons (single or multi). */
  function geometryBounds(geom) {
    const coords = geometryAllCoords(geom);
    if (coords.length === 0) return null;
    const b = new maplibregl.LngLatBounds(coords[0], coords[0]);
    for (let i = 1; i < coords.length; i++) b.extend(coords[i]);
    return b;
  }

  // =========================================================
  // Actuators
  // =========================================================
  function renderActuatorRows() {
    const list = document.getElementById('actuator-list');
    list.innerHTML = '';
    ACTUATOR_SLOTS.forEach((slot) => {
      const row = document.createElement('div');
      row.className = 'actuator-row';
      row.innerHTML =
        '<label>' + slot.label + '</label>' +
        '<select class="form-control form-control-sm actuator-select" data-key="' + slot.key + '">' +
        '<option value="">— Not mapped —</option>' +
        '</select>';
      list.appendChild(row);
    });
  }

  async function loadOutputs() {
    try {
      const res = await fetch('/api/geo/devices', { credentials: 'same-origin' });
      const json = await res.json();
      const list = json.devices || json || [];
      State.availableOutputs = list.filter((d) => {
        const t = (d.type || '').toLowerCase();
        return ['output', 'function', 'custom_controller', 'custom', 'pid'].includes(t);
      });
      document.querySelectorAll('.actuator-select').forEach((sel) => {
        State.availableOutputs.forEach((d) => {
          const opt = document.createElement('option');
          opt.value = d.unique_id;
          opt.textContent = (d.name || d.unique_id) + ' (' + (d.type || '') + ')';
          sel.appendChild(opt);
        });
      });
    } catch (e) {
      console.warn('[facility] loadOutputs failed:', e);
    }
  }

  // =========================================================
  // Form ↔ State
  // =========================================================
  function readForm() {
    const layerCount = parseInt(document.getElementById('layer-count').value, 10) || 1;
    const data = {
      facility_uuid: State.facilityUuid || undefined,
      geo_id: document.getElementById('map-selector').value,
      site_shape_uuid: State.selectedSiteUuid || '',
      name: document.getElementById('facility-name').value || 'New Facility',
      preset: document.getElementById('facility-preset').value,
      structure: (document.querySelector('input[name="structure"]:checked') || {}).value || 'single',
      bay_count: parseInt(document.getElementById('bay-count').value, 10) || 1,
      outer_geometry: State.outerGeometry,
      geometry_3d: {
        span_width_m: parseFloat(document.getElementById('span-width').value) || 7,
        eave_height_m: parseFloat(document.getElementById('eave-height').value) || 2,
        ridge_height_m: parseFloat(document.getElementById('ridge-height').value) || 4,
        length_m: parseFloat(document.getElementById('length-m').value) || 30,
        orientation_deg: State.orientationDeg || 0,
        roof_type: (document.getElementById('roof-type') || {}).value || 'arch',
        spacing_m: parseFloat((document.getElementById('spacing-m') || {}).value) || 0,
        center_lng: State.center ? State.center[0] : null,
        center_lat: State.center ? State.center[1] : null,
      },
      envelope: {
        layer_count: layerCount,
        outer: {
          cover_material: document.getElementById('outer-cover').value,
          side_vent: { enabled: document.getElementById('outer-side-vent').checked },
          roof_vent: { enabled: document.getElementById('outer-roof-vent').checked }
        },
        inner: layerCount === 2 ? {
          cover_material: document.getElementById('inner-cover').value,
          air_gap_m: 0.5,
          side_vent: {
            enabled: document.getElementById('inner-side-vent').checked,
            control_mode: document.getElementById('inner-control-mode').value
          },
          roof_vent: {
            enabled: document.getElementById('inner-roof-vent').checked,
            control_mode: document.getElementById('inner-control-mode').value
          }
        } : null,
        curtain: {
          thermal: document.getElementById('curtain-thermal').checked,
          shade: document.getElementById('curtain-shade').checked
        }
      },
      actuators: {}
    };
    document.querySelectorAll('.actuator-select').forEach((sel) => {
      data.actuators[sel.dataset.key] = sel.value || null;
    });
    return data;
  }

  function fillForm(f) {
    State.facilityUuid = f.unique_id;
    State.outerGeometry = (f.outer_feature && f.outer_feature.geometry) || null;
    setOuterGeometry(State.outerGeometry);

    document.getElementById('facility-name').value = f.name || '';
    document.getElementById('facility-preset').value = f.preset || 'standard_arch';
    document.querySelectorAll('input[name="structure"]').forEach((r) => {
      r.checked = (r.value === f.structure);
    });
    document.getElementById('bay-count').value = f.bay_count || 1;
    if (f.geo_id) {
      document.getElementById('map-selector').value = f.geo_id;
      // Reload sites for this map so the site-selector can be restored below
      loadSites(f.geo_id).then(() => {
        if (f.parent_site_uuid) {
          const sel = document.getElementById('site-selector');
          if (sel) {
            sel.value = f.parent_site_uuid;
            State.selectedSiteUuid = f.parent_site_uuid;
          }
        }
      });
      // facility-prod also needs to refresh for the loaded map
      loadSavedFacilities(f.geo_id);
    }

    if (f.geometry_3d) {
      document.getElementById('span-width').value = f.geometry_3d.span_width_m || 7;
      document.getElementById('eave-height').value = f.geometry_3d.eave_height_m || 2;
      document.getElementById('ridge-height').value = f.geometry_3d.ridge_height_m || 4;
      document.getElementById('length-m').value = f.geometry_3d.length_m || 30;
      const roofSel = document.getElementById('roof-type');
      if (roofSel) roofSel.value = f.geometry_3d.roof_type || 'arch';
      const spacingEl = document.getElementById('spacing-m');
      if (spacingEl) spacingEl.value = (f.geometry_3d.spacing_m != null ? f.geometry_3d.spacing_m : 1.0);
      State.orientationDeg = f.geometry_3d.orientation_deg || 0;
      const slider = document.getElementById('orientation-slider');
      const orientInput = document.getElementById('orientation-input');
      const orientValue = document.getElementById('orientation-value');
      if (slider) slider.value = State.orientationDeg;
      if (orientInput) orientInput.value = State.orientationDeg;
      if (orientValue) orientValue.textContent = State.orientationDeg;
    }
    // Recover center from saved polygon centroid (best-effort)
    if (State.outerGeometry) {
      State.center = polygonCentroid(State.outerGeometry);
    }
    if (f.envelope) {
      document.getElementById('layer-count').value = f.envelope.layer_count || 1;
      const outer = f.envelope.outer || {};
      document.getElementById('outer-cover').value = outer.cover_material || 'vinyl_double';
      document.getElementById('outer-side-vent').checked = !!(outer.side_vent && outer.side_vent.enabled);
      document.getElementById('outer-roof-vent').checked = !!(outer.roof_vent && outer.roof_vent.enabled);
      const inner = f.envelope.inner || {};
      document.getElementById('inner-cover').value = inner.cover_material || 'non_woven_fabric';
      document.getElementById('inner-side-vent').checked = !!(inner.side_vent && inner.side_vent.enabled);
      document.getElementById('inner-roof-vent').checked = !!(inner.roof_vent && inner.roof_vent.enabled);
      if (inner.side_vent && inner.side_vent.control_mode) {
        document.getElementById('inner-control-mode').value = inner.side_vent.control_mode;
      }
      const curtain = f.envelope.curtain || {};
      document.getElementById('curtain-thermal').checked = !!curtain.thermal;
      document.getElementById('curtain-shade').checked = !!curtain.shade;
    }
    if (f.actuators) {
      Object.entries(f.actuators).forEach(([k, v]) => {
        const sel = document.querySelector('.actuator-select[data-key="' + k + '"]');
        if (sel) sel.value = v || '';
      });
    }
    if (f.computed) updatePreview(f.computed);

    handleStructureChange();
    handleLayerCountChange();

    // Re-emit polygon with height_m/eave_h in properties so the 3D extrusion layer
    // picks up the correct ridge height for the loaded facility.
    if (State.center) {
      rebuildOuterGeometry();
    }

    // Recenter map on outer polygon (cap zoom at 18 to avoid OSM/CARTO 404 at z=20)
    // Supports both Polygon and MultiPolygon (Phase C: single + bays > 1).
    if (State.outerGeometry && State.map) {
      const bounds = geometryBounds(State.outerGeometry);
      if (bounds) {
        const doFit = (label) => {
          try {
            State.map.fitBounds(bounds, { padding: 60, duration: 0, maxZoom: 18 });
          } catch (e) {}
        };
        // Immediate (works if style/style-data is already loaded)
        doFit('immediate');
        // Safety net: fire on first idle in case the immediate call lost a race
        // with style loading or pending source data.
        try { State.map.once('idle', () => doFit('idle')); } catch (e) {}
      } else {
        console.warn('[facility v3] empty bounds for geometry', State.outerGeometry);
      }
    } else {
      console.warn('[facility v3] fillForm: no outerGeometry or map',
                   { hasGeom: !!State.outerGeometry, hasMap: !!State.map });
    }
  }

  // =========================================================
  // Compute (debounced)
  // =========================================================
  let computeTimer = null;
  function debouncedCompute() {
    clearTimeout(computeTimer);
    computeTimer = setTimeout(doCompute, 500);
  }

  async function doCompute() {
    const data = readForm();
    if (!data.outer_geometry) return;
    try {
      const res = await fetch('/api/geo/facility/compute', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      if (res.status === 501) {
        // P4 facility_calc not yet available — leave preview as is
        return;
      }
      const json = await res.json();
      if (json.ok) updatePreview(json.computed);
    } catch (e) {
      console.warn('[facility] compute failed:', e);
    }
  }

  function updatePreview(c) {
    if (!c) return;
    const set = (id, val, unit) => {
      const el = document.getElementById(id);
      if (!el) return;
      if (val == null) { el.textContent = '— ' + unit; return; }
      el.textContent = (typeof val === 'number' ? val.toFixed(1) : val) + ' ' + unit;
    };
    set('pv-floor', c.floor_m2, 'm²');
    set('pv-volume', c.volume_m3, 'm³');
    set('pv-glazing', c.glazing_m2, 'm²');
    set('pv-vent', c.vent_open_m2, 'm²');
    set('pv-heating', c.heating_kw, 'kW');
    set('pv-cooling', c.cooling_kw, 'kW');
    if (c.ach_total != null) {
      set('pv-ach', c.ach_total, '/h');
    } else if (c.ach_m3h != null && c.volume_m3) {
      set('pv-ach', c.ach_m3h / c.volume_m3, '/h');
    }
  }

  // =========================================================
  // Save / Load
  // =========================================================
  async function saveFacility() {
    const data = readForm();
    if (!data.geo_id) { alert('Please select a map first.'); return; }
    if (!data.outer_geometry) { alert('Use "Place on Map" to set the facility location first.'); return; }

    try {
      const res = await fetch('/api/geo/facility', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(data)
      });
      const json = await res.json();
      if (json.ok) {
        State.facilityUuid = json.facility_uuid;
        showToast('Saved.');
        setTimeout(() => {
          window.location.search = '?facility_uuid=' + json.facility_uuid;
        }, 600);
      } else {
        alert('Save failed: ' + (json.message || 'unknown error'));
      }
    } catch (e) {
      alert('Save error: ' + e.message);
    }
  }

  async function loadFacility(uuid) {
    try {
      const res = await fetch('/api/geo/facility/' + uuid, { credentials: 'same-origin' });
      const json = await res.json();
      if (json.ok && json.facility) fillForm(json.facility);
    } catch (e) {
      console.warn('[facility] loadFacility failed:', e);
    }
  }

  // =========================================================
  // Event handlers
  // =========================================================
  function bindEventHandlers() {
    // structure radio: toggle bay-count input + rebuild rect (W = span × bays)
    document.querySelectorAll('input[name="structure"]').forEach((r) => {
      r.addEventListener('change', () => {
        handleStructureChange();
        rebuildOuterGeometry();
        debouncedCompute();
      });
    });
    document.getElementById('layer-count').addEventListener('change', () => {
      handleLayerCountChange();
      debouncedCompute();
    });

    // Fields that affect compute only (no geometry change)
    const computeOnlyFields = [
      'outer-cover', 'inner-cover', 'inner-control-mode',
      'outer-side-vent', 'outer-roof-vent', 'inner-side-vent', 'inner-roof-vent',
      'curtain-thermal', 'curtain-shade'
    ];
    computeOnlyFields.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('change', debouncedCompute);
    });

    // Fields that change footprint dimensions OR 3D height → rebuild + recompute
    // (heights propagate to the fill-extrusion layer via properties)
    const dimensionFields = [
      'span-width', 'length-m', 'bay-count', 'spacing-m',
      'eave-height', 'ridge-height'
    ];
    dimensionFields.forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.addEventListener('input', () => {
        rebuildOuterGeometry();
        debouncedCompute();
      });
    });

    // Roof type — affects compute (and dashboard mimic) but not footprint
    const roofSel = document.getElementById('roof-type');
    if (roofSel) roofSel.addEventListener('change', debouncedCompute);

    // Orientation slider + numeric input — bidirectional sync
    const slider = document.getElementById('orientation-slider');
    const orientInput = document.getElementById('orientation-input');
    const orientValue = document.getElementById('orientation-value');
    function setOrientation(deg, syncSlider, syncInput) {
      const d = ((parseFloat(deg) || 0) % 360 + 360) % 360;
      State.orientationDeg = d;
      if (syncSlider && slider) slider.value = d;
      if (syncInput && orientInput) orientInput.value = d;
      if (orientValue) orientValue.textContent = Math.round(d);
      rebuildOuterGeometry();
      debouncedCompute();
    }
    if (slider) slider.addEventListener('input', (e) => setOrientation(e.target.value, false, true));
    if (orientInput) orientInput.addEventListener('change', (e) => setOrientation(e.target.value, true, false));

    // Place-on-map button (replaces old draw-polygon flow)
    const placeBtn = document.getElementById('btn-place-on-map');
    if (placeBtn) placeBtn.addEventListener('click', startPlaceMode);
    document.getElementById('btn-clear-shape').addEventListener('click', () => {
      setOuterGeometry(null);
      State.center = null;
      finishPlaceMode();
    });
    document.getElementById('btn-save-facility').addEventListener('click', saveFacility);
  }

  function handleStructureChange() {
    const sel = document.querySelector('input[name="structure"]:checked');
    const v = sel ? sel.value : 'single';
    // Bays count is meaningful for both single (detached row) and connected
    const bayBox = document.getElementById('bay-count-container');
    if (bayBox) bayBox.style.display = '';
    // Spacing only applies to detached single-bay rows (connected bays share walls)
    const spacingBox = document.getElementById('spacing-container');
    if (spacingBox) spacingBox.style.display = (v === 'single') ? '' : 'none';
  }

  function handleLayerCountChange() {
    const v = parseInt(document.getElementById('layer-count').value, 10) || 1;
    document.querySelectorAll('.inner-only').forEach((el) => {
      el.style.display = (v === 2) ? '' : 'none';
    });
  }

  // =========================================================
  // 3D overlay helpers (AoTFacilityMap3D integration)
  // =========================================================
  function _readFacilitySpec() {
    const layerCount = parseInt(document.getElementById('layer-count').value, 10) || 1;
    return {
      unique_id: State.facilityUuid || 'preview',
      preset:    document.getElementById('facility-preset').value || 'standard_arch',
      structure: (document.querySelector('input[name="structure"]:checked') || {}).value || 'single',
      bay_count: Math.max(parseInt(document.getElementById('bay-count').value, 10) || 1, 1),
      geometry_3d: {
        span_width_m:    parseFloat(document.getElementById('span-width').value)  || 7,
        eave_height_m:   parseFloat(document.getElementById('eave-height').value) || 2,
        ridge_height_m:  parseFloat(document.getElementById('ridge-height').value) || 4,
        length_m:        parseFloat(document.getElementById('length-m').value)    || 30,
        orientation_deg: State.orientationDeg || 0,
        roof_type:       (document.getElementById('roof-type') || {}).value || 'arch',
        spacing_m:       parseFloat((document.getElementById('spacing-m') || {}).value) || 0,
      },
      envelope: {
        layer_count: layerCount,
        outer: { cover_material: document.getElementById('outer-cover').value || 'vinyl_double' },
        inner: layerCount === 2
          ? { cover_material: document.getElementById('inner-cover').value || 'non_woven_fabric' }
          : null,
      },
    };
  }

  function _update3DPreview() {
    if (!window.AoTFacilityMap3D) return;
    if (!State.outerGeometry || !State.center) {
      AoTFacilityMap3D.clearPreview();
      return;
    }
    AoTFacilityMap3D.setPreview(_readFacilitySpec(), State.center);
  }

  function _load3DProdFacilities(facilities) {
    if (!window.AoTFacilityMap3D) return;
    AoTFacilityMap3D.loadProd(facilities || []);
  }

  function showToast(msg) {
    const t = document.createElement('div');
    t.textContent = msg;
    t.style.cssText =
      'position:fixed;bottom:30px;right:30px;background:#333;color:#fff;' +
      'padding:.6rem 1.2rem;border-radius:6px;z-index:9999;' +
      'font-size:.9rem;box-shadow:0 2px 6px rgba(0,0,0,0.3);';
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 2500);
  }
})();
