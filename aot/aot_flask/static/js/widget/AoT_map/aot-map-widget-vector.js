/**
 * aot-map-widget-vector.js
 * Pure MapLibre GL-based AoT Map Widget
 * Leaflet-free implementation with full 3D support
 * 
 * @version 3.0.0 (Pure MapLibre)
 * @requires maplibre-gl.js
 */

(function() {
    'use strict';

    /**
     * Initialize Pure MapLibre Map Widget
     * @param {string} uniqueId - Widget unique identifier
     */
    // Inject .aot-type-hidden CSS rule once — independent of Python template caching
    if (!document.getElementById('aot-type-hidden-style')) {
        var _styleEl = document.createElement('style');
        _styleEl.id = 'aot-type-hidden-style';
        _styleEl.textContent = '.aot-type-hidden { display: none !important; }';
        document.head.appendChild(_styleEl);
    }

    window.initAoTMapVectorWidget = async function(uniqueId) {
        console.log('[AoT Vector Widget] Initializing for:', uniqueId);

        // Get widget data from embedded JSON
        const varsEl = document.getElementById('aot-map-vars-' + uniqueId);
        if (!varsEl) {
            console.error('[AoT Vector Widget] Widget data element not found:', 'aot-map-vars-' + uniqueId);
            return;
        }

        let vars;
        try {
            vars = JSON.parse(varsEl.textContent);
        } catch (e) {
            console.error('[AoT Vector Widget] Failed to parse widget data:', e);
            return;
        }

        const mapId = vars.mapId || 'aot-map-' + uniqueId;
        const mapContainer = document.getElementById(mapId);
        if (!mapContainer) {
            console.error('[AoT Vector Widget] Map container not found:', mapId);
            return;
        }

        const canvasId = mapId + '-canvas';
        let canvas = document.getElementById(canvasId);
        if (!canvas) {
            canvas = document.createElement('div');
            canvas.id = canvasId;
            canvas.style.width = '100%';
            canvas.style.height = '100%';
            mapContainer.appendChild(canvas);
        }

        // Get geo config from global or vars
        const geoConfig = vars.geoConfig || window.AOT_GEO_CONFIG || {};
        const settings = geoConfig.settings || geoConfig;

        // Widget custom_options — vars.vars == widget_variables from generate_page_variables_logic
        const wOpts = (vars && vars.vars) || {};

        // Extract configuration — widget custom_options take precedence over global defaults
        const defaultLat = parseFloat(wOpts.fallback_latitude) || parseFloat(settings.default_lat) || 37.5665;
        const defaultLng = parseFloat(wOpts.fallback_longitude) || parseFloat(settings.default_lng) || 126.978;
        const defaultZoom = parseFloat(wOpts.default_zoom) || parseFloat(settings.zoom) || 12;
        const maxZoom = parseInt(settings.max_zoom) || 22;
        const defaultPitch = parseFloat(wOpts.default_pitch) || parseFloat(vars.default_pitch) || 0;
        const defaultBearing = parseFloat(wOpts.default_bearing) || parseFloat(vars.default_bearing) || 0;

        // Get layers from config
        const layers = vars.layers || settings.layers || geoConfig.layers || [];
        const activeLayers = vars.active_layers || [];

        // Find vector base layer — map_style_url custom option overrides geoConfig
        const vectorLayers = layers.filter(l => l.type === 'vector');
        const _selectedBase = wOpts.selected_base_layer || '';
        const _selectedVectorLayer = _selectedBase
            ? vectorLayers.find(l => l.name === _selectedBase)
            : null;
        const baseStyleUrl = wOpts.map_style_url
            || (_selectedVectorLayer && _selectedVectorLayer.url ? _selectedVectorLayer.url
                : (vectorLayers.length > 0 ? vectorLayers[0].url : 'https://demotiles.maplibre.org/style.json'));

        // Create MapLibre map
        if (typeof maplibregl === 'undefined') {
            console.error('[AoT Vector Widget] MapLibre GL not loaded!');
            return;
        }

        const map = new maplibregl.Map({
            container: canvasId,
            style: baseStyleUrl,
            center: [defaultLng, defaultLat],
            zoom: defaultZoom,
            maxZoom: maxZoom,
            pitch: defaultPitch,
            bearing: defaultBearing,
            attributionControl: false
        });

        // Add attribution control
        map.addControl(new maplibregl.AttributionControl({
            compact: true,
            position: 'bottom-left'
        }), 'bottom-left');

        // NOTE: native NavigationControl removed — its top-right placement
        // overlapped the new .map-tools-right toolbar (Layers/Note/Measure)
        // and intercepted clicks. Zoom +/- now lives in the left tool-group.
        // The compass button is injected into the left tool-group by
        // addControlButtons() so pitch-rotation is still available.

        // Add scale control
        map.addControl(new maplibregl.ScaleControl({
            maxWidth: 100,
            unit: 'metric'
        }), 'bottom-left');

        // Store widget instance
        window.AoTWidgetInstances = window.AoTWidgetInstances || {};
        window.AoTWidgetInstances[uniqueId] = {
            map: map,
            vars: vars,
            markers: new Map(),
            shapes: new Map(),
            sources: new Map(),
            layers: new Map()
        };

        const instance = window.AoTWidgetInstances[uniqueId];

        // Initialize when style is loaded
        map.on('load', async function() {
            // Ensure canvas is visible and sized correctly.
            // map.resize() must always run: the canvas may have been initialised
            // at a small placeholder size (e.g. 61×300 px) and needs to expand to
            // the real container dimensions before the render loop starts.
            try {
                const cv = map.getCanvas();
                if (cv && cv.style.display === 'none') {
                    cv.style.display = ''; // un-hide if a rogue script hid it
                }
                map.resize(); // always resize — container may have grown since map init
            } catch (_) {}

            // Initialize VectorLayerManager if available
            if (window.AoTVectorLayerManager && typeof window.AoTVectorLayerManager.init === 'function') {
                window.AoTVectorLayerManager.init(map);

                // Add configured layers
                if (typeof window.AoTVectorLayerManager.addLayer === 'function') {
                    for (const layerConfig of layers) {
                        if (layerConfig.enabled !== false) {
                            try {
                                window.AoTVectorLayerManager.addLayer(layerConfig);
                            } catch (e) {
                                console.warn('[AoT Vector Widget] addLayer failed for', layerConfig.id || layerConfig.unique_id, e);
                            }
                        }
                    }
                }
            } else {
                console.warn('[AoT Vector Widget] AoTVectorLayerManager.init not available — skipping vector layers (cache may be stale; reload required)');
            }

            // Add GeoJSON layers for sites/zones/devices
            await loadGeoJSONLayers(uniqueId, map, vars);

            // Add geo/design labels (label_aux markers)
            await loadGeoDesignLabels(uniqueId, map, vars);

            // 3D terrain (enable_3d_terrain custom option)
            const _wOpts = (vars && vars.vars) || {};
            if (_wOpts.enable_3d_terrain === true || _wOpts.enable_3d_terrain === 'true') {
                try {
                    if (!map.getSource('mapbox-dem')) {
                        map.addSource('mapbox-dem', { type: 'raster-dem', url: 'https://demotiles.maplibre.org/terrain-tiles/tiles.json', tileSize: 256 });
                    }
                    map.setTerrain({ source: 'mapbox-dem', exaggeration: 1.5 });
                } catch (e) { console.warn('[AoT Map] 3D terrain failed:', e); }
            }

            // Load device markers: async if async_devices=true (default), sync fallback
            const _wOpts3 = (vars && vars.vars) || {};
            if (_wOpts3.async_devices === true || _wOpts3.async_devices === 'true' || _wOpts3.async_devices === undefined) {
                fetchAndRenderDevices(uniqueId, map, vars);
            } else if (vars.devices && vars.devices.length > 0) {
                addDeviceMarkers(uniqueId, map, vars.devices, vars.theme, vars);
            }

            // Restore widget UI: control buttons, measurement panel, overlay legend
            try { addControlButtons(uniqueId, map, vars); } catch (e) {
                console.error('[AoT Map] addControlButtons FAILED:', e);
            }
            try { addMeasurementPanel(uniqueId, map, vars); } catch (e) {
                console.error('[AoT Map] addMeasurementPanel FAILED:', e);
            }
            // Layer panel (top-right unified toolbar: Layers + Measure + Note).
            // Must come before addLegendOverlay so legend can reference the layer panel's update hook.
            try { addLayerPanel(uniqueId, map, vars); } catch (e) {
                console.error('[AoT Map] addLayerPanel FAILED:', e);
            }
            // Legend — uses initial active_layers; also wired to layer panel changes.
            try { addLegendOverlay(uniqueId, map, vars); } catch (e) {
                console.error('[AoT Map] addLegendOverlay FAILED:', e);
            }
            // Note markers (port of v3 raster widget renderMapNotes).
            try { startMapNotesPolling(uniqueId, map, vars.refreshSeconds); } catch (e) {
                console.error('[AoT Map] startMapNotesPolling FAILED:', e);
            }
            // Site list rehydration from /api/geo/overlays (port of v3:744-813).
            try { refreshSiteList(uniqueId, map, vars); } catch (e) {
                console.error('[AoT Map] refreshSiteList FAILED:', e);
            }
            // Apply global panel transparency after all panels are created.
            try { applyPanelOpacity(uniqueId, vars); } catch (e) {
                console.error('[AoT Map] applyPanelOpacity FAILED:', e);
            }
        });

        // Handle errors — tile decode failures (e.g. WMS service exception returned as
        // XML/HTML) are downgraded to warnings so the console stays clean.
        map.on('error', function(e) {
            const msg = (e && e.error && e.error.message) || '';
            // Tile-level HTTP errors (404/410) and image decode failures are expected
            // for optional overlay layers — downgrade to warn to keep console clean.
            if (msg.indexOf('decode') !== -1 || msg.indexOf('source image') !== -1 ||
                msg.indexOf('410') !== -1 || msg.indexOf('404') !== -1 ||
                (e && e.tile)) {
                console.warn('[AoT Map] Tile warning:', msg || e);
            } else {
                console.error('[AoT Vector Widget] Map error:', e);
            }
        });

        // Persist view state (center, zoom, pitch, bearing) after user interaction
        let _viewSaveTimer;
        map.on('moveend', function() {
            clearTimeout(_viewSaveTimer);
            _viewSaveTimer = setTimeout(function() {
                const widgetId = (vars && vars.widgetId) || uniqueId;
                const center = map.getCenter();
                fetch('/save_widget_custom_options', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        widget_id: widgetId,
                        options: {
                            fallback_latitude:  center.lat.toFixed(6),
                            fallback_longitude: center.lng.toFixed(6),
                            default_zoom:       map.getZoom().toFixed(2),
                            default_pitch:      Math.round(map.getPitch()),
                            default_bearing:    Math.round(map.getBearing())
                        }
                    })
                }).catch(function(e) { console.warn('[AoT Map] saveViewState:', e); });
            }, 1000);
        });

        // Refresh handler
        if (vars.refreshSeconds > 0) {
            setupRefresh(uniqueId, vars.refreshSeconds);
        }
    };

    /**
     * Load GeoJSON layers (sites, zones, devices)
     */
    async function loadGeoJSONLayers(uniqueId, map, vars) {
        const instance = window.AoTWidgetInstances[uniqueId];
        if (!instance) return;

        const wOpts = (vars && vars.vars) || {};
        function _boolOpt(key) {
            const v = wOpts[key];
            return v === true || v === 'true' || v === 1;
        }

        // Theme colors from geo/design panel settings
        // Device colors are stored by sub-type: theme['input'], theme['output'], theme['function']
        const theme = wOpts.theme_config || (vars && vars.theme) || {};
        const C = {
            site:      theme.site      || '#DF5353',
            zone:      theme.zone      || '#28a745',
            facility:  theme.facility  || '#82898f',
            equipment: theme.equipment || '#007bff',
            drawn:     theme.drawn     || '#f59e42'
        };
        // Data-driven device shape color: match GeoJSON device_type property to theme key
        const _devInputColor    = theme['input']    || '#995aff';
        const _devOutputColor   = theme['output']   || '#dd4444';
        const _devFunctionColor = theme['function'] || '#28a745';
        const _deviceColorExpr = ['match', ['get', 'device_type'],
            'input',    _devInputColor,
            'output',   _devOutputColor,
            'function', _devFunctionColor,
            _devInputColor
        ];

        // mapUuid: multiple fallback sources (fixes aot-device missing when contentMapUuid empty)
        const mapUuid = wOpts.selected_map_uuid || wOpts.map_uuid || (vars && vars.contentMapUuid) || '';

        // ============================================================
        // Sites — rendered only when show_site_shape is ON
        // ============================================================
        if (_boolOpt('show_site_shape')) {
            try {
                const sitesResponse = await fetch('/api/geo/sites?format=geojson');
                if (sitesResponse.ok) {
                    const sitesGeoJSON = await sitesResponse.json();
                    if (sitesGeoJSON.features && sitesGeoJSON.features.length > 0) {
                        addGeoJSONLayer(uniqueId, map, 'sites', sitesGeoJSON, {
                            type: 'fill',
                            paint: { 'fill-color': C.site, 'fill-opacity': 0.08 }
                        }, 'sites-fill');
                        addGeoJSONLayer(uniqueId, map, 'sites', sitesGeoJSON, {
                            type: 'line',
                            paint: { 'line-color': C.site, 'line-width': 3, 'line-opacity': 0.8 }
                        }, 'sites-line');
                    }
                }
            } catch (e) {
                console.warn('[AoT Vector Widget] Failed to load sites:', e);
            }
        }

        // ============================================================
        // Zones — rendered only when show_zone_shape is ON
        // ============================================================
        if (_boolOpt('show_zone_shape')) {
            try {
                const zonesResponse = await fetch('/api/geo/zones?format=geojson');
                if (zonesResponse.ok) {
                    const zonesGeoJSON = await zonesResponse.json();
                    if (zonesGeoJSON.features && zonesGeoJSON.features.length > 0) {
                        addGeoJSONLayer(uniqueId, map, 'zones', zonesGeoJSON, {
                            type: 'fill',
                            paint: { 'fill-color': C.zone, 'fill-opacity': 0.1 }
                        }, 'zones-fill');
                        addGeoJSONLayer(uniqueId, map, 'zones', zonesGeoJSON, {
                            type: 'line',
                            paint: { 'line-color': C.zone, 'line-width': 2, 'line-dasharray': [2, 2], 'line-opacity': 0.8 }
                        }, 'zones-line');
                    }
                }
            } catch (e) {
                console.warn('[AoT Vector Widget] Failed to load zones:', e);
            }
        }

        // facility/equipment/device/drawn require mapUuid
        if (!mapUuid) return;

        // ============================================================
        // Facility shapes
        // ============================================================
        if (_boolOpt('show_facility_shape')) {
            try {
                const facRes = await fetch('/api/geo/overlays?map_uuid=' + encodeURIComponent(mapUuid) + '&type=facility');
                if (facRes.ok) {
                    const facGeoJSON = await facRes.json();
                    if (facGeoJSON.features && facGeoJSON.features.length > 0) {
                        addGeoJSONLayer(uniqueId, map, 'facilities', facGeoJSON, {
                            type: 'fill',
                            paint: { 'fill-color': C.facility, 'fill-opacity': 0.15 }
                        }, 'facilities-fill');
                        addGeoJSONLayer(uniqueId, map, 'facilities', facGeoJSON, {
                            type: 'line',
                            paint: { 'line-color': C.facility, 'line-width': 1.5 }
                        }, 'facilities-line');
                        addGeoJSONLayer(uniqueId, map, 'facilities', facGeoJSON, {
                            type: 'fill-extrusion',
                            layout: { visibility: 'none' },
                            paint: {
                                'fill-extrusion-color': C.facility,
                                'fill-extrusion-height': ['coalesce', ['get', 'height_m'], 4],
                                'fill-extrusion-base':   ['coalesce', ['get', 'base_m'], 0],
                                'fill-extrusion-opacity': 0.55
                            }
                        }, 'facilities-3d');

                        // Attach Three.js greenhouse model overlay (replaces fill-extrusion box)
                        if (window.AoTFacilityMap3D && window.AoTFacility3D) {
                            try {
                                const facListRes = await fetch('/api/geo/facility/list?geo_id=' + encodeURIComponent(mapUuid));
                                if (facListRes.ok) {
                                    const facListData = await facListRes.json();
                                    const facilities3d = (facListData.facilities || facListData || []).filter(function(f) {
                                        return f.geometry_3d && f.outer_feature;
                                    });
                                    if (facilities3d.length) {
                                        AoTFacilityMap3D.attach(map, facilities3d, { hideLayers: ['facilities-3d'] });
                                    }
                                }
                            } catch (e3d) {
                                console.warn('[AoT Vector Widget] Facility 3D overlay failed:', e3d);
                            }
                        }
                    }
                }
            } catch (e) {
                console.warn('[AoT Vector Widget] Failed to load facilities:', e);
            }
        }

        // ============================================================
        // Equipment shapes
        // ============================================================
        if (_boolOpt('show_equipment_shape')) {
            try {
                const eqRes = await fetch('/api/geo/overlays?map_uuid=' + encodeURIComponent(mapUuid) + '&type=equipment');
                if (eqRes.ok) {
                    const eqGeoJSON = await eqRes.json();
                    if (eqGeoJSON.features && eqGeoJSON.features.length > 0) {
                        addGeoJSONLayer(uniqueId, map, 'equipment', eqGeoJSON, {
                            type: 'line',
                            paint: { 'line-color': C.equipment, 'line-width': 2, 'line-opacity': 0.9 }
                        }, 'equipment-line');
                        addGeoJSONLayer(uniqueId, map, 'equipment', eqGeoJSON, {
                            type: 'fill',
                            paint: { 'fill-color': C.equipment, 'fill-opacity': 0.12 }
                        }, 'equipment-fill');
                    }
                }
            } catch (e) {
                console.warn('[AoT Vector Widget] Failed to load equipment shapes:', e);
            }
        }

        // ============================================================
        // Device shapes (aot_device) — on:0.9 / off:0.2 via data-driven expr
        // Initial state: all OFF (0.2); updated after device fetch
        // ============================================================
        if (_boolOpt('show_device_shapes')) {
            try {
                const devRes = await fetch('/api/geo/overlays?map_uuid=' + encodeURIComponent(mapUuid) + '&type=aot_device');
                if (devRes.ok) {
                    const devGeoJSON = await devRes.json();
                    if (devGeoJSON.features && devGeoJSON.features.length > 0) {
                        addGeoJSONLayer(uniqueId, map, 'aot_devices', devGeoJSON, {
                            type: 'line',
                            paint: { 'line-color': _deviceColorExpr, 'line-width': 2, 'line-opacity': 0.5 }
                        }, 'aot-devices-line');
                        addGeoJSONLayer(uniqueId, map, 'aot_devices', devGeoJSON, {
                            type: 'fill',
                            paint: { 'fill-color': _deviceColorExpr, 'fill-opacity': 0.2 }
                        }, 'aot-devices-fill');
                    }
                }
            } catch (e) {
                console.warn('[AoT Vector Widget] Failed to load device shapes:', e);
            }
        }

        // ============================================================
        // Drawn shapes (기타 그리기 도형 — types not in known list)
        // ============================================================
        if (_boolOpt('show_drawn_shapes')) {
            try {
                const KNOWN_TYPES = new Set([
                    'site', 'zone', 'facility', 'facility_bay',
                    'equipment', 'equipment_collection',
                    'aot_device', 'connection', 'label_aux'
                ]);
                const allRes = await fetch('/api/geo/overlays?map_uuid=' + encodeURIComponent(mapUuid));
                if (allRes.ok) {
                    const allGeoJSON = await allRes.json();
                    if (allGeoJSON.features) {
                        const drawnFeatures = allGeoJSON.features.filter(function(f) {
                            const t = ((f.properties || {}).aot_type || '').toLowerCase();
                            return t && !KNOWN_TYPES.has(t);
                        });
                        if (drawnFeatures.length > 0) {
                            const drawnGeoJSON = { type: 'FeatureCollection', features: drawnFeatures };
                            addGeoJSONLayer(uniqueId, map, 'drawn_shapes', drawnGeoJSON, {
                                type: 'fill',
                                paint: { 'fill-color': C.drawn, 'fill-opacity': 0.2 }
                            }, 'drawn-shapes-fill');
                            addGeoJSONLayer(uniqueId, map, 'drawn_shapes', drawnGeoJSON, {
                                type: 'line',
                                paint: { 'line-color': C.drawn, 'line-width': 2, 'line-opacity': 0.8 }
                            }, 'drawn-shapes-line');
                        }
                    }
                }
            } catch (e) {
                console.warn('[AoT Vector Widget] Failed to load drawn shapes:', e);
            }
        }
    }

    /**
     * Load geo/design label_aux markers and render them as HTML markers
     * matching the geo/design visual style.
     */

    /**
     * Shared label collision + clustering.
     * Overlapping markers are hidden and replaced with a cluster badge showing the count.
     * Clicking the badge flies/fits the map so the individual labels become visible.
     *
     * @param {maplibregl.Marker[]} markers  All label markers to process
     * @param {maplibregl.Map}      map
     * @param {number}              spacing  Extra padding (px) around each label rect
     * @param {object}              instance Widget instance
     * @param {string}              clusterKey  instance[clusterKey] = cluster marker array
     */
    // ── Inline hex→rgba (no external dep, hoisted here so all label helpers can use it) ──
    function _clusterHexRgba(hex, a) {
        if (!hex || hex[0] !== '#') return 'rgba(153,90,255,' + a + ')';
        var r = parseInt(hex.slice(1,3),16), g = parseInt(hex.slice(3,5),16), b = parseInt(hex.slice(5,7),16);
        return 'rgba('+r+','+g+','+b+','+a+')';
    }

    /**
     * Single-group collision pass.
     *
     * @param {maplibregl.Marker[]} markers      Markers for THIS group only.
     * @param {maplibregl.Map}      map
     * @param {number}              spacing      Extra px padding around each label.
     * @param {object}              instance     Widget instance.
     * @param {string}              clusterKey   instance[clusterKey] = array of cluster badge markers.
     * @param {Array}               preOccupied  Rects already taken by higher-priority groups
     *                                           (same coordinate system as getBoundingClientRect).
     * @returns {Array} Rects occupied by visible solo labels in this group (for next group's preOccupied).
     */
    function runLabelCollisionWithClustering(markers, map, spacing, instance, clusterKey, preOccupied) {
        preOccupied = preOccupied || [];
        var placedRects = [];   // rects of solo visible labels → fed to lower-priority groups

        // Remove previous cluster badges
        if (instance[clusterKey]) {
            instance[clusterKey].forEach(function(m) { try { m.remove(); } catch(e) {} });
        }
        instance[clusterKey] = [];

        if (!markers || markers.length === 0) return placedRects;

        // Reset all to invisible-but-in-layout
        markers.forEach(function(mk) {
            var e = mk.getElement();
            e.style.display = 'block';
            e.style.opacity = '0';
            e.style.pointerEvents = 'none';
        });

        // Sort: highest zIndex first
        var sorted = markers.slice().sort(function(a, b) {
            var za = parseInt(a.getElement().style.zIndex) || 0;
            var zb = parseInt(b.getElement().style.zIndex) || 0;
            return zb - za;
        });

        if (sorted.length > 0) void sorted[0].getElement().offsetWidth; // force reflow

        var n = sorted.length;
        var sp = spacing;

        function _overlaps(ra, rb) {
            return !(ra.right <= rb.left || ra.left >= rb.right ||
                     ra.bottom <= rb.top  || ra.top  >= rb.bottom);
        }

        // Build padded rects + flag markers conflicted by higher-priority groups
        var rects = sorted.map(function(mk) {
            var r = mk.getElement().getBoundingClientRect();
            var padded = {
                left:   r.left   - sp,
                right:  r.right  + sp,
                top:    r.top    - sp,
                bottom: r.bottom + sp,
                valid:  r.width > 1,
                conflicted: false
            };
            if (padded.valid) {
                for (var pi = 0; pi < preOccupied.length; pi++) {
                    if (_overlaps(padded, preOccupied[pi])) { padded.conflicted = true; break; }
                }
            }
            return padded;
        });

        // Hide conflicted markers immediately (higher-priority group wins)
        rects.forEach(function(rect, idx) {
            if (rect.conflicted) sorted[idx].getElement().style.display = 'none';
        });

        // Union-Find on non-conflicted, valid markers only
        var parent = [];
        for (var ii = 0; ii < n; ii++) parent[ii] = ii;
        function ufFind(x) { return parent[x] === x ? x : (parent[x] = ufFind(parent[x])); }

        for (var ii = 0; ii < n; ii++) {
            if (rects[ii].conflicted || !rects[ii].valid) continue;
            for (var jj = ii + 1; jj < n; jj++) {
                if (rects[jj].conflicted || !rects[jj].valid) continue;
                if (_overlaps(rects[ii], rects[jj])) {
                    var rootI = ufFind(ii), rootJ = ufFind(jj);
                    if (rootI !== rootJ) parent[rootI] = rootJ;
                }
            }
        }

        // Build groups (non-conflicted only)
        var groups = {};
        for (var ii = 0; ii < n; ii++) {
            if (rects[ii].conflicted) continue;
            var root = ufFind(ii);
            if (!groups[root]) groups[root] = [];
            groups[root].push(ii);
        }

        // Process each group
        Object.keys(groups).forEach(function(root) {
            var group = groups[root];

            if (group.length === 1) {
                var mk = sorted[group[0]];
                var e  = mk.getElement();
                if (!rects[group[0]].valid) {
                    e.style.display = 'none';
                } else {
                    e.style.opacity = '1';
                    e.style.pointerEvents = 'auto';
                    placedRects.push(rects[group[0]]); // reserve for lower-priority groups
                }
            } else {
                // Hide all members, show cluster badge
                var lngLats = [];
                group.forEach(function(idx) {
                    sorted[idx].getElement().style.display = 'none';
                    lngLats.push(sorted[idx].getLngLat());
                });

                var sumLng = 0, sumLat = 0;
                lngLats.forEach(function(ll) { sumLng += ll.lng; sumLat += ll.lat; });
                var cLng = sumLng / lngLats.length;
                var cLat = sumLat / lngLats.length;

                // Representative: lowest sorted index = highest zIndex
                var repIdx   = group.reduce(function(a, b) { return a < b ? a : b; });
                var repEl    = sorted[repIdx].getElement();
                var repName  = repEl.dataset.labelName  || '';
                var repColor = repEl.dataset.labelColor || '#995aff';
                var repLabel = repName.length > 8 ? repName.substring(0, 7) + '…' : repName;
                var badgeBg     = _clusterHexRgba(repColor, 0.92);
                var badgeShadow = _clusterHexRgba(repColor, 0.40);

                var clusterEl = document.createElement('div');
                clusterEl.className = 'aot-label-cluster';
                clusterEl.style.cssText = [
                    'background-color:' + badgeBg,
                    'color:#fff',
                    'border-radius:14px',
                    'height:28px',
                    'padding:0 8px',
                    'display:inline-flex',
                    'align-items:center',
                    'gap:4px',
                    'font-weight:bold',
                    'font-size:12px',
                    'cursor:pointer',
                    'box-shadow:0 2px 6px ' + badgeShadow,
                    'border:2px solid #fff',
                    'z-index:10',
                    'user-select:none',
                    'white-space:nowrap',
                    'max-width:160px'
                ].join(';');
                clusterEl.innerHTML =
                    '<span style="overflow:hidden;text-overflow:ellipsis;max-width:90px">' + repLabel + '</span>' +
                    '<span style="background:rgba(255,255,255,0.25);border-radius:10px;padding:1px 5px;font-size:11px;flex-shrink:0">+' + (group.length - 1) + '</span>';

                (function(lls, centerLng, centerLat) {
                    clusterEl.addEventListener('click', function(e) {
                        e.stopPropagation();
                        var allSame = lls.every(function(ll) {
                            return Math.abs(ll.lng - lls[0].lng) < 0.000001 &&
                                   Math.abs(ll.lat - lls[0].lat) < 0.000001;
                        });
                        if (allSame) {
                            map.flyTo({ center: [centerLng, centerLat], zoom: Math.min(map.getZoom() + 4, 22), duration: 600 });
                        } else {
                            var minLng = Math.min.apply(null, lls.map(function(l) { return l.lng; }));
                            var maxLng = Math.max.apply(null, lls.map(function(l) { return l.lng; }));
                            var minLat = Math.min.apply(null, lls.map(function(l) { return l.lat; }));
                            var maxLat = Math.max.apply(null, lls.map(function(l) { return l.lat; }));
                            map.fitBounds([[minLng, minLat], [maxLng, maxLat]], { padding: 120, maxZoom: 22, duration: 600 });
                        }
                    });
                })(lngLats, cLng, cLat);

                var clusterMarker = new maplibregl.Marker({ element: clusterEl, anchor: 'center' })
                    .setLngLat([cLng, cLat])
                    .addTo(map);
                instance[clusterKey].push(clusterMarker);
            }
        });

        return placedRects;
    }

    /**
     * Post-pass: after all group collision runs, deconflict the cluster BADGES themselves.
     * Priority: siteZone > geoDevice > device.
     * Lower-priority badges that overlap a higher-priority badge are hidden.
     */
    function _deconflictClusterBadges(instance, spacing) {
        var sp = spacing;
        var tiers = [
            instance.siteZoneClusterMarkers  || [],   // priority 1
            instance.geoDeviceClusterMarkers || [],   // priority 2
            instance.deviceClusterMarkers    || []    // priority 3
        ];
        var placedBadgeRects = [];

        tiers.forEach(function(clusterArr) {
            clusterArr.forEach(function(cm) {
                var e = cm.getElement();
                var r = e.getBoundingClientRect();
                if (r.width <= 1) { e.style.display = 'none'; return; }
                var rect = { left: r.left - sp, right: r.right + sp, top: r.top - sp, bottom: r.bottom + sp };
                var blocked = placedBadgeRects.some(function(pr) {
                    return !(rect.right <= pr.left || rect.left >= pr.right ||
                             rect.bottom <= pr.top  || rect.top  >= pr.bottom);
                });
                if (blocked) {
                    e.style.display = 'none';
                } else {
                    placedBadgeRects.push(rect);
                }
            });
        });
    }

    /**
     * Run all three group passes in priority order, then deconflict badges.
     * siteZone (1) → geoDevice (2) → pillDevice (3)
     */
    function _runUnifiedLabelCollision(instance, map, spacing) {
        var sp = spacing;

        console.log('[AoT Label] collision spacing=' + sp + 'px' +
            ' | siteZone=' + (instance.siteZoneLabelMarkers  || []).length +
            ' geoDevice=' + (instance.geoDeviceLabelMarkers  || []).length +
            ' device='    + (instance.deviceLabelMarkers     || []).length + ' markers');

        // Pass 1: site + zone (no pre-occupied)
        var occ1 = runLabelCollisionWithClustering(
            instance.siteZoneLabelMarkers  || [], map, sp, instance, 'siteZoneClusterMarkers', []
        );

        // Pass 2: geo aot_device labels (must avoid site+zone areas)
        var occ2 = runLabelCollisionWithClustering(
            instance.geoDeviceLabelMarkers || [], map, sp, instance, 'geoDeviceClusterMarkers', occ1
        );

        // Pass 3: pill device markers (lowest priority)
        runLabelCollisionWithClustering(
            instance.deviceLabelMarkers    || [], map, sp, instance, 'deviceClusterMarkers', occ1.concat(occ2)
        );

        // Badge-level deconfliction in next frame (badges need to be rendered first)
        requestAnimationFrame(function() {
            _deconflictClusterBadges(instance, sp);
        });
    }

    /**
     * Register (or replace) the single unified collision handler on the map.
     * Call this whenever geo-labels or device-labels are refreshed.
     */
    function _updateUnifiedCollisionHandler(instance, map, spacing) {
        var sp = spacing;

        // Remove old handler
        if (instance._unifiedCollisionHandler) {
            map.off('moveend', instance._unifiedCollisionHandler);
            map.off('zoomend', instance._unifiedCollisionHandler);
            instance._unifiedCollisionHandler = null;
        }

        var _debounce;
        function debouncedUnified() {
            clearTimeout(_debounce);
            _debounce = setTimeout(function() {
                requestAnimationFrame(function() { _runUnifiedLabelCollision(instance, map, sp); });
            }, 150);
        }

        instance._unifiedCollisionHandler = debouncedUnified;
        map.on('moveend', debouncedUnified);
        map.on('zoomend', debouncedUnified);
    }

    async function loadGeoDesignLabels(uniqueId, map, vars) {
        const instance = window.AoTWidgetInstances[uniqueId];
        if (!instance) return;

        // Remove old label markers and clean up collision listeners before re-loading
        ['labelMarkers', 'siteZoneLabelMarkers', 'geoDeviceLabelMarkers'].forEach(function(key) {
            if (instance[key] && instance[key].length > 0) {
                instance[key].forEach(function(m) { try { m.remove(); } catch(e) {} });
            }
            instance[key] = [];
        });
        ['labelClusterMarkers', 'siteZoneClusterMarkers', 'geoDeviceClusterMarkers'].forEach(function(key) {
            if (instance[key] && instance[key].length > 0) {
                instance[key].forEach(function(m) { try { m.remove(); } catch(e) {} });
            }
            instance[key] = [];
        });
        // Remove old per-group handler (legacy) and unified handler
        if (instance._collisionHandler) {
            map.off('moveend', instance._collisionHandler);
            map.off('zoomend', instance._collisionHandler);
            instance._collisionHandler = null;
        }

        const mapUuid = (vars && vars.contentMapUuid) || '';
        if (!mapUuid) return;

        const wOpts = (vars && vars.vars) || {};
        const showSiteLabel    = wOpts.show_site_label   === true || wOpts.show_site_label   === 'true';
        const showZoneLabel    = wOpts.show_zone_label   === true || wOpts.show_zone_label   === 'true';
        const showDeviceLabels = wOpts.show_device_labels === true || wOpts.show_device_labels === 'true';
        const labelCollision   = wOpts.enable_label_collision !== false && wOpts.enable_label_collision !== 'false';
        const _rawSpacing      = parseInt(wOpts.label_spacing);
        const labelSpacing     = (!isNaN(_rawSpacing) && wOpts.label_spacing !== '' && wOpts.label_spacing !== null && wOpts.label_spacing !== undefined) ? _rawSpacing : 0;
        const globalLabelSize  = parseFloat(wOpts.global_label_size) || 1.0;
        const labelFontPx      = Math.round(globalLabelSize * 14);

        // Skip if no label type is enabled
        if (!showSiteLabel && !showZoneLabel && !showDeviceLabels) return;

        // Build allowed device ID set (mirrors addDeviceMarkers) so device labels
        // only render for devices the widget is configured to display.
        const allowedDeviceIds = new Set();
        const _fetchIdsLbl = wOpts.map_device_ids || wOpts.device_ids;
        if (_fetchIdsLbl && wOpts.include_all_devices !== true) {
            String(_fetchIdsLbl).split(',').forEach(function(id) {
                const t = id.trim();
                if (t) {
                    allowedDeviceIds.add(t);
                    if (t.includes('::')) allowedDeviceIds.add(t.split('::')[0]);
                }
            });
        }
        const isStrictDeviceLabelFilter = (allowedDeviceIds.size > 0 && wOpts.include_all_devices !== true);

        const COLOR_MAP = {
            'site':       '#DF5353',
            'zone':       '#28a745',
            'facility':   '#82898f',
            'equipment':  '#007bff',
            'device':     '#995aff',
            'aot_device': '#995aff'
        };
        const ZINDEX_MAP = {
            'site':       5,
            'zone':       3,
            'facility':   2,
            'equipment':  2,
            'device':     2,
            'aot_device': 2
        };

        try {
            const url = '/api/geo/overlays?map_uuid=' + encodeURIComponent(mapUuid) + '&type=label_aux';
            const res = await fetch(url);
            if (!res.ok) return;

            const geojson = await res.json();
            if (!geojson.features || geojson.features.length === 0) return;

            if (!instance.labelMarkers) instance.labelMarkers = [];

            geojson.features.forEach(function(feature) {
                if (!feature.geometry || feature.geometry.type !== 'Point') return;
                const coords = feature.geometry.coordinates;
                const props = feature.properties || {};
                const pType = props.parent_type || '';

                // Respect show_site_label / show_zone_label / show_device_labels options
                if (pType === 'site' && !showSiteLabel) return;
                if (pType === 'zone' && !showZoneLabel) return;
                if (pType === 'aot_device' && !showDeviceLabels) return;

                // Strict device-label filtering: hide labels for devices not in selection
                if (pType === 'aot_device' && isStrictDeviceLabelFilter) {
                    const _devLabelId = String(props.device_id || props.parent_id || props.db_id || '');
                    const _devLabelBase = _devLabelId.split('::')[0];
                    if (!allowedDeviceIds.has(_devLabelId) && !allowedDeviceIds.has(_devLabelBase)) return;
                }

                const color  = COLOR_MAP[pType] || '#666';
                const zIndex = ZINDEX_MAP[pType] || 2;
                const name   = props.label_name || '';
                const area   = props.label_area  || '';

                const el = document.createElement('div');
                el.className = 'geo-label-marker';
                el.dataset.labelName  = name;
                el.dataset.labelColor = color;
                el.style.cssText = [
                    'background-color:' + color,
                    'color:white',
                    'border-radius:4px',
                    'padding:2px 8px',
                    'box-shadow:0 2px 4px rgba(0,0,0,0.3)',
                    'text-align:center',
                    'font-size:' + labelFontPx + 'px',
                    'cursor:pointer',
                    'white-space:nowrap'
                ].join(';');
                // Store parent type/id for device-state refresh in the periodic cycle
                el.dataset.parentType = pType;
                el.dataset.parentId   = String(props.parent_id || props.db_id || '');

                const nameDiv = document.createElement('div');
                nameDiv.style.fontWeight = 'bold';
                nameDiv.textContent = name;
                el.appendChild(nameDiv);

                // [3-way Actuator] Empty value slot for aot_device labels.
                // Filled in _updateGeoDesignDeviceLabels when device state arrives.
                if (pType === 'aot_device') {
                    const valSpan = document.createElement('span');
                    valSpan.className = 'aot-3way-pct';
                    valSpan.style.cssText = 'margin-left:4px;font-weight:bold;display:none;';
                    nameDiv.appendChild(valSpan);
                }

                const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
                    .setLngLat([coords[0], coords[1]])
                    .addTo(map);

                el.style.zIndex = String(zIndex);

                // Click → popup (v3 port: name + Open Notes button + last note preview)
                (function(lngLat, popupName, popupArea, tId, tType) {
                    el.addEventListener('click', function(e) {
                        e.stopPropagation();
                        if (instance._labelPopup) { instance._labelPopup.remove(); }
                        var noteElId = 'label-note-' + tId;
                        var safeName = (popupName || '').replace(/'/g, "\\'");
                        var openNoteAction = 'window.dispatchEvent(new CustomEvent(\'open-notes\',{detail:{targetId:\'' + tId + '\',targetType:\'' + tType + '\',name:\'' + safeName + '\'}}))';
                        var html = '<div style="min-width:180px;padding:5px;">'
                            + '<div class="aot-popup-title" style="font-size:1.4em;font-weight:bold;margin:0;line-height:1.2;word-break:break-all;padding-top:15px;margin-bottom:8px;color:#333;">' + popupName + '</div>'
                            + (popupArea ? '<div style="font-size:0.85em;color:#888;margin-bottom:6px;">' + popupArea + '</div>' : '')
                            + '<hr style="margin:8px 0;border-top:1px solid #eee;">'
                            + '<div style="display:flex;flex-direction:column;gap:6px;">'
                            + '<button class="btn btn-primary" style="border-radius:14px;height:28px;width:100%;font-size:0.9em;display:flex;align-items:center;justify-content:center;padding:0;" onclick="' + openNoteAction + '">'
                            + '<i class="fas fa-clipboard mr-2"></i> ' + (window._ ? window._('Open Notes') : 'Open Notes') + '</button>'
                            + '<div id="' + noteElId + '" style="font-size:0.85em;color:#888;padding-left:4px;overflow:hidden;white-space:nowrap;text-overflow:ellipsis;">'
                            + (window._ ? window._('Loading...') : 'Loading...') + '</div>'
                            + '</div></div>';
                        instance._labelPopup = new maplibregl.Popup({ offset: 12, closeOnClick: true, className: 'aot-map-popup' })
                            .setLngLat(lngLat)
                            .setHTML(html)
                            .addTo(map);
                        // Fetch last note
                        setTimeout(function() {
                            fetch('/notes/target/' + tId)
                                .then(function(r) { return r.json(); })
                                .then(function(notes) {
                                    var el = document.getElementById(noteElId);
                                    if (!el) return;
                                    if (notes && notes.length > 0) {
                                        var txt = notes[0].note || '';
                                        el.innerText = txt.substring(0, 30) + (txt.length > 30 ? '...' : '');
                                        el.style.color = '#555';
                                    } else {
                                        el.innerText = window._ ? window._('No notes written') : 'No notes written';
                                        el.style.color = '#ccc';
                                    }
                                }).catch(function() {});
                        }, 100);
                    });
                }([coords[0], coords[1]], name, area,
                  props.db_id || props.parent_id || name,
                  props.parent_type || 'site'));

                instance.labelMarkers.push(marker);
                // Split by group: site+zone vs aot_device
                if (pType === 'site' || pType === 'zone') {
                    instance.siteZoneLabelMarkers.push(marker);
                } else if (pType === 'aot_device') {
                    instance.geoDeviceLabelMarkers.push(marker);
                }
            });

            // Unified collision — all groups in priority order via single handler
            if (labelCollision) {
                instance._labelSpacing = labelSpacing;
                _updateUnifiedCollisionHandler(instance, map, labelSpacing);
                map.once('idle', function() {
                    _runUnifiedLabelCollision(instance, map, labelSpacing);
                });
            }

            console.log('[AoT Vector Widget] Loaded ' + instance.labelMarkers.length + ' geo/design labels');
        } catch (e) {
            console.warn('[AoT Vector Widget] Failed to load geo/design labels:', e);
        }
    }

    /**
     * Add GeoJSON layer to map.
     *
     * @param {object} layerConfig  { type: 'fill'|'line'|'fill-extrusion', paint: {...}, layout?: {...} }
     */
    function addGeoJSONLayer(uniqueId, map, sourceId, geojson, layerConfig, layerId) {
        const instance = window.AoTWidgetInstances[uniqueId];
        if (!instance) return;

        const actualLayerId = layerId || sourceId;
        const layerType = layerConfig && layerConfig.type;
        const paintProps = (layerConfig && layerConfig.paint) || {};

        // Add source if not exists
        if (!map.getSource(sourceId)) {
            map.addSource(sourceId, {
                type: 'geojson',
                data: geojson
            });
            instance.sources.set(sourceId, geojson);
        }

        // Add layer
        if (!map.getLayer(actualLayerId)) {
            const layerDef = {
                id: actualLayerId,
                type: layerType,
                source: sourceId,
                paint: paintProps
            };
            if (layerConfig && layerConfig.layout) {
                layerDef.layout = layerConfig.layout;
            }
            map.addLayer(layerDef);


            instance.layers.set(actualLayerId, layerType);
        }
    }

    /**
     * Build a tool button (matches /geo/design styling).
     */
    function _toolBtn(id, iconCls, title, classes) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.id = id;
        btn.className = 'btn btn-white' + (classes ? ' ' + classes : '');
        btn.title = title || '';
        const i = document.createElement('i');
        i.className = iconCls;
        btn.appendChild(i);
        return btn;
    }

    function _setMapInteraction(map, enabled) {
        const handlers = ['dragPan', 'scrollZoom', 'boxZoom', 'doubleClickZoom', 'touchZoomRotate', 'keyboard'];
        handlers.forEach(function(h) {
            if (map[h]) {
                try { enabled ? map[h].enable() : map[h].disable(); } catch (e) {}
            }
        });
    }

    /**
     * Add control buttons.
     * Left rail (custom HTML, simple direct map calls): zoom, fullscreen,
     * search, locate, reset, lock, hide.
     * Site-list / Layers / Note / Measure: delegated to the existing
     * AoTMapCustomControls factories (same code that powers /geo/design).
     */
    function addControlButtons(uniqueId, map, vars) {
        const LOG = '[AoT Map]';
        const mapContainer = map.getContainer();
        const widgetWrap = document.getElementById('aot-map-' + uniqueId) || mapContainer;
        widgetWrap.style.position = widgetWrap.style.position || 'relative';

        // Warn once if map.css didn't load (the toolbar would render but be invisible).
        const probe = document.createElement('div');
        probe.className = 'map-tools-right';
        probe.style.visibility = 'hidden';
        document.body.appendChild(probe);
        const probeZ = window.getComputedStyle(probe).zIndex;
        document.body.removeChild(probe);
        if (probeZ === 'auto' || probeZ === '') {
            console.warn(LOG, 'map.css not loaded — /static/css/map/map.css is missing.');
        }

        const isLocked = !!vars.isLocked;
        const isHidden = !!vars.hideControls;

        // ---------- LEFT TOOLBAR ----------
        const left = document.createElement('div');
        left.className = 'map-tools-left';
        left.style.cssText = 'position:absolute; top:10px; left:10px; z-index:20; pointer-events:auto;';

        // Group: Zoom in/out (+ native compass injected after creation)
        const zoomGroup = document.createElement('div');
        zoomGroup.className = 'tool-group';
        const btnZoomIn  = _toolBtn(`tool-zoom-in-${uniqueId}`,  'fas fa-plus',  'Zoom In');
        const btnZoomOut = _toolBtn(`tool-zoom-out-${uniqueId}`, 'fas fa-minus', 'Zoom Out');
        zoomGroup.appendChild(btnZoomIn);
        zoomGroup.appendChild(btnZoomOut);
        left.appendChild(zoomGroup);

        // Compass-only NavigationControl, attached then moved into zoomGroup so
        // it shares the left rail with zoom +/- (matches /geo/design layout).
        try {
            const navCtrl = new maplibregl.NavigationControl({
                showCompass: true,
                showZoom: false,
                visualizePitch: true
            });
            map.addControl(navCtrl, 'top-left');
            // The control's DOM is inserted next frame; relocate it.
            requestAnimationFrame(function() {
                const nativeGroup = mapContainer.querySelector('.maplibregl-ctrl-top-left .maplibregl-ctrl-group');
                if (nativeGroup) {
                    zoomGroup.appendChild(nativeGroup);
                }
            });
        } catch (e) {}

        // Group: Fullscreen / Search / Locate / Reset
        const navGroup = document.createElement('div');
        navGroup.className = 'tool-group mt-2';
        const btnFs     = _toolBtn(`tool-fullscreen-${uniqueId}`, 'fas fa-expand',     'Fullscreen');
        const btnSearch = _toolBtn(`tool-search-${uniqueId}`,     'fas fa-search',     'Search Address');
        const btnLocate = _toolBtn(`tool-locate-${uniqueId}`,     'fas fa-crosshairs', 'My Location');
        const btnReset  = _toolBtn(`tool-reset-${uniqueId}`,      'fas fa-undo',       'Reset View');
        navGroup.appendChild(btnFs);
        navGroup.appendChild(btnSearch);
        navGroup.appendChild(btnLocate);
        navGroup.appendChild(btnReset);
        left.appendChild(navGroup);

        // Lock toggle
        const btnLock = _toolBtn(`tool-lock-${uniqueId}`,
            isLocked ? 'fas fa-lock' : 'fas fa-unlock',
            isLocked ? 'Unlock Map' : 'Lock Map',
            'btn-circle mt-2');
        btnLock.dataset.locked = isLocked ? 'true' : 'false';
        left.appendChild(btnLock);

        // Hide-controls toggle
        const btnHide = _toolBtn(`tool-hide-${uniqueId}`,
            isHidden ? 'fas fa-eye-slash' : 'fas fa-eye',
            isHidden ? 'Show Button' : 'Hide Button',
            'btn-circle mt-2');
        btnHide.dataset.hidden = isHidden ? 'true' : 'false';
        left.appendChild(btnHide);

        // Site list button (back on the left rail where it used to live)
        const btnSiteList = _toolBtn(`tool-site-list-${uniqueId}`,
            'fas fa-list', 'Site List', 'btn-circle mt-2');
        left.appendChild(btnSiteList);
        const sitePop = document.createElement('div');
        sitePop.id = `site-list-popover-${uniqueId}`;
        sitePop.className = 'bg-white shadow-lg rounded border';
        sitePop.style.cssText = 'display:none; position:absolute; left:40px; top:130px; width:200px; overflow-y:auto; z-index:30;';
        left.appendChild(sitePop);

        function _adjustSitePopHeight() {
            const wrapRect = widgetWrap.getBoundingClientRect();
            const popRect = sitePop.getBoundingClientRect();
            const available = wrapRect.bottom - popRect.top - 10;
            sitePop.style.maxHeight = Math.max(80, available) + 'px';
        }
        if (map && typeof map.on === 'function') {
            map.on('resize', function() {
                if (sitePop.style.display === 'block') _adjustSitePopHeight();
            });
        }
        if (typeof ResizeObserver !== 'undefined') {
            new ResizeObserver(function() {
                if (sitePop.style.display === 'block') _adjustSitePopHeight();
            }).observe(widgetWrap);
        }

        widgetWrap.appendChild(left);

        // Note / Measure / Layers buttons are built together in addLayerPanel()
        // into a single right-rail toolbar for correct vertical alignment.

        // ---------- WIRE HANDLERS ----------
        function _wire(btn, label, fn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                try { fn(e); } catch (err) {
                    console.error(LOG, label, 'failed:', err);
                }
            });
        }

        _wire(btnZoomIn,  'zoom-in',  function() { map.zoomIn(); });
        _wire(btnZoomOut, 'zoom-out', function() { map.zoomOut(); });

        _wire(btnFs, 'fullscreen', function() {
            const target = widgetWrap;
            const doc = document;
            if (!doc.fullscreenElement && target.requestFullscreen) {
                target.requestFullscreen();
            } else if (doc.exitFullscreen) {
                doc.exitFullscreen();
            } else {
                target.classList.toggle('aot-map-pseudo-fullscreen');
            }
        });

        _wire(btnSearch, 'search', function() {
            const overlay = document.getElementById('search-overlay-' + uniqueId);
            if (overlay) overlay.classList.toggle('d-none');
        });

        _wire(btnLocate, 'locate', function() {
            if (!navigator.geolocation) return;
            navigator.geolocation.getCurrentPosition(function(pos) {
                map.flyTo({ center: [pos.coords.longitude, pos.coords.latitude], zoom: 16 });
            }, function(err) {
                console.warn(LOG, 'geolocation:', err.message);
            });
        });

        _wire(btnReset, 'reset', function() {
            const lat = parseFloat((vars.geoConfig && vars.geoConfig.settings && vars.geoConfig.settings.default_lat) || vars.default_lat) || 37.5665;
            const lng = parseFloat((vars.geoConfig && vars.geoConfig.settings && vars.geoConfig.settings.default_lng) || vars.default_lng) || 126.978;
            const z   = parseFloat((vars.geoConfig && vars.geoConfig.settings && vars.geoConfig.settings.zoom) || vars.default_zoom) || 12;
            map.flyTo({ center: [lng, lat], zoom: z, pitch: 0, bearing: 0 });
        });

        _wire(btnLock, 'lock', function() {
            const locked = btnLock.dataset.locked !== 'true';
            btnLock.dataset.locked = locked ? 'true' : 'false';
            const ic = btnLock.querySelector('i');
            if (ic) ic.className = locked ? 'fas fa-lock' : 'fas fa-unlock';
            btnLock.title = locked ? 'Unlock Map' : 'Lock Map';
            _setMapInteraction(map, !locked);
            fetch('/save_widget_custom_options', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ widget_id: (vars && vars.widgetId) || uniqueId, options: { map_locked: locked } })
            }).catch(function(e) { console.warn('[AoT Map] saveLock:', e); });
        });

        _wire(btnHide, 'hide-button', function() {
            const hidden = btnHide.dataset.hidden !== 'true';
            btnHide.dataset.hidden = hidden ? 'true' : 'false';
            const ic = btnHide.querySelector('i');
            if (ic) ic.className = hidden ? 'fas fa-eye-slash' : 'fas fa-eye';
            btnHide.title = hidden ? 'Show Button' : 'Hide Button';
            const disp = hidden ? 'none' : '';
            // Hide/show all controls except the hide button itself
            [zoomGroup, navGroup, btnLock, btnSiteList, sitePop].forEach(function(el) {
                if (el) el.style.display = disp;
            });
            const rightToolbar = widgetWrap.querySelector('#map-tools-right-' + uniqueId);
            if (rightToolbar) rightToolbar.style.display = disp;
            fetch('/save_widget_custom_options', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ widget_id: (vars && vars.widgetId) || uniqueId, options: { hide_controls: hidden } })
            }).catch(function(e) { console.warn('[AoT Map] saveHide:', e); });
        });

        // Site list popover toggle — reads from instance.sites which is
        // rehydrated from /api/geo/overlays after map load (see refreshSiteList).
        _wire(btnSiteList, 'site-list', function() {
            const inst = window.AoTWidgetInstances[uniqueId] || {};
            const inner = (vars && vars.vars) || {};
            const sites = (inst.sites && inst.sites.length) ? inst.sites : (inner.sites_in_map || []);
            sitePop.innerHTML = '';
            const ul = document.createElement('ul');
            ul.className = 'list-group list-group-flush small';
            if (!sites.length) {
                const empty = document.createElement('li');
                empty.className = 'list-group-item text-muted small';
                empty.textContent = 'No registered sites.';
                ul.appendChild(empty);
            } else {
                sites.forEach(function(s) {
                    const li = document.createElement('li');
                    li.className = 'list-group-item list-group-item-action';
                    li.style.cursor = 'pointer';
                    li.textContent = s.name || s.id || '(unnamed)';
                    li.addEventListener('click', function() {
                        if (s.lat != null && s.lng != null) {
                            map.flyTo({ center: [parseFloat(s.lng), parseFloat(s.lat)], zoom: s.zoom || 17 });
                        }
                        sitePop.style.display = 'none';
                    });
                    ul.appendChild(li);
                });
            }
            sitePop.appendChild(ul);
            const opening = sitePop.style.display === 'none';
            sitePop.style.display = opening ? 'block' : 'none';
            if (opening) _adjustSitePopHeight();
        });
        document.addEventListener('click', function(e) {
            if (!btnSiteList.contains(e.target) && !sitePop.contains(e.target)) {
                sitePop.style.display = 'none';
            }
        });

        // Initial lock state
        if (isLocked) _setMapInteraction(map, false);

        // Initial hide state
        if (isHidden) {
            [zoomGroup, navGroup, btnLock, btnSiteList, sitePop].forEach(function(el) {
                if (el) el.style.display = 'none';
            });
            const rightToolbar = widgetWrap.querySelector('#map-tools-right-' + uniqueId);
            if (rightToolbar) rightToolbar.style.display = 'none';
        }

        // Track for cleanup
        const inst = window.AoTWidgetInstances[uniqueId];
        if (inst) inst.toolbarLeft = left;
    }

    /**
     * Compute a rough center for a GeoJSON geometry (average of all coords).
     * Good enough for fly-to. Used by refreshSiteList for site centers.
     */
    function _computeCenter(geometry) {
        if (!geometry || !geometry.coordinates) return null;
        const lngs = [], lats = [];
        (function walk(arr) {
            if (typeof arr[0] === 'number') { lngs.push(arr[0]); lats.push(arr[1]); }
            else if (Array.isArray(arr)) { arr.forEach(walk); }
        })(geometry.coordinates);
        if (!lngs.length) return null;
        return {
            lng: lngs.reduce(function(a, b) { return a + b; }, 0) / lngs.length,
            lat: lats.reduce(function(a, b) { return a + b; }, 0) / lats.length
        };
    }

    /**
     * Fetch /api/geo/overlays for the widget's selected map, filter site
     * features, compute centers, store on instance.sites for the site-list
     * popover. Direct port of v3 logic at v3.js:744-813.
     */
    function refreshSiteList(uniqueId, map, vars) {
        const instance = window.AoTWidgetInstances[uniqueId];
        if (!instance) return;
        const mapUuid = vars && vars.contentMapUuid;
        if (!mapUuid) {
            // Fall back to whatever the server pre-populated.
            instance.sites = (vars && vars.vars && vars.vars.sites_in_map) || [];
            return;
        }
        fetch('/api/geo/overlays?map_uuid=' + encodeURIComponent(mapUuid))
            .then(function(r) { return r.json(); })
            .then(function(data) {
                const features = (data && data.features) || [];
                const sites = [];
                features.forEach(function(f) {
                    const p = f.properties || {};
                    if (String(p.aot_type || '').toLowerCase() !== 'site') return;
                    let lat = null, lng = null;
                    if (p.center_lat != null && p.center_lng != null) {
                        lat = parseFloat(p.center_lat);
                        lng = parseFloat(p.center_lng);
                    } else if (f.geometry) {
                        const c = _computeCenter(f.geometry);
                        if (c) { lat = c.lat; lng = c.lng; }
                    }
                    if (lat != null && lng != null && !isNaN(lat) && !isNaN(lng)) {
                        sites.push({
                            name: p.label_name || p.name || ('Site ' + (p.db_id || p.id || '')),
                            lat: lat,
                            lng: lng,
                            zoom: 17
                        });
                    }
                });
                instance.sites = sites;
            })
            .catch(function(e) { console.error('[AoT Map] refreshSiteList:', e); });
    }

    /**
     * Unified right toolbar: Layers button (+ panel) / Measure / Note.
     * All three buttons live in a single flex-column container at top-right
     * so they are always vertically aligned with consistent 5px gaps.
     *
     * Layer selection is persisted per-widget via /save_widget_custom_options.
     * On overlay change, the legend is also refreshed via instance.refreshLegend.
     */

    /**
     * Resolve active overlay names from innerVars.active_layers.
     * Python returns a list of layer objects with a `visible` flag; older paths
     * may pass a comma-separated string or a plain array of name strings.
     */
    function _resolveActiveOverlayNames(rawActiveLayers) {
        if (!rawActiveLayers) return [];
        if (Array.isArray(rawActiveLayers)) {
            if (rawActiveLayers.length && rawActiveLayers[0] !== null && typeof rawActiveLayers[0] === 'object') {
                // Layer objects from Python — extract names of visible overlays
                return rawActiveLayers
                    .filter(function(l) { return l && l.visible && !(l.is_base || l.role === 'base'); })
                    .map(function(l) { return l.name || l.id || ''; })
                    .filter(Boolean);
            }
            // Array of plain strings
            return rawActiveLayers.map(function(s) { return String(s).trim(); }).filter(Boolean);
        }
        // Comma-separated string fallback
        return String(rawActiveLayers).split(',').map(function(s) { return s.trim(); }).filter(Boolean);
    }

    function addLayerPanel(uniqueId, map, vars) {
        const mapContainer = map.getContainer();
        mapContainer.style.position = mapContainer.style.position || 'relative';

        const geoLayers = (vars && vars.geoConfig && vars.geoConfig.layers)
            || (window.AOT_GEO_CONFIG && window.AOT_GEO_CONFIG.layers)
            || [];

        const innerVars = (vars && vars.vars) || {};
        let activeBase = innerVars.selected_base_layer || null;
        let activeOverlays = _resolveActiveOverlayNames(innerVars.active_layers);

        // ---- Unified right toolbar ----
        const toolbar = document.createElement('div');
        toolbar.id = 'map-tools-right-' + uniqueId;
        toolbar.style.cssText = 'position:absolute; top:10px; right:10px; z-index:20; display:flex; flex-direction:column; align-items:center; gap:5px;';
        mapContainer.appendChild(toolbar);
        const _rightHidden = !!(vars && vars.hideControls);
        if (_rightHidden) toolbar.style.display = 'none';

        // ---- Layer button + panel (sub-container so panel anchors correctly) ----
        const layerWrap = document.createElement('div');
        layerWrap.style.cssText = 'position:relative;';
        toolbar.appendChild(layerWrap);

        const btn = document.createElement('a');
        btn.href = '#';
        btn.className = 'btn btn-white btn-circle';
        btn.title = (typeof window._ === 'function') ? window._('Layers') : 'Layers';
        btn.id = 'tool-layers-' + uniqueId;
        btn.setAttribute('role', 'button');
        const icon = document.createElement('i');
        icon.className = 'fas fa-layer-group';
        btn.appendChild(icon);
        layerWrap.appendChild(btn);

        const panel = document.createElement('div');
        panel.style.cssText = 'display:none; position:absolute; top:45px; right:0; background:white; padding:10px; border-radius:8px; box-shadow:0 2px 8px rgba(0,0,0,0.25); min-width:220px; overflow-y:auto; z-index:30; font-size:12px;';
        layerWrap.appendChild(panel);

        function _adjustLayerPanelHeight() {
            const containerRect = mapContainer.getBoundingClientRect();
            const panelRect = panel.getBoundingClientRect();
            const available = containerRect.bottom - panelRect.top - 10;
            panel.style.maxHeight = Math.max(80, available) + 'px';
        }
        if (map && typeof map.on === 'function') {
            map.on('resize', function() {
                if (panel.style.display === 'block') _adjustLayerPanelHeight();
            });
        }
        if (typeof ResizeObserver !== 'undefined') {
            new ResizeObserver(function() {
                if (panel.style.display === 'block') _adjustLayerPanelHeight();
            }).observe(mapContainer);
        }

        // ---- Measure + Memo buttons via factories, moved into toolbar ----
        if (window.AoTMapCustomControls) {
            ['createMeasureControl', 'createMemoControl'].forEach(function(fn) {
                try {
                    const result = window.AoTMapCustomControls[fn](map, {});
                    if (result && result.container) {
                        // Factory appended to mapContainer — detach and re-parent
                        if (result.container.parentNode) {
                            result.container.parentNode.removeChild(result.container);
                        }
                        // Clear absolute positioning so flex column controls placement
                        result.container.style.cssText = '';
                        result.container.classList.remove('aot-mr-10');
                        toolbar.appendChild(result.container);
                    }
                } catch (e) { console.error('[AoT Map] ' + fn + ' failed:', e); }
            });
        }

        // ---- Custom Options group: device-type label toggles + measurement hide ----
        (function() {
            var widgetId = (vars && vars.widgetId) || uniqueId;
            var innerVars = (vars && vars.vars) || {};
            var _lsPrefix = 'aot_map_toggle_' + widgetId + '_';

            function _lsGet(key) {
                try { var v = localStorage.getItem(_lsPrefix + key); return v === 'true' ? true : v === 'false' ? false : null; } catch(e) { return null; }
            }
            function _lsSet(key, val) {
                try { localStorage.setItem(_lsPrefix + key, val ? 'true' : 'false'); } catch(e) {}
            }

            function _readSaved(saveKey) {
                // Server-side state takes priority; fall back to localStorage if server returns nothing
                var sv = innerVars[saveKey];
                if (sv === true || sv === 'true') return true;
                if (sv === false || sv === 'false') return false;
                // sv is undefined/null → server didn't provide it; check localStorage
                var lv = _lsGet(saveKey);
                return lv === true;
            }

            function _saveToggleState(patch) {
                fetch('/save_widget_custom_options', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ widget_id: widgetId, options: patch })
                }).catch(function(e) { console.warn('[AoT Map] saveToggle:', e); });
                // Mirror to localStorage as backup
                Object.keys(patch).forEach(function(k) { _lsSet(k, patch[k]); });
            }

            function _applyTypeHide(type, hidden) {
                var inst = window.AoTWidgetInstances[uniqueId];
                if (!inst) return;

                // 1. Device markers (pill / dot) stored in instance.markers
                if (inst.markers) {
                    inst.markers.forEach(function(marker) {
                        if (!marker || typeof marker.getElement !== 'function') return;
                        var el = marker.getElement();
                        if (!el || el.dataset.deviceType !== type) return;
                        el.classList.toggle('aot-type-hidden', hidden);
                    });
                }

                // 2. Geo-design device labels stored in instance.geoDeviceLabelMarkers
                //    These have dataset.parentId (device base UUID) — look up via _deviceTypeMap
                var typeMap = inst._deviceTypeMap || {};
                (inst.geoDeviceLabelMarkers || []).forEach(function(marker) {
                    if (!marker || typeof marker.getElement !== 'function') return;
                    var el = marker.getElement();
                    if (!el) return;
                    var parentId = el.dataset.parentId || '';
                    if (typeMap[parentId] !== type) return;
                    el.classList.toggle('aot-type-hidden', hidden);
                });

                // Persist on instance so addDeviceMarkers applies on re-render
                if (!inst._hiddenTypes) inst._hiddenTypes = {};
                inst._hiddenTypes[type] = hidden;
            }

            var customGroup = document.createElement('div');
            customGroup.className = 'tool-group mt-2';

            var deviceTypes = [
                { type: 'input',    icon: 'fas fa-thermometer-half', title: 'Input 라벨 켜기/끄기',    saveKey: 'label_hidden_input' },
                { type: 'output',   icon: 'fas fa-sliders-h',         title: 'Output 라벨 켜기/끄기',   saveKey: 'label_hidden_output' },
                { type: 'function', icon: 'fas fa-code-branch',        title: 'Function 라벨 켜기/끄기', saveKey: 'label_hidden_function' }
            ];

            deviceTypes.forEach(function(dt) {
                // Read saved state (server-side primary, localStorage fallback)
                var savedHidden = _readSaved(dt.saveKey);

                var btn = _toolBtn('tool-label-' + dt.type + '-' + uniqueId, dt.icon, dt.title);
                customGroup.appendChild(btn);

                // Apply saved state to button appearance immediately
                if (savedHidden) btn.style.opacity = '0.4';

                // Store initial state on instance for addDeviceMarkers timing
                var inst = window.AoTWidgetInstances[uniqueId];
                if (inst) {
                    if (!inst._hiddenTypes) inst._hiddenTypes = {};
                    inst._hiddenTypes[dt.type] = savedHidden;
                }

                // Apply saved hide state after markers are rendered (delayed to catch async fetch)
                if (savedHidden) {
                    setTimeout(function(type) {
                        return function() { _applyTypeHide(type, true); };
                    }(dt.type), 500);
                    setTimeout(function(type) {
                        return function() { _applyTypeHide(type, true); };
                    }(dt.type), 1500);
                    setTimeout(function(type) {
                        return function() { _applyTypeHide(type, true); };
                    }(dt.type), 3000);
                }

                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    var inst2 = window.AoTWidgetInstances[uniqueId];
                    if (!inst2._hiddenTypes) inst2._hiddenTypes = {};
                    var hidden = !inst2._hiddenTypes[dt.type];
                    btn.style.opacity = hidden ? '0.4' : '1';
                    _applyTypeHide(dt.type, hidden);
                    var patch = {};
                    patch[dt.saveKey] = hidden;
                    _saveToggleState(patch);
                });
            });

            // Measurements hide button
            var savedMeasHidden = _readSaved('label_hidden_meas');
            var measBtn = _toolBtn('tool-meas-hide-' + uniqueId, 'fas fa-tachometer-alt', '측정값 숨기기');
            customGroup.appendChild(measBtn);
            if (savedMeasHidden) measBtn.style.opacity = '0.4';

            // Apply saved meas-hide state after panel is created (slight delay)
            if (savedMeasHidden) {
                setTimeout(function() {
                    var inst = window.AoTWidgetInstances[uniqueId];
                    if (!inst || !inst.measurementPanel) return;
                    var handle = inst.measurementPanel;
                    var panelEl = (handle && handle.panel) ? handle.panel
                                : (handle instanceof HTMLElement) ? handle : null;
                    if (panelEl) panelEl.style.display = 'none';
                }, 300);
            }

            measBtn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                var inst = window.AoTWidgetInstances[uniqueId];
                if (!inst) return;
                inst._measHidden = !inst._measHidden;
                measBtn.style.opacity = inst._measHidden ? '0.4' : '1';
                var handle = inst.measurementPanel;
                if (handle) {
                    var panelEl = (handle && handle.panel) ? handle.panel
                                : (handle instanceof HTMLElement) ? handle : null;
                    if (panelEl) panelEl.style.display = inst._measHidden ? 'none' : '';
                }
                _saveToggleState({ label_hidden_meas: inst._measHidden });
            });

            // Initialise _measHidden on instance
            var inst0 = window.AoTWidgetInstances[uniqueId];
            if (inst0) inst0._measHidden = savedMeasHidden;

            toolbar.appendChild(customGroup);
        })();

        // ---- Map-side application helpers ----
        const _baseStyleIds = ((map.getStyle() || {}).layers || []).map(function(l) { return l.id; });
        let _activeRasterBaseId = null;

        // Cache with TTL (5 min) so stale timestamps don't cause 410 Gone.
        const _tsCache = {};
        const _TS_TTL = 5 * 60 * 1000;

        // Extract timestamp from RainViewer meta — mirrors input-preview.js logic.
        function _extractRainviewerTs(meta) {
            if (!meta || !meta.radar) return null;
            const past = (meta.radar.past || []);
            const nowcast = (meta.radar.nowcast || []);
            const last = past.length ? past[past.length - 1] : (nowcast.length ? nowcast[0] : null);
            if (!last) return null;
            if (last.path) {
                const parts = String(last.path).split('/').filter(Boolean);
                return parts.length ? parts[parts.length - 1] : null;
            }
            return last.time ? String(last.time) : null;
        }

        function _buildSource(l, resolvedUrl) {
            if (map.getSource(l.id)) return;
            // Never create a source with an unresolved {ts} — it will 404.
            if (resolvedUrl && resolvedUrl.indexOf('{ts}') !== -1) {
                console.warn('[AoT Map] Skipping source — {ts} unresolved:', l.id);
                return;
            }
            const opts = (l.options) || {};
            const tileSize = parseInt(opts.tileSize || opts.tile_size) || 256;
            const tiles = _toTilesFromUrl(l, resolvedUrl);
            const spec = { type: 'raster', tiles: tiles, tileSize: tileSize };
            const maxNative = parseInt(opts.maxNativeZoom || opts.max_native_zoom || opts.maxZoom || 0);
            if (maxNative > 0) spec.maxzoom = maxNative;
            const minNative = parseInt(opts.minZoom || opts.minNativeZoom || opts.min_zoom || 0);
            if (minNative > 0) spec.minzoom = minNative;
            try { map.addSource(l.id, spec); } catch (e) { console.warn('[AoT Map] addSource failed:', e); }
        }

        function _toTilesFromUrl(l, url) {
            url = (url || l.url || '').replace(/\{r\}/g, '');
            if (l.type === 'wms') {
                return ['/api/geo/proxy/wms/' + encodeURIComponent(l.id) + '?BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256'];
            }
            if (url.indexOf('{s}') !== -1) {
                return ['a', 'b', 'c'].map(function(s) { return url.replace(/\{s\}/g, s); });
            }
            return [url];
        }

        // Async: resolves {ts} via RainViewer API, then calls onReady().
        // Mirrors input-preview.js: direct API first, proxy fallback, path extraction.
        function _ensureSource(l, onReady) {
            if (map.getSource(l.id)) { onReady && onReady(); return; }
            const url = l.url || '';
            if (url.indexOf('{ts}') !== -1) {
                // Use cached timestamp if still fresh.
                const cached = _tsCache.rainviewer;
                if (cached && (Date.now() - cached.at < _TS_TTL)) {
                    _buildSource(l, url.replace(/\{ts\}/g, cached.ts));
                    onReady && onReady();
                    return;
                }
                // Direct API first (CORS-enabled); proxy as fallback.
                const _tryFetch = function(u) {
                    return fetch(u, { credentials: 'omit' })
                        .then(function(r) { return r.ok ? r.json() : null; })
                        .catch(function() { return null; });
                };
                _tryFetch('https://api.rainviewer.com/public/weather-maps.json')
                    .then(function(meta) {
                        return meta || _tryFetch('/api/geo/proxy/rainviewer/meta');
                    })
                    .then(function(meta) {
                        const ts = _extractRainviewerTs(meta);
                        if (ts) _tsCache.rainviewer = { ts: ts, at: Date.now() };
                        _buildSource(l, ts ? url.replace(/\{ts\}/g, ts) : url);
                        onReady && onReady();
                    })
                    .catch(function() { _buildSource(l, url); onReady && onReady(); });
                return;
            }
            _buildSource(l, url);
            onReady && onReady();
        }
        function _hideAllVectorBase() {
            _baseStyleIds.forEach(function(id) {
                try { map.setLayoutProperty(id, 'visibility', 'none'); } catch (e) {}
            });
        }
        function _showAllVectorBase() {
            _baseStyleIds.forEach(function(id) {
                try { map.setLayoutProperty(id, 'visibility', 'visible'); } catch (e) {}
            });
        }
        // Returns the first GeoJSON layer ID so raster tiles are inserted BEFORE it,
        // preventing raster tiles from covering GeoJSON shapes.
        function _getFirstGeoJSONLayerId() {
            const inst = window.AoTWidgetInstances[uniqueId];
            if (inst && inst.layers && inst.layers.size > 0) {
                return inst.layers.keys().next().value;
            }
            return undefined;
        }

        // Returns the first active overlay tile layer ID. Used to insert the raster
        // base BELOW overlays — prevents the base from covering overlay layers that
        // were added earlier with the same beforeId (first GeoJSON).
        function _getFirstOverlayLayerId() {
            for (var _oi = 0; _oi < geoLayers.length; _oi++) {
                var _ol = geoLayers[_oi];
                if (_ol.role === 'base' || _ol.is_base) continue;
                var _olyId = _ol.id + '_layer';
                if (map.getLayer(_olyId)) return _olyId;
            }
            return undefined;
        }

        // Re-stack GeoJSON shape layers (sites/zones/facilities/equipment/devices/drawn)
        // above all raster base/overlay layers so 2D rasters never cover shapes/labels.
        // Called after any raster add/show — covers cases where the raster was added
        // with beforeId=undefined (no shapes loaded yet at activation time) or where a
        // previously-hidden raster is re-shown without a fresh insertion point.
        function _promoteShapesToTop() {
            const inst = window.AoTWidgetInstances[uniqueId];
            if (!inst || !inst.layers) return;
            inst.layers.forEach(function(_type, layerId) {
                if (map.getLayer(layerId)) {
                    try { map.moveLayer(layerId); } catch (e) {}
                }
            });
        }

        function _activateRasterBase(l) {
            const lyId = l.id + '_layer';
            _ensureSource(l, function() {
                if (!map.getSource(l.id)) return;
                // Insert base BELOW any active overlay layers so overlays remain visible.
                // Fall back to first GeoJSON layer (shapes stay on top).
                const beforeId = _getFirstOverlayLayerId() || _getFirstGeoJSONLayerId();
                if (!map.getLayer(lyId)) {
                    try {
                        map.addLayer({ id: lyId, type: 'raster', source: l.id, layout: { visibility: 'visible' } }, beforeId);
                    } catch (e) {
                        console.warn('[AoT Map] addLayer raster base failed:', e);
                    }
                } else {
                    map.setLayoutProperty(lyId, 'visibility', 'visible');
                }
                // Guarantee shapes/labels remain on top regardless of insertion order
                // or whether shapes were loaded before activation.
                _promoteShapesToTop();
            });
            _activeRasterBaseId = l.id;
        }
        function _deactivateRasterBase() {
            if (!_activeRasterBaseId) return;
            const lyId = _activeRasterBaseId + '_layer';
            try { map.setLayoutProperty(lyId, 'visibility', 'none'); } catch (e) {}
            _activeRasterBaseId = null;
        }
        function _setOverlayVisible(l, visible) {
            if (visible) {
                const lyId = l.id + '_layer';
                _ensureSource(l, function() {
                    if (!map.getSource(l.id)) return;
                    const beforeId = _getFirstGeoJSONLayerId();
                    if (!map.getLayer(lyId)) {
                        try { map.addLayer({ id: lyId, type: 'raster', source: l.id, layout: { visibility: 'visible' } }, beforeId); } catch(e) {}
                    } else {
                        map.setLayoutProperty(lyId, 'visibility', 'visible');
                    }
                    // Same guarantee for overlay rasters — covers re-toggle cases where
                    // a previously-hidden overlay would otherwise stay below shapes only
                    // by accident of original insertion position.
                    _promoteShapesToTop();
                });
            } else {
                const lyId = l.id + '_layer';
                if (map.getLayer(lyId)) {
                    try { map.setLayoutProperty(lyId, 'visibility', 'none'); } catch (e) {}
                }
            }
        }

        // ---- Persistence ----
        function saveSelection() {
            const widgetId = (vars && vars.widgetId) || uniqueId;
            fetch('/save_widget_custom_options', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ widget_id: widgetId, options: { selected_base_layer: activeBase || '', active_layers: activeOverlays } })
            }).catch(function(e) { console.error('[AoT Map] saveSelection:', e); });
        }

        // ---- Render panel ----
        function render() {
            panel.innerHTML = '';
            if (!geoLayers.length) {
                panel.innerHTML = '<div style="color:#666;padding:8px;">활성화된 레이어 없음</div>';
                return;
            }
            const groups = { base: [], overlay: [] };
            geoLayers.forEach(function(l) {
                groups[(l.role === 'base' || l.is_base) ? 'base' : 'overlay'].push(l);
            });

            ['base', 'overlay'].forEach(function(role) {
                if (!groups[role].length) return;
                const head = document.createElement('div');
                head.style.cssText = 'font-weight:bold;color:#444;font-size:11px;text-transform:uppercase;letter-spacing:.5px;border-bottom:1px solid #eee;margin-bottom:4px;padding-bottom:2px;';
                head.textContent = role === 'base' ? '베이스 맵' : '오버레이';
                panel.appendChild(head);

                groups[role].forEach(function(l) {
                    const row = document.createElement('label');
                    row.style.cssText = 'display:flex;align-items:center;gap:6px;padding:3px 0;cursor:pointer;font-size:13px;';
                    const input = document.createElement('input');
                    if (role === 'base') {
                        input.type = 'radio';
                        input.name = 'layer-base-' + uniqueId;
                        input.checked = activeBase ? (l.name === activeBase) : false;
                    } else {
                        input.type = 'checkbox';
                        input.checked = activeOverlays.indexOf(l.name) !== -1;
                    }
                    input.dataset.layerId = l.id;
                    input.dataset.layerName = l.name;
                    input.addEventListener('change', function() {
                        if (role === 'base') {
                            activeBase = l.name;
                            // Base map always switches regardless of _dataOnly (only overlay tiles are suppressed)
                            _deactivateRasterBase();
                            if ((l.type || 'xyz') === 'vector' && l.url) {
                                try { map.setStyle(l.url, { diff: false }); } catch (e) { console.error('[AoT Map] setStyle:', e); }
                                // setStyle({ diff:false }) destroys all custom sources/layers — re-add after style loads
                                map.once('style.load', function() {
                                    const inst = window.AoTWidgetInstances[uniqueId];
                                    if (inst) { inst.sources.clear(); inst.layers.clear(); }
                                    loadGeoJSONLayers(uniqueId, map, vars);
                                    loadGeoDesignLabels(uniqueId, map, vars);
                                    if (vars.devices && vars.devices.length > 0) {
                                        addDeviceMarkers(uniqueId, map, vars.devices, vars.theme, vars);
                                    }
                                });
                            } else {
                                _activateRasterBase(l);
                            }
                        } else {
                            if (input.checked) {
                                if (activeOverlays.indexOf(l.name) === -1) activeOverlays.push(l.name);
                                if (!_dataOnly) _setOverlayVisible(l, true);
                            } else {
                                activeOverlays = activeOverlays.filter(function(n) { return n !== l.name; });
                                if (!_dataOnly) _setOverlayVisible(l, false);
                            }
                            // Refresh legend when overlay selection changes
                            const inst = window.AoTWidgetInstances[uniqueId];
                            if (inst && typeof inst.refreshLegend === 'function') {
                                inst.refreshLegend(activeOverlays);
                            }
                        }
                        saveSelection();
                    });
                    row.appendChild(input);
                    const span = document.createElement('span');
                    span.textContent = l.name || l.id;
                    row.appendChild(span);
                    panel.appendChild(row);
                });
            });
        }

        btn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            const opening = panel.style.display === 'none';
            panel.style.display = opening ? 'block' : 'none';
            if (opening) { render(); _adjustLayerPanelHeight(); }
        });
        document.addEventListener('click', function(e) {
            if (!layerWrap.contains(e.target)) panel.style.display = 'none';
        });

        // Apply initial overlay/base selection
        // In data-only mode skip tile rendering — legend data comes from geoConfig metadata, not tiles
        const _dataOnly = innerVars.overlay_data_only === true || innerVars.overlay_data_only === 'true';
        if (!_dataOnly) {
            geoLayers.forEach(function(l) {
                const isBase = (l.role === 'base' || l.is_base);
                if (isBase && activeBase && l.name === activeBase) {
                    if ((l.type || 'xyz') !== 'vector') _activateRasterBase(l);
                } else if (!isBase && activeOverlays.indexOf(l.name) !== -1) {
                    _setOverlayVisible(l, true);
                }
            });
        }

        const inst = window.AoTWidgetInstances[uniqueId];
        if (inst) {
            inst.layerPanelContainer = toolbar;
            inst.activeOverlays = activeOverlays;
        }
    }

    /**
     * Poll /notes/geo and render a marker for every note with GPS coords.
     * Direct port of v3 raster widget's renderMapNotes (Leaflet → MapLibre).
     * Each marker carries a popup with the note's tag, content preview, and
     * Edit / Open Notes / Remove buttons (same UX as v3).
     */
    function startMapNotesPolling(uniqueId, map, refreshSeconds) {
        const instance = window.AoTWidgetInstances[uniqueId];
        if (!instance) return;
        if (!instance.noteMarkers) instance.noteMarkers = new Map();

        function _t(key, fallback) {
            return (typeof window._ === 'function') ? window._(key) : (fallback || key);
        }

        function buildPopupHtml(note, noteId, tagName, content) {
            const safeTag = String(tagName || '').replace(/'/g, "\\'");
            const safeContent = String(content || '').replace(/'/g, "\\'");
            const tId = note.target_id || note.unique_id;
            const openAction = "window.dispatchEvent(new CustomEvent('open-notes', { detail: { targetId: '" + tId + "', targetType: 'map_location', name: '" + safeTag + "' } }))";
            const renameAction = "window.AoTMapApp['" + uniqueId + "'].updateMapNoteTags('" + noteId + "', document.getElementById('rename-input-" + noteId + "').value)";
            const deleteAction = "window.AoTMapApp['" + uniqueId + "'].deleteMapNote('" + noteId + "')";
            const toggleAction = "window.AoTMapApp['" + uniqueId + "'].toggleNoteEditMode('" + noteId + "')";
            const btnStyle = 'height:28px; border-radius:14px; font-size:1em; display:flex; align-items:center; justify-content:center; padding:0 16px; border:none; transition:all 0.2s; color:black; white-space:nowrap;';
            const primary  = btnStyle + ' background: var(--primary, #995aff);';
            const gray     = btnStyle + ' background:#adb5bd;';
            const secondary= btnStyle + ' background:#e9ecef;';
            return ''
                + '<div style="min-width:200px; padding:10px; font-family:\'Inter\', sans-serif;">'
                + '  <div style="font-size:1.1em; font-weight:600; color:#000; margin-bottom:12px; word-break:break-all;">' + safeTag + '</div>'
                + '  <div id="note-row2-view-' + noteId + '" style="display:flex; flex-direction:column; gap:10px;">'
                + '    <div style="display:flex; gap:8px; justify-content:flex-end;">'
                + '      <button class="btn" style="' + secondary + '" onclick="' + toggleAction + '">' + _t('edit', 'Edit') + '</button>'
                + '      <button class="btn" style="' + primary   + '" onclick="' + openAction   + '">' + _t('Open Notes', 'Open Notes') + '</button>'
                + '    </div>'
                + '    <div style="font-size:0.9em; color:#666; line-height:1.4; word-break:break-all; max-height:60px; overflow-y:auto; padding:4px 0;">'
                +        (safeContent || '<span style="color:#ccc;">' + _t('no_content', 'No content') + '</span>')
                + '    </div>'
                + '  </div>'
                + '  <div id="note-row2-edit-' + noteId + '" style="display:none; flex-direction:column; gap:8px;">'
                + '    <input type="text" id="rename-input-' + noteId + '" value="' + safeTag + '" class="form-control" style="height:30px; font-size:0.9em; padding:4px 8px; border:1px solid #ddd; border-radius:4px; width:100%;">'
                + '    <div style="display:flex; gap:8px; justify-content:flex-end;">'
                + '      <button class="btn" style="' + gray    + '" onclick="' + deleteAction + '">' + _t('Remove from Map', 'Remove from Map') + '</button>'
                + '      <button class="btn" style="' + primary + '" onclick="' + renameAction + '">' + _t('Save', 'Save') + '</button>'
                + '    </div>'
                + '  </div>'
                + '</div>';
        }

        function renderMapNotes() {
            return fetch('/notes/geo')
                .then(function(res) { return res.json(); })
                .then(function(notes) {
                    if (!Array.isArray(notes)) return;

                    // Track which note IDs are still on the server so we can
                    // remove markers for notes that were deleted/hidden.
                    const seen = new Set();

                    notes.forEach(function(note) {
                        if (note.gps_lat == null || note.gps_lng == null) return;
                        const lat = parseFloat(note.gps_lat);
                        const lng = parseFloat(note.gps_lng);
                        if (isNaN(lat) || isNaN(lng)) return;

                        const noteId = note.unique_id;
                        seen.add(noteId);

                        const uniqueTag = (note.tag_list || []).find(function(t) {
                            return t.name !== 'widget' && t.name !== 'map_hidden';
                        }) || { name: _t('New Note', 'New Note') };
                        const tagName = uniqueTag.name;
                        const content = note.note || '';
                        const html = buildPopupHtml(note, noteId, tagName, content);

                        if (instance.noteMarkers.has(noteId)) {
                            // Existing marker: refresh popup + position
                            const m = instance.noteMarkers.get(noteId);
                            m.setLngLat([lng, lat]);
                            const pop = m.getPopup();
                            if (pop) pop.setHTML(html);
                            return;
                        }

                        // Pin element (matches v3 divIcon styling)
                        const el = document.createElement('div');
                        el.className = 'aot-map-note-marker';
                        el.style.cssText = 'background:var(--gray-dark, #495057); border:2px solid #fff; border-radius:50%; width:24px; height:24px; display:flex; justify-content:center; align-items:center; box-shadow:0 2px 5px rgba(0,0,0,0.3); color:#fff; cursor:pointer;';
                        el.innerHTML = '<i class="fas fa-map-pin" style="font-size:12px;"></i>';

                        const popup = new maplibregl.Popup({ offset: 18, closeOnClick: false, maxWidth: '260px' })
                            .setHTML(html);
                        const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
                            .setLngLat([lng, lat])
                            .setPopup(popup)
                            .addTo(map);
                        instance.noteMarkers.set(noteId, marker);
                    });

                    // Remove markers for notes that disappeared from /notes/geo.
                    instance.noteMarkers.forEach(function(marker, id) {
                        if (!seen.has(id)) {
                            try { marker.remove(); } catch (e) {}
                            instance.noteMarkers.delete(id);
                        }
                    });
                })
                .catch(function(e) { console.error('[AoT Map] renderMapNotes:', e); });
        }

        // Expose helpers used by v3-style popup buttons (Open / Edit / Save / Remove).
        window.AoTMapApp = window.AoTMapApp || {};
        window.AoTMapApp[uniqueId] = window.AoTMapApp[uniqueId] || {};
        window.AoTMapApp[uniqueId].renderMapNotes = renderMapNotes;

        function _csrf() {
            return (window.AoTMapData && window.AoTMapData.getCsrfToken)
                ? window.AoTMapData.getCsrfToken()
                : (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
        }

        window.AoTMapApp[uniqueId].updateMapNoteTags = function(noteId, newTagName) {
            fetch('/notes/update/' + noteId, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrf() },
                body: JSON.stringify({ new_tag_name: newTagName })
            }).then(function(r) { return r.json(); }).then(function(d) {
                if (d && d.error) alert('Error: ' + d.error);
                else renderMapNotes();
            }).catch(function(e) { alert('Update failed: ' + e); });
        };

        window.AoTMapApp[uniqueId].deleteMapNote = function(noteId) {
            if (!confirm(_t('confirm_remove_pin', 'Remove pin from map?'))) return;
            fetch('/notes/toggle_map_visibility', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': _csrf() },
                body: JSON.stringify({ unique_id: noteId, visible: false })
            }).then(function(r) { return r.json(); }).then(function(d) {
                if (d && d.error) alert('Error: ' + d.error);
                else renderMapNotes();
            }).catch(function(e) { alert('Remove failed: ' + e); });
        };

        window.AoTMapApp[uniqueId].toggleNoteEditMode = function(noteId) {
            const v = document.getElementById('note-row2-view-' + noteId);
            const e = document.getElementById('note-row2-edit-' + noteId);
            if (v && e) {
                if (v.style.display === 'none') { v.style.display = 'flex'; e.style.display = 'none'; }
                else                            { v.style.display = 'none'; e.style.display = 'flex'; }
            }
        };

        // Refresh markers when the user creates/closes notes.
        window.addEventListener('notes-closed', renderMapNotes);

        // Initial fetch + poll at refreshSeconds interval (min 30s to avoid over-polling).
        const _noteIntervalMs = Math.max(30, refreshSeconds || 30) * 1000;
        renderMapNotes();
        instance.notePollTimer = setInterval(renderMapNotes, _noteIntervalMs);
    }

    /**
     * Build measurement list for the bottom panel from vars.measurements_map.
     */
    function buildPanelMeasurements(measurementsMap, devices) {
        const out = [];
        if (!measurementsMap || typeof measurementsMap !== 'object') return out;

        const devList = Array.isArray(devices) ? devices : [];
        Object.keys(measurementsMap).forEach(function(devId) {
            const measList = measurementsMap[devId];
            if (!Array.isArray(measList)) return;
            const devObj = devList.find(function(d) {
                return d.device_unique_id === devId || d.unique_id === devId;
            });
            const fallbackName = devObj ? (devObj.device_name || devObj.name) : null;

            measList.forEach(function(m) {
                out.push({
                    id: m.id || (devId + '_0'),
                    device_unique_id: m.device_unique_id || devId,
                    device_type: m.device_type,
                    device_name: m.device_name || fallbackName,
                    // meas_name has no channel prefix; fall back to name only if meas_name absent
                    name: m.meas_name || m.device_name || fallbackName || m.label || 'Measurement',
                    unit: m.unit || '',
                    value: (m.last_value !== undefined && m.last_value !== null && m.last_value !== '') ? m.last_value : '-'
                });
            });
        });

        out.sort(function(a, b) {
            const an = a.device_name || a.name || '';
            const bn = b.device_name || b.name || '';
            return an.localeCompare(bn, undefined, { numeric: true, sensitivity: 'base' });
        });
        return out;
    }

    /**
     * Fetch the latest value for each panel measurement via /last/ and update the panel.
     */
    function refreshMeasurementPanelValues(uniqueId) {
        const instance = window.AoTWidgetInstances[uniqueId];
        if (!instance || !instance.measurementPanel) return;
        const panel = instance.measurementPanel;
        const measurements = instance.panelMeasurements || [];

        measurements.forEach(function(m) {
            const devId = m.device_unique_id;
            const measId = m.id;
            const devType = m.device_type || 'input';
            if (!devId || !measId) return;

            // Resolve unit: aotMapUnits has proper display symbols (m/s, °C, bearing…)
            const resolvedUnit = (window.aotMapUnits && window.aotMapUnits[measId]) || m.unit || '';
            fetch('/last/' + encodeURIComponent(devId) + '/' + encodeURIComponent(devType) + '/' + encodeURIComponent(measId) + '/600')
                .then(function(res) {
                    if (!res.ok || res.status === 204) return null;
                    return res.json();
                })
                .then(function(data) {
                    if (data && Array.isArray(data) && data[1] !== null && data[1] !== undefined) {
                        panel.updateValue(measId, data[1], resolvedUnit);
                    }
                })
                .catch(function() {});
        });
    }

    /**
     * Add bottom-center measurement panel using AoTMapCustomControls.
     */
    function addMeasurementPanel(uniqueId, map, vars) {
        const LOG = '[AoT Map]';
        if (!window.AoTMapCustomControls || typeof window.AoTMapCustomControls.createMeasurementPanel !== 'function') {
            console.warn(LOG, 'measurement panel skipped: AoTMapCustomControls.createMeasurementPanel missing');
            return;
        }
        const innerVars = (vars && vars.vars) || {};
        const panelMeasurements = buildPanelMeasurements(innerVars.measurements_map, vars.devices);
        if (!panelMeasurements.length) {
            console.warn(LOG, 'measurement panel skipped: no measurements selected in widget config (Measurement Panel section).');
            return;
        }
        const handle = window.AoTMapCustomControls.createMeasurementPanel(map, {
            measurements: panelMeasurements,
            updateInterval: innerVars.input_update_interval || 300,
            maxAge: innerVars.max_measure_age || 300
        });
        const instance = window.AoTWidgetInstances[uniqueId];
        if (instance) {
            instance.measurementPanel = handle;
            instance.panelMeasurements = panelMeasurements;

            // Fetch live values immediately (backend initial value may be stale)
            setTimeout(function() { refreshMeasurementPanelValues(uniqueId); }, 200);

            // Periodic refresh for measurement values
            const refreshMs = Math.max(10, (innerVars.input_update_interval || 60)) * 1000;
            if (instance.panelRefreshTimer) clearInterval(instance.panelRefreshTimer);
            instance.panelRefreshTimer = setInterval(function() {
                refreshMeasurementPanelValues(uniqueId);
            }, refreshMs);
        }
    }

    /**
     * Build legend HTML for a single layer's legend data into a wrapper div.
     */
    function _buildLegendItem(layer) {
        const wrapper = document.createElement('div');
        wrapper.className = 'aot-legend-item-wrapper';
        wrapper.style.cssText = 'margin-bottom:6px;';
        // Layer name intentionally omitted — legend content is self-describing
        const legendData = layer.legend;
        // Resolve the layer's API key (mirrors aot-map-loader.js approach)
        const layerApiKey = layer.api_key
            || (layer.options && (layer.options.apiKey || layer.options.api_key))
            || '';

        if (legendData && legendData.type === 'html' && legendData.content) {
            const body = document.createElement('div');
            body.innerHTML = legendData.content;
            // Inject API key so _fetchLegendCenterValues can replace {apiKey} in URLs
            if (layerApiKey) {
                body.querySelectorAll('.aot-legend-value-box').forEach(function(box) {
                    box.dataset.apiKey = layerApiKey;
                });
            }
            wrapper.appendChild(body);
        } else if (legendData && legendData.type === 'img' && legendData.url) {
            const img = document.createElement('img');
            img.src = legendData.url;
            img.alt = 'Legend';
            img.style.cssText = 'max-width:100%;display:block;';
            wrapper.appendChild(img);
        } else if (legendData && Array.isArray(legendData.items)) {
            legendData.items.forEach(function(item) {
                const row = document.createElement('div');
                row.style.cssText = 'display:flex;align-items:center;gap:6px;line-height:1.4;';
                const swatch = document.createElement('span');
                swatch.style.cssText = 'display:inline-block;width:14px;height:14px;border:1px solid #ccc;background:' + (item.color || '#ccc') + ';';
                const lbl = document.createElement('span');
                lbl.textContent = item.label || '';
                row.appendChild(swatch);
                row.appendChild(lbl);
                wrapper.appendChild(row);
            });
        } else if (typeof legendData === 'string') {
            const body = document.createElement('div');
            body.innerHTML = legendData;
            wrapper.appendChild(body);
        }

        // Wrap trailing (unit) in .aot-legend-title for CSS-based hiding
        wrapper.querySelectorAll('.aot-legend-title').forEach(function(el) {
            const m = el.textContent.match(/^(.*?)\s*(\([^)]+\))\s*$/);
            if (m) {
                el.innerHTML = m[1] + '<span class="aot-legend-title-unit"> ' + m[2] + '</span>';
            }
        });

        return wrapper;
    }

    /**
     * Fetch center-point values for .aot-legend-value-box elements in legendEl.
     * Mirrors the dynamic updater from aot-map-loader.js.
     */
    function _fetchLegendCenterValues(legendEl, map) {
        if (!legendEl || legendEl.style.display === 'none') return;
        const boxes = legendEl.querySelectorAll('.aot-legend-value-box');
        if (!boxes.length) return;

        const center = map.getCenter();

        boxes.forEach(function(box) {
            const paramPath = box.getAttribute('data-api-param');
            const customUrl  = box.getAttribute('data-api-url');
            const dFactor    = box.getAttribute('data-d-factor');
            const valueText  = box.querySelector('.aot-legend-value-text');
            if (!valueText || !paramPath || !customUrl) return;

            const apiKey = box.dataset.apiKey || '';
            // Skip if URL still needs an apiKey that wasn't provided
            if (!apiKey && /\{apiKey\}|appid=&|appid=$/.test(customUrl)) {
                valueText.innerText = '-';
                return;
            }

            // Round to 3 decimals (~111m) to maximise cache hits on small map pans.
            // ISRIC SoilGrids native resolution is ~250m, so this loses no useful precision.
            const rLat = Math.round(center.lat * 1000) / 1000;
            const rLng = Math.round(center.lng * 1000) / 1000;
            const url = customUrl
                .replace(/\{lat\}/g,    rLat)
                .replace(/\{lon\}/g,    rLng)
                .replace(/\{lng\}/g,    rLng)
                .replace(/\{apiKey\}/g, apiKey);

            valueText.innerText = '…';

            const req = (window.AoTAPIManager && typeof window.AoTAPIManager.request === 'function')
                ? window.AoTAPIManager.request(url)
                : fetch(url).then(function(r) { return r.json(); });

            req.then(function(data) {
                    const keys = paramPath.split('.');
                    let val = data;
                    for (let k of keys) {
                        if (val != null && k in Object(val)) {
                            val = val[k];
                        } else if (Array.isArray(val) && !isNaN(parseInt(k))) {
                            val = val[parseInt(k)];
                        } else { val = undefined; break; }
                    }
                    if (val !== undefined && val !== null) {
                        let num = parseFloat(val);
                        if (dFactor) num = num / parseFloat(dFactor);
                        valueText.innerText = isNaN(num) ? val : (Math.round(num * 100) / 100);
                    } else {
                        valueText.innerText = '-';
                    }
                })
                .catch(function() { valueText.innerText = '-'; });
        });
    }

    /**
     * Measurement panel is always bottom-center regardless of legend visibility.
     * Legend is positioned above the panel via CSS (bottom: 120px desktop / 100px mobile).
     */
    function _syncLegendPanelLayout(instance) {
        const panel = instance.measurementPanel && instance.measurementPanel.panel;
        if (!panel) return;
        panel.classList.remove('left-aligned');
        panel.style.maxWidth = '';
    }

    /**
     * Overlay legend panel in the bottom-right corner.
     * Uses vars.geoConfig.layers as the full layer list (which carries legend
     * metadata). Exposes instance.refreshLegend(activeLayerNames) so the layer
     * panel can call it when overlay selection changes.
     */
    function addLegendOverlay(uniqueId, map, vars) {
        const allLayers = (vars && vars.geoConfig && vars.geoConfig.layers)
            || (window.AOT_GEO_CONFIG && window.AOT_GEO_CONFIG.layers)
            || (vars && vars.layers)
            || [];

        const mapCanvas    = map.getContainer();                                               // maplibregl canvas wrapper
        const mapId        = vars.mapId || ('aot-map-' + uniqueId);
        const mapContainer = document.getElementById(mapId) || mapCanvas.parentElement || mapCanvas;  // .aot-map-container
        mapContainer.style.position = mapContainer.style.position || 'relative';

        const _legendVars = (vars && vars.vars) || {};
        const _dataOnlyMode = _legendVars.overlay_data_only === true || _legendVars.overlay_data_only === 'true';

        const legendEl = document.createElement('div');
        legendEl.className = 'aot-legend-container aot-vector-legend';

        // 레전드는 항상 mapContainer 내부 우측 하단(정상 위치)에 배치
        // _dataOnlyMode: 오버레이 타일만 숨김(addLayerPanel 처리), 베이스 지도·레전드는 정상 표시
        legendEl.style.cssText = 'position:absolute; right:10px; max-width:220px; overflow-y:auto; font-size:11px; color:#333; display:none; box-sizing:border-box;';
        mapContainer.appendChild(legendEl);

        const instance = window.AoTWidgetInstances[uniqueId];

        // 측정값 패널이 없으면 레전드를 패널 하단 y 좌표만큼 아래로 내림 (bottom: 32px)
        if (!instance || !instance.measurementPanel) {
            legendEl.classList.add('aot-legend-no-panel');
        }

        function refreshLegend(activeLayerNames) {
            legendEl.innerHTML = '';
            const names = Array.isArray(activeLayerNames) ? activeLayerNames
                : (typeof activeLayerNames === 'string' ? activeLayerNames.split(',').map(function(s) { return s.trim(); }) : []);

            const candidates = allLayers.filter(function(l) {
                if (!l || !l.legend) return false;
                if (l.enabled === false) return false;
                if (!names.length) return false;  // no active overlays → show no legend
                return names.indexOf(l.name)               !== -1
                    || names.indexOf(l.id)                 !== -1
                    || names.indexOf(String(l.unique_id || '')) !== -1;
            });

            if (candidates.length) {
                candidates.forEach(function(layer) { legendEl.appendChild(_buildLegendItem(layer)); });
                legendEl.style.display = 'block';
                setTimeout(function() { _fetchLegendCenterValues(legendEl, map); }, 50);
            } else {
                legendEl.style.display = 'none';
            }

            // Reposition measurement panel after legend visibility change
            if (instance) { _syncLegendPanelLayout(instance); }
        }

        // Re-fetch center values on map move (debounced)
        let _moveDebounce;
        map.on('moveend', function() {
            clearTimeout(_moveDebounce);
            _moveDebounce = setTimeout(function() {
                _fetchLegendCenterValues(legendEl, map);
            }, 500);
        });

        // Get initial active overlays from widget custom_options
        const innerVars = (vars && vars.vars) || {};
        const initActive = _resolveActiveOverlayNames(innerVars.active_layers);

        refreshLegend(initActive);

        if (instance) {
            instance.legendEl      = legendEl;
            instance.refreshLegend = refreshLegend;
        }
    }

    /**
     * Apply global panel transparency from geo design theme settings.
     * Reads vars.theme.panel_opacity (0-100, default 90) and applies
     * rgba background to all panels created by this widget instance.
     */
    function applyPanelOpacity(uniqueId, vars) {
        const theme = (vars && vars.theme) || {};
        const rawOpacity = theme.panel_opacity !== undefined ? theme.panel_opacity
            : ((window.AOT_GEO_CONFIG && window.AOT_GEO_CONFIG.theme_config && window.AOT_GEO_CONFIG.theme_config.panel_opacity) || 90);
        const opacity = Math.min(1, Math.max(0, parseInt(rawOpacity) / 100));
        if (isNaN(opacity)) return;

        const bg = 'rgba(255,255,255,' + opacity + ')';
        const instance = window.AoTWidgetInstances[uniqueId];
        if (!instance) return;

        // Set CSS variable on map container — cascades to both .aot-measurement-panel
        // and .aot-legend-container (bypasses !important on background-color).
        const mapContainer = instance.map ? instance.map.getContainer() : null;
        if (mapContainer) {
            mapContainer.style.setProperty('--panel-bg-rgba', bg);
        }
    }

    /**
     * Add device markers to map
     */
    function addDeviceMarkers(uniqueId, map, devices, theme, vars) {
        const instance = window.AoTWidgetInstances[uniqueId];
        if (!instance) return;

        const wOpts = (vars && vars.vars) || {};
        const showDeviceLabels = wOpts.show_device_labels === true || wOpts.show_device_labels === 'true';
        const globalLabelSize = parseFloat(wOpts.global_label_size) || 1.0;
        const labelCollision   = wOpts.enable_label_collision !== false && wOpts.enable_label_collision !== 'false';
        const _rawSpacingD     = parseInt(wOpts.label_spacing);
        const labelSpacing     = (!isNaN(_rawSpacingD) && wOpts.label_spacing !== '' && wOpts.label_spacing !== null && wOpts.label_spacing !== undefined) ? _rawSpacingD : 0;

        // Build allowed ID set for strict filtering (mirrors v3 renderDevices)
        const allowedIds = new Set();
        const fetchIds = wOpts.map_device_ids || wOpts.device_ids;
        if (fetchIds && wOpts.include_all_devices !== true) {
            String(fetchIds).split(',').forEach(function(id) {
                const t = id.trim();
                if (t) {
                    allowedIds.add(t);
                    if (t.includes('::')) allowedIds.add(t.split('::')[0]);
                }
            });
        }
        const isStrictFiltering = (allowedIds.size > 0 && wOpts.include_all_devices !== true);

        // Clear existing device markers and cluster badges before re-rendering
        instance.markers.forEach(function(m) { m.remove(); });
        instance.markers.clear();

        if (instance.deviceClusterMarkers) {
            instance.deviceClusterMarkers.forEach(function(m) { try { m.remove(); } catch(e) {} });
        }
        instance.deviceClusterMarkers = [];
        instance.deviceLabelMarkers = [];

        if (instance._deviceCollisionHandler) {
            map.off('moveend', instance._deviceCollisionHandler);
            map.off('zoomend', instance._deviceCollisionHandler);
            instance._deviceCollisionHandler = null;
        }

        // Build deviceTypeMap: baseUUID → device_type ('input'|'output'|'function')
        // Used by _applyTypeHide to also cover geoDeviceLabelMarkers
        if (!instance._deviceTypeMap) instance._deviceTypeMap = {};
        devices.forEach(function(dev) {
            const baseId = String(dev.device_id || dev.device_unique_id ||
                (dev.unique_id ? dev.unique_id.split('::')[0] : (dev.id || '').split('::')[0]));
            if (baseId) instance._deviceTypeMap[baseId] = dev.device_type || dev.type || '';
        });

        // Apply persisted hide state to geo-device labels now that _deviceTypeMap is built
        // (loadGeoDesignLabels runs before this, so it can't do this itself)
        var _hiddenTypes = instance._hiddenTypes || {};
        (instance.geoDeviceLabelMarkers || []).forEach(function(marker) {
            if (!marker || typeof marker.getElement !== 'function') return;
            var el = marker.getElement();
            if (!el) return;
            var parentId = el.dataset.parentId || '';
            var devType = instance._deviceTypeMap[parentId];
            if (!devType) return;
            el.classList.toggle('aot-type-hidden', !!_hiddenTypes[devType]);
        });

        devices.forEach(function(dev) {
            const devLat = dev.lat || dev.latitude;
            const devLng = dev.lng || dev.longitude;
            if (!devLat || !devLng) return;

            // Strict device filtering
            if (isStrictFiltering) {
                const devId = String(dev.id || dev.unique_id || '');
                const baseId = devId.split('::')[0];
                if (!allowedIds.has(devId) && !allowedIds.has(baseId)) return;
            }

            // [3-way Actuator] Initial render: always off-style. Motion (detected from
            // position changes between polls or commandActuator calls) flips it to ON.
            const isON = (dev.control_kind === 'value_3way')
                ? false
                : (dev.status === 'active' || dev.status === 'on' ||
                   dev.is_activated === true || dev.is_activated === 'true');

            const devType2 = dev.device_type || dev.type || '';
            const userColor = getUnifiedDeviceColor(devType2, dev, theme);

            const popup = createDevicePopup(uniqueId, dev, wOpts);

            if (showDeviceLabels) {
                // Pill label style (show_device_labels = true)
                const displayName = (dev.device_name || dev.name ||
                    (dev.unique_id || dev.id || '').toString().split('::')[0] || '').toString().trim();
                if (!displayName) return;

                const targetMap = wOpts.all_measurements_map || wOpts.measurements_map || {};
                const devIdKey = dev.device_id || dev.device_unique_id ||
                                 (dev.unique_id ? dev.unique_id.split('::')[0] : (dev.id || '').split('::')[0]);
                const devMeas = targetMap[devIdKey] || [];
                let firstVal = '';
                let unit = '';
                if (devMeas.length > 0) {
                    const m = devMeas.find(function(x) { return parseInt(x.channel) === parseInt(dev.channel_id); }) || devMeas[0];
                    if (m && m.last_value !== undefined && m.last_value !== null && m.last_value !== '') {
                        firstVal = m.last_value;
                        unit = (window.aotMapUnits && window.aotMapUnits[m.id]) ? window.aotMapUnits[m.id] : (m.unit || '');
                        if (unit === 'bearing') unit = '';
                    }
                }
                // [3-way Actuator] Override label value with current position % (and direction arrow)
                if (dev.control_kind === 'value_3way') {
                    const p = (typeof dev.position_pct === 'number') ? dev.position_pct : 0;
                    const dir = dev.motion_dir;
                    const arrow = (dir === 'open') ? '▲ ' : (dir === 'close') ? '▼ ' : '';
                    firstVal = arrow + Math.round(p);
                    unit = '%';
                }

                let baseSize = globalLabelSize;
                if (dev.font_size) {
                    const scale = parseInt(dev.font_size);
                    if (!isNaN(scale)) baseSize = baseSize * (1 + ((scale - 1) * 0.2));
                }

                const showValue = firstVal !== '' && firstVal !== undefined && firstVal !== null;
                const shadowColorOff = hexToRgba(userColor, 0.3);
                const shadowColorOn  = hexToRgba(userColor, 0.6);
                const pillStyle = isON
                    ? 'background-color:' + userColor + ';color:#fff;border:2px solid #fff !important;box-shadow:0 4px 12px ' + shadowColorOn + ' !important;'
                    : 'background-color:#fff;color:' + userColor + ';border:2px solid ' + userColor + ' !important;box-shadow:0 2px 5px ' + shadowColorOff + ' !important;';

                const labelHtml =
                    '<div class="aot-label-content marker-pill' + (isON ? ' device-on' : '') + '" ' +
                    'style="' + pillStyle + 'font-size:' + baseSize + 'em;padding:4px 8px;border-radius:12px;' +
                    'width:max-content;white-space:nowrap;margin:0;' + (dev.label_style || '') + '">' +
                    '<div style="line-height:1.2">' +
                    '<span class="dev-name">' + displayName + '</span>' +
                    (showValue
                        ? '<span class="dev-val-group" style="display:inline;margin-left:4px">' +
                          '<span class="dev-value">' + firstVal + '</span>' +
                          '<span class="dev-unit" style="font-size:0.5em;margin-left:2px">' + unit + '</span>' +
                          '</span>'
                        : '') +
                    '</div></div>';

                const el = document.createElement('div');
                el.className = 'aot-device-label-wrapper';
                el.dataset.labelName  = displayName;
                el.dataset.labelColor = userColor;
                el.dataset.deviceType = devType2;
                el.innerHTML = labelHtml;
                // Apply persisted hide state immediately on creation
                if (instance._hiddenTypes && instance._hiddenTypes[devType2]) {
                    el.classList.add('aot-type-hidden');
                }

                const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
                    .setLngLat([parseFloat(devLng), parseFloat(devLat)])
                    .addTo(map);

                el.addEventListener('click', function(e) {
                    e.stopPropagation();
                    if (popup.isOpen()) { popup.remove(); }
                    else { popup.setLngLat([parseFloat(devLng), parseFloat(devLat)]).addTo(map); }
                });

                instance.markers.set(dev.unique_id || dev.id, marker);
                instance.markers.set('__popup__' + (dev.unique_id || dev.id), { remove: function() { popup.remove(); } });
                instance.deviceLabelMarkers.push(marker);

            } else {
                // Dot style (show_device_labels = false, default)
                const el = document.createElement('div');
                el.className = 'map-marker-dot' + (isON ? ' device-on' : '');
                el.dataset.deviceType = devType2;
                el.style.cssText =
                    'background-color:' + (isON ? userColor : '#fff') + ';' +
                    'border:2px solid ' + userColor + ';' +
                    'opacity:' + (dev.opacity !== undefined ? dev.opacity : 1) + ';' +
                    'cursor:pointer;';
                // Apply persisted hide state immediately on creation
                if (instance._hiddenTypes && instance._hiddenTypes[devType2]) {
                    el.classList.add('aot-type-hidden');
                }

                const marker = new maplibregl.Marker({ element: el, anchor: 'center' })
                    .setLngLat([parseFloat(devLng), parseFloat(devLat)])
                    .addTo(map);

                el.addEventListener('click', function(e) {
                    e.stopPropagation();
                    if (popup.isOpen()) { popup.remove(); }
                    else { popup.setLngLat([parseFloat(devLng), parseFloat(devLat)]).addTo(map); }
                });

                instance.markers.set(dev.unique_id || dev.id, marker);
                instance.markers.set('__popup__' + (dev.unique_id || dev.id), { remove: function() { popup.remove(); } });
            }
        });

        // Device label collision — joins unified handler (all groups run together in priority order)
        if (showDeviceLabels && labelCollision && instance.deviceLabelMarkers.length > 0) {
            instance._labelSpacing = labelSpacing;
            _updateUnifiedCollisionHandler(instance, map, labelSpacing);
            map.once('idle', function() {
                _runUnifiedLabelCollision(instance, map, labelSpacing);
            });
        }

        // Sync device shape opacity with initial on/off state
        _updateDeviceShapeOpacity(instance, devices);
    }

    function hexToRgba(hex, alpha) {
        if (!hex) return 'rgba(0,0,0,' + alpha + ')';
        const r = parseInt(hex.slice(1, 3), 16) || 0;
        const g = parseInt(hex.slice(3, 5), 16) || 0;
        const b = parseInt(hex.slice(5, 7), 16) || 0;
        return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
    }

    // Color priority: Theme (type-specific → generic) → device label_color → device color → fallback
    function getUnifiedDeviceColor(type, dev, theme) {
        if (theme) {
            if (theme[type + '-color']) return theme[type + '-color'];
            if (theme[type]) return theme[type];
            if (theme['aot_device-color']) return theme['aot_device-color'];
            if (theme['aot_device']) return theme['aot_device'];
            if (theme.device) return theme.device;
        }
        if (dev && dev.label_color) return dev.label_color;
        var bc = dev && (dev.color || dev.marker_color);
        if (bc && bc.trim()) return bc.trim();
        return (theme && theme.primary) || '#995aff';
    }

    /**
     * Create device popup (MapLibre) — exact port of v3 bindDevicePopup.
     * Returns { popup, onOpen } where onOpen must be called after marker.setPopup(popup).addTo(map).
     */
    function createDevicePopup(uniqueId, dev, wOpts) {
        const devType = dev.device_type || dev.type || '';
        const isInput = devType === 'input';
        const isOutput = devType === 'output' || devType === 'function';
        const isON = dev.status === 'active' || dev.status === 'on' ||
                     dev.is_activated === true || dev.is_activated === 'true';

        const displayName = dev.device_name || dev.name || dev.unique_id || 'Device';
        const uniqueKey = dev.device_id || dev.device_unique_id ||
                          (dev.unique_id ? dev.unique_id.split('::')[0] : (dev.id || '').split('::')[0]);
        const channel = (dev.channel_id && dev.channel_id !== 'undefined') ? dev.channel_id : 0;
        const notePreviewId = 'note-prev-' + uniqueKey + '-' + (dev.id || '');

        const targetMap = (wOpts && (wOpts.all_measurements_map || wOpts.measurements_map)) || {};
        const devMeas = targetMap[uniqueKey] || [];

        // ----- Notes section (shared) -----
        const noteSectionHtml =
            '<hr style="margin:8px 0;border:0;border-top:1px solid #eee">' +
            '<button class="btn btn-primary" style="border-radius:14px;height:28px;width:100%;font-size:0.9em;display:flex;align-items:center;justify-content:center;padding:0;" ' +
            'onclick="window.dispatchEvent(new CustomEvent(\'open-notes\',{detail:{targetId:\'' + uniqueKey + '\',targetType:\'device\',name:\'' + displayName.replace(/'/g, "\\'") + '\'}}))"> ' +
            '<i class="fas fa-clipboard mr-2"></i> ' + (window._ ? window._('Create Note') : 'Create Note') + '</button>' +
            '<div id="' + notePreviewId + '" style="font-size:0.9em;color:#666;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;min-height:1.2em;line-height:1.4;margin-top:6px;">' +
            '<span style="color:#ccc;font-style:italic">...</span></div>';

        // Hoist devId/toggleId to function scope so onOpen closure can access them
        const devId = dev.id || dev.unique_id || '';
        const toggleId = 'toggle-' + devId;

        let html = '';

        if (isInput) {
            // ----- Input popup: name + measurements -----
            let bodyHtml = '';
            if (devMeas.length > 0) {
                devMeas.forEach(function(m) {
                    const mName = m.meas_name || m.name || '';
                    const mVal = (m.last_value !== undefined && m.last_value !== null && m.last_value !== '') ? m.last_value : 'N/A';
                    let unitStr = (window.aotMapUnits && window.aotMapUnits[m.id]) ? window.aotMapUnits[m.id] : (m.unit || '');
                    if (unitStr === 'bearing') unitStr = '';
                    bodyHtml +=
                        '<div class="aot-popup-row" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;border-bottom:1px dotted #eee;padding-bottom:4px;">' +
                        '<span style="font-weight:normal;font-size:1.2em;color:#333;flex:1;padding-right:4px;line-height:1.2;min-width:0;word-break:break-word;">' + mName + '</span>' +
                        '<span style="text-align:right;white-space:nowrap;flex:0 0 auto;">' +
                        '<span id="popup-val-' + (dev.id || '') + '-' + (m.id || '') + '" style="font-weight:bold;font-size:1.2em;color:#000">' + mVal + '</span>' +
                        (unitStr ? '<span class="aot-popup-unit" style="font-size:0.9em;margin-left:2px;color:#555">' + unitStr + '</span>' : '') +
                        '</span></div>';
                });
            } else {
                bodyHtml = '<div class="text-muted">' + (window._ ? window._('No Measurements') : 'No Measurements') + '</div>';
            }
            html = '<div><div class="aot-popup-title">' + displayName + '</div>' +
                   '<hr style="margin:8px 0">' + bodyHtml + noteSectionHtml + '</div>';

        } else if (dev.control_kind === 'value_3way') {
            // ----- 3-way Actuator popup: Open/Stop/Close + slider -----
            const posInit = (typeof dev.position_pct === 'number') ? dev.position_pct : 0;
            const posRounded = Math.round(posInit);
            const posDispId = 'pos-disp-' + devId;
            const sliderId = 'pos-slider-' + devId;
            const cmd = function(action, valueExpr) {
                return "window.AoTMapLoader.commandActuator('" + devId + "','" + action + "'," + valueExpr + ",'" + channel + "','" + uniqueId + "')";
            };
            const headerHtml3 =
                '<div class="aot-3way-header">' +
                '<div class="aot-popup-title">' + displayName + '</div>' +
                '<div id="' + posDispId + '" class="aot-3way-position">' + posRounded + '%</div></div>';
            const buttonsHtml =
                '<div class="aot-3way-buttons">' +
                '<input type="button" value="' + (window._ ? window._('Close') : 'Close') + '" class="form-control btn aot-btn-on aot-entry-btn-base aot-paired-btn" onclick="' + cmd('close', '0') + '">' +
                '<input type="button" value="' + (window._ ? window._('Stop') : 'Stop') + '" class="form-control btn aot-btn-off aot-entry-btn-base aot-paired-btn" onclick="' + cmd('stop', 'null') + '">' +
                '<input type="button" value="' + (window._ ? window._('Open') : 'Open') + '" class="form-control btn aot-btn-on aot-entry-btn-base aot-paired-btn" onclick="' + cmd('open', '100') + '"></div>';
            const sliderHtml =
                '<div class="aot-3way-slider-wrap"><input type="range" id="' + sliderId + '" class="aot-3way-slider" min="0" max="100" step="1" value="' + posRounded + '" ' +
                'style="--aot-3way-fill: ' + posRounded + '%;" ' +
                'oninput="this.style.setProperty(\'--aot-3way-fill\', this.value + \'%\'); document.getElementById(\'' + posDispId + '\').innerText = this.value + \'%\'" ' +
                'onchange="' + cmd('goto', 'parseFloat(this.value)') + '"></div>';
            // [3-way] Only Last Work Time; Current Work Time has no meaningful value at rest.
            const infoHtml3 =
                '<div class="aot-3way-info">' +
                '<div class="aot-3way-info-row">' +
                '<span class="aot-3way-info-label">' + (window._ ? window._('Last Work Time') : 'Last Work Time') + '</span>' +
                '<span id="last-dur-' + devId + '" class="aot-3way-info-value">00:00:00</span></div></div>';
            html = '<div class="aot-3way-popup" style="padding-top:15px">' + headerHtml3 + buttonsHtml + sliderHtml + infoHtml3 + noteSectionHtml + '</div>';

        } else {
            // ----- Output / Function popup: name + toggle + timer -----
            const durId = 'dur-' + devId;
            const canControl = isOutput;

            const btnHtml = '<label class="btn-toggle" style="margin-bottom:0">' +
                '<input type="checkbox" id="' + toggleId + '" class="btn-toggle-input" ' + (isON ? 'checked' : '') +
                (canControl ? '' : ' disabled') +
                ' onchange="(function(cb,ev){' +
                    'if(ev)ev.stopPropagation();' +
                    'var inst=window.AoTWidgetInstances&&window.AoTWidgetInstances[\'' + uniqueId + '\'];' +
                    'if(inst&&inst.markers){var mk=inst.markers.get(\'' + devId + '\');' +
                    'if(mk){mk._pendingToggle=Date.now();mk._isActive=cb.checked;}}' +
                    'if(window.AoTMapLoader&&window.AoTMapLoader.toggleDevice){' +
                    'window.AoTMapLoader.toggleDevice(\'' + devId + '\',cb.checked,\'' + channel + '\',\'' + devType + '\');}' +
                    'else{' +
                    'var bid=\'' + devId + '\'.split(\'::\')[0];' +
                    'if(\'' + devType + '\'===\'function\'){' +
                    'var fd=new FormData();fd.append(\'function_id\',bid);fd.append(cb.checked?\'function_activate\':\'function_deactivate\',\'True\');' +
                    'fetch(\'/function_submit\',{method:\'POST\',body:fd}).catch(function(){});}' +
                    'else{fetch(\'/api/outputs/\'+bid,{method:\'POST\',' +
                    'headers:{\'Content-Type\':\'application/vnd.aot.v1+json\',\'Accept\':\'application/vnd.aot.v1+json\'},' +
                    'body:JSON.stringify({state:cb.checked,channel:\'' + channel + '\'})}).catch(function(){});}}' +
                '})(this,event)">' +
                '<span class="btn-toggle-slider"><span class="btn-toggle-thumb"></span></span></label>';

            const headerHtml =
                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;gap:10px;">' +
                '<div class="aot-popup-title" style="font-size:1.4em;font-weight:bold;margin:0;line-height:1.2;word-break:break-all;">' + displayName + '</div>' +
                '<div style="display:flex;align-items:center;flex:0 0 auto">' + btnHtml + '</div></div>';

            const infoHtml =
                '<div style="border-top:1px solid #eee;padding-top:8px;">' +
                '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">' +
                '<span style="font-weight:bold;color:#555">' + (window._ ? window._('Current Work Time') : 'Current Work Time') + '</span>' +
                '<span id="' + durId + '" class="aot-timer-display" style="font-family:monospace;font-size:1.1em;font-weight:bold">00:00:00</span></div>' +
                '<div style="display:flex;justify-content:space-between;align-items:center;">' +
                '<span style="font-weight:bold;color:#555">' + (window._ ? window._('Last Work Time') : 'Last Work Time') + '</span>' +
                '<span id="last-dur-' + devId + '" style="font-family:monospace;font-size:1.1em;color:#777">00:00:00</span></div></div>';

            html = '<div style="min-width:180px;padding-top:15px">' + headerHtml + infoHtml + noteSectionHtml + '</div>';
        }

        const popupMaxW = (dev.control_kind === 'value_3way') ? '200px' : '260px';
        const popup = new maplibregl.Popup({ offset: 12, maxWidth: popupMaxW, className: 'aot-map-popup' }).setHTML(html);

        // ----- onOpen: fetch fresh values + notes -----
        function onOpen() {
            // Fetch last note
            var noteEl = document.getElementById(notePreviewId);
            if (noteEl) {
                fetch('/notes/target/' + uniqueKey)
                    .then(function(r) { return r.json(); })
                    .then(function(notes) {
                        if (!noteEl) return;
                        if (notes && notes.length > 0) {
                            noteEl.innerText = notes[0].note;
                            noteEl.style.fontStyle = 'normal';
                        } else {
                            noteEl.innerHTML = '<span style="color:#ccc;font-style:italic">' + (window._ ? window._('No Notes') : 'No Notes') + '</span>';
                        }
                    }).catch(function() {});
            }

            if (isInput && devMeas.length > 0) {
                // Fetch fresh measurement values
                devMeas.forEach(function(m) {
                    var url = '/last/' + uniqueKey + '/input/' + m.id + '/300';
                    var valEl = document.getElementById('popup-val-' + (dev.id || '') + '-' + (m.id || ''));
                    if (!valEl) return;
                    fetch(url)
                        .then(function(r) { return r.status === 200 ? r.json() : null; })
                        .then(function(data) {
                            if (!data) return;
                            var val = null;
                            if (Array.isArray(data) && data.length >= 2) val = data[1];
                            else if (data && data.value !== undefined) val = data.value;
                            if (val !== null && val !== undefined) {
                                if (typeof val === 'number' && !Number.isInteger(val)) val = parseFloat(val.toFixed(2));
                                valEl.innerText = val;
                            }
                        }).catch(function() {});
                });
            }

            if (isOutput) {
                var baseDevId = (dev.device_unique_id || dev.id || '').split('::')[0];
                var durEl = document.getElementById('dur-' + (dev.id || dev.unique_id || ''));


                // Async fetch: live state + start epoch, then register stopwatch
                Promise.all([
                    fetch('/outputstate_unique_id/' + baseDevId + '/' + channel)
                        .then(function(r) { return r.ok ? r.json() : null; }).catch(function() { return null; }),
                    fetch('/output_started_at_public/' + baseDevId + '/' + channel)
                        .then(function(r) { return r.ok ? r.json() : null; }).catch(function() { return null; })
                ]).then(function(results) {
                    var state = results[0];
                    var startData = results[1];
                    var liveON = (state !== null && state !== undefined)
                        ? (state === 'on' || (typeof state === 'number' && state > 0))
                        : isON;

                    // Prefer started_at_epoch; fall back to server-computed elapsed_sec
                    var startEpoch = null;
                    if (startData) {
                        if (startData.started_at_epoch) {
                            startEpoch = startData.started_at_epoch;
                        } else if (startData.elapsed_sec > 0 && startData.server_now_epoch) {
                            // Reconstruct start epoch using server clock to avoid client-clock skew
                            startEpoch = startData.server_now_epoch - startData.elapsed_sec;
                        }
                    }

                    var cb = document.getElementById(toggleId);
                    if (cb) cb.checked = liveON;
                    if (durEl && window.AoTStopwatchManager) {
                        window.AoTStopwatchManager.register(
                            baseDevId, channel, liveON, liveON ? startEpoch : null, durEl, 7000, false
                        );
                    }
                });

                // Last Work Time (separate — no dependency on live state)
                setTimeout(function() {
                    var lastDurEl = document.getElementById('last-dur-' + (dev.id || dev.unique_id || ''));
                    if (lastDurEl) {
                        fetch('/output_last_duration_public/' + baseDevId + '/' + channel)
                            .then(function(r) { return r.json(); })
                            .then(function(d) {
                                if (d && d.last_duration_sec !== undefined && d.last_duration_sec !== null && lastDurEl) {
                                    var s = parseInt(d.last_duration_sec, 10);
                                    if (isNaN(s)) return;
                                    var h = Math.floor(s / 3600).toString().padStart(2, '0');
                                    var mm = Math.floor((s % 3600) / 60).toString().padStart(2, '0');
                                    var ss = (s % 60).toString().padStart(2, '0');
                                    lastDurEl.innerText = h + ':' + mm + ':' + ss;
                                }
                            }).catch(function() {});
                    }
                }, 50);
            }
        }

        popup.on('open', onOpen);
        return popup;
    }

    /**
     * Fetch devices from /api/geo/devices and render markers.
     * Used when async_devices=true (default).
     */
    async function fetchAndRenderDevices(uniqueId, map, vars) {
        const instance = window.AoTWidgetInstances[uniqueId];
        if (!instance) return;

        const wOpts = (vars && vars.vars) || {};
        const mapUuid = wOpts.selected_map_uuid || wOpts.map_uuid || vars.contentMapUuid || '';
        const deviceIds = wOpts.map_device_ids || wOpts.device_ids || '';
        const includeAll = wOpts.include_all_devices === true || wOpts.include_all_devices === 'true';

        const params = new URLSearchParams();
        if (mapUuid) params.set('map_uuid', mapUuid);
        if (deviceIds) params.set('device_ids', deviceIds);
        params.set('include_all', String(includeAll));

        try {
            const response = await fetch('/api/geo/devices?' + params.toString());
            if (!response.ok) {
                console.warn('[AoT Map] fetchAndRenderDevices: HTTP', response.status);
                return;
            }
            const data = await response.json();
            if (!data.ok) {
                console.warn('[AoT Map] fetchAndRenderDevices: API error', data.message);
                return;
            }

            const devices = data.devices || [];
            // Merge measurements from API response into vars so popup can use them
            if (data.all_measurements_map) {
                wOpts.all_measurements_map = data.all_measurements_map;
            }

            if (devices.length > 0) {
                addDeviceMarkers(uniqueId, map, devices, vars.theme, vars);
                // [3-way Actuator] Immediately reflect initial state on geo-design
                // labels (parent_type=aot_device). Without this they wait one full
                // poll cycle before showing the position %.
                const instance = window.AoTWidgetInstances[uniqueId];
                if (instance) {
                    try { _updateGeoDesignDeviceLabels(instance, devices, vars.theme); } catch (e) {}
                }
            }
        } catch (e) {
            console.warn('[AoT Map] fetchAndRenderDevices failed:', e);
        }
    }

    /**
     * Setup automatic refresh — re-fetches device data from API.
     */
    /**
     * Refresh device marker appearance (color, label text) without remove/re-add.
     * Called by setupRefresh. Positions never change → no flicker.
     */
    function refreshDeviceMarkersAppearance(uniqueId, devices, wOpts) {
        const instance = window.AoTWidgetInstances[uniqueId];
        if (!instance) return;

        const showDeviceLabels = wOpts.show_device_labels === true || wOpts.show_device_labels === 'true';
        const globalLabelSize = parseFloat(wOpts.global_label_size) || 1.0;
        const targetMap = wOpts.all_measurements_map || wOpts.measurements_map || {};
        const theme = (instance.vars && instance.vars.theme) || {};

        devices.forEach(function(dev) {
            const markerId = dev.unique_id || dev.id;
            const marker = instance.markers.get(markerId);
            if (!marker) return;

            let isON = dev.status === 'active' || dev.status === 'on' ||
                         dev.is_activated === true || dev.is_activated === 'true';
            const devType2 = dev.device_type || dev.type || '';
            const userColor = getUnifiedDeviceColor(devType2, dev, theme);
            const el = marker.getElement();

            // [3-way Actuator] Override "on" semantics: label ON only when MOTION is
            // happening (transient). Motion is detected via position changes between
            // polls (or a recent commandActuator call). At rest at any position, the
            // label renders in the off style — consistent with other outputs.
            if (dev.control_kind === 'value_3way') {
                const newPos = (typeof dev.position_pct === 'number') ? dev.position_pct : 0;
                const prevPos = (typeof marker._prevPosPct === 'number') ? marker._prevPosPct : newPos;
                if (Math.abs(newPos - prevPos) > 0.5) {
                    marker._motion_detected_ts = Date.now();
                }
                marker._prevPosPct = newPos;
                const motionTs = marker._motion_detected_ts || 0;
                const cmdTs = marker._pending_command || 0;
                const motionWindowMs = 7000; // ~one poll cycle + grace
                isON = (Date.now() - Math.max(motionTs, cmdTs)) < motionWindowMs;
            }

            if (showDeviceLabels) {
                // Update pill: measurement value + color
                const devIdKey = dev.device_id || dev.device_unique_id ||
                    (dev.unique_id ? dev.unique_id.split('::')[0] : (dev.id || '').split('::')[0]);
                const devMeas = targetMap[devIdKey] || [];
                let firstVal = '', unit = '';
                if (devMeas.length > 0) {
                    const m = devMeas.find(function(x) { return parseInt(x.channel) === parseInt(dev.channel_id); }) || devMeas[0];
                    if (m && m.last_value !== undefined && m.last_value !== null && m.last_value !== '') {
                        firstVal = String(m.last_value);
                        unit = (window.aotMapUnits && window.aotMapUnits[m.id]) ? window.aotMapUnits[m.id] : (m.unit || '');
                        if (unit === 'bearing') unit = '';
                    }
                }
                // [3-way Actuator] Live position % refresh for labels
                if (dev.control_kind === 'value_3way') {
                    const p = (typeof dev.position_pct === 'number') ? dev.position_pct : 0;
                    const dir = dev.motion_dir;
                    const arrow = (dir === 'open') ? '▲ ' : (dir === 'close') ? '▼ ' : '';
                    firstVal = arrow + Math.round(p);
                    unit = '%';
                    // Also sync open popup's position display + slider (if not focused)
                    const posDisp = document.getElementById('pos-disp-' + (dev.id || dev.unique_id || ''));
                    if (posDisp) posDisp.innerText = Math.round(p) + '%';
                    const slider = document.getElementById('pos-slider-' + (dev.id || dev.unique_id || ''));
                    if (slider && document.activeElement !== slider) {
                        const r2 = Math.round(p);
                        slider.value = r2;
                        slider.style.setProperty('--aot-3way-fill', r2 + '%');
                    }
                }
                const valEl = el.querySelector('.dev-value');
                const unitEl = el.querySelector('.dev-unit');
                const valGroup = el.querySelector('.dev-val-group');
                if (valEl && firstVal !== '') { valEl.textContent = firstVal; if (valGroup) valGroup.style.display = 'inline'; }
                else if (valGroup) valGroup.style.display = 'none';
                if (unitEl) unitEl.textContent = unit;

                const pillEl = el.querySelector('.marker-pill');
                if (pillEl) {
                    const shadowOn  = hexToRgba(userColor, 0.6);
                    const shadowOff = hexToRgba(userColor, 0.3);
                    if (isON) {
                        pillEl.style.backgroundColor = userColor;
                        pillEl.style.color = '#fff';
                        pillEl.style.border = '2px solid #fff';
                        pillEl.style.boxShadow = '0 4px 12px ' + shadowOn;
                    } else {
                        pillEl.style.backgroundColor = '#fff';
                        pillEl.style.color = userColor;
                        pillEl.style.border = '2px solid ' + userColor;
                        pillEl.style.boxShadow = '0 2px 5px ' + shadowOff;
                    }
                }
            } else {
                // Update dot color
                el.style.backgroundColor = isON ? userColor : '#fff';
                el.style.borderColor = userColor;
            }

            // --- Sync open popup: toggle button + stopwatch ---
            const devId2   = String(dev.id || dev.unique_id || '');
            const baseId2  = devId2.split('::')[0];
            const ch2      = (dev.channel_id && dev.channel_id !== 'undefined') ? dev.channel_id : 0;
            const isOutput2 = (devType2 === 'output' || devType2 === 'function');

            // 1. Update toggle checkbox (popup is open when element exists in DOM)
            var toggleEl = document.getElementById('toggle-' + devId2);
            if (toggleEl) {
                toggleEl.checked = isON;
            }

            // 2. Update stopwatch — only relevant for output/function devices
            if (isOutput2) {
                var durEl2 = document.getElementById('dur-' + devId2);
                if (durEl2 && window.AoTStopwatchManager) {
                    if (isON) {
                        // Device ON: register/update timer
                        var swKey2 = window.AoTStopwatchManager.register(
                            baseId2, ch2, true, null, durEl2, 7000, false
                        );
                        // Force immediate sync when:
                        //  - first observation (no cached state yet), or
                        //  - state just transitioned from OFF → ON
                        var prevState2 = instance._deviceStateCache && instance._deviceStateCache[devId2];
                        if (prevState2 !== true) {
                            window.AoTStopwatchManager.sync(swKey2);
                        }
                    } else {
                        // Device OFF: stop timer, reset display
                        window.AoTStopwatchManager.register(
                            baseId2, ch2, false, null, durEl2, 7000, false
                        );
                    }
                }
            }

            // Cache current ON/OFF state for next cycle comparison
            if (!instance._deviceStateCache) instance._deviceStateCache = {};
            instance._deviceStateCache[devId2] = isON;
        });

        // Update aot-devices shape opacity based on device on/off state
        // on: fill-opacity 0.9 / line-opacity 1.0
        // off: fill-opacity 0.2 / line-opacity 0.5
        _updateDeviceShapeOpacity(instance, devices);

        // Update geo-design aot_device label marker color/opacity based on device state
        _updateGeoDesignDeviceLabels(instance, devices, theme);
    }

    /**
     * Update geo-design label_aux markers that have aot_device parent type.
     * ON  → device theme color, full opacity.
     * OFF → dimmed grey, reduced opacity.
     * Called by refreshDeviceMarkersAppearance at every refresh cycle.
     */
    function _updateGeoDesignDeviceLabels(instance, devices, theme) {
        if (!instance.labelMarkers || !instance.labelMarkers.length) return;

        // Build lookup: base device_id → { isON, devType, controlKind, positionPct }
        // [3-way Actuator] For value_3way devices, treat "ON" as motion in progress
        // (position change since last poll). isActivated alone is position>0, which
        // is misleading for a resting actuator — at rest it should look like other
        // outputs in off state.
        const stateMap = {};
        devices.forEach(function(dev) {
            const devId = String(dev.device_id || (dev.unique_id ? dev.unique_id.split('::')[0] : '') || dev.id || '');
            if (!devId) return;
            const devType = dev.device_type || dev.type || '';
            const controlKind = dev.control_kind || 'on_off';
            const positionPct = (typeof dev.position_pct === 'number') ? dev.position_pct : null;

            let isON = dev.status === 'active' || dev.status === 'on' ||
                       dev.is_activated === true || dev.is_activated === 'true';

            if (controlKind === 'value_3way') {
                // Track motion per device on the instance state
                if (!instance._3wayState) instance._3wayState = {};
                const tracker = instance._3wayState[devId] || {};
                const prev = (typeof tracker.prevPos === 'number') ? tracker.prevPos : (positionPct || 0);
                const curr = (positionPct != null) ? positionPct : 0;
                if (Math.abs(curr - prev) > 0.5) {
                    tracker.motionTs = Date.now();
                }
                tracker.prevPos = curr;
                instance._3wayState[devId] = tracker;
                const motionTs = tracker.motionTs || 0;
                isON = (Date.now() - motionTs) < 7000;
            }

            stateMap[devId] = {
                isON: isON,
                devType: devType,
                controlKind: controlKind,
                positionPct: positionPct,
            };
        });

        instance.labelMarkers.forEach(function(marker) {
            const el = marker.getElement();
            if (!el || el.dataset.parentType !== 'aot_device') return;
            const parentId = el.dataset.parentId || '';
            if (!parentId) return;
            const state = stateMap[parentId];
            if (!state) return;

            if (state.isON) {
                const color = getUnifiedDeviceColor(state.devType, {}, theme || {});
                el.style.backgroundColor = color;
                el.style.opacity = '1';
            } else {
                el.style.backgroundColor = '#999';
                el.style.opacity = '0.55';
            }

            // [3-way Actuator] Update the position % suffix beside the device name.
            const pctEl = el.querySelector('.aot-3way-pct');
            if (pctEl) {
                if (state.controlKind === 'value_3way' && state.positionPct != null) {
                    pctEl.textContent = ' ' + Math.round(state.positionPct) + '%';
                    pctEl.style.display = 'inline';
                } else {
                    pctEl.style.display = 'none';
                }
            }
        });
    }

    function _updateDeviceShapeOpacity(instance, devices) {
        const map = instance && instance.map;
        if (!map || !map.getLayer('aot-devices-fill')) return;

        const onIds = [];
        devices.forEach(function(dev) {
            const isON = dev.status === 'active' || dev.status === 'on' ||
                         dev.is_activated === true || dev.is_activated === 'true';
            if (isON) {
                const devId = String(dev.device_id || (dev.unique_id ? dev.unique_id.split('::')[0] : '') || dev.id || '');
                if (devId) onIds.push(devId);
            }
        });

        try {
            if (onIds.length > 0) {
                // MapLibre match: ['match', input, [label,...], outputIfMatch, defaultOutput]
                // ON device_ids → 0.9 opacity, all others → 0.2
                const fillExpr = ['match', ['get', 'device_id'], onIds, 0.9, 0.2];
                const lineExpr = ['match', ['get', 'device_id'], onIds, 1.0, 0.5];
                map.setPaintProperty('aot-devices-fill', 'fill-opacity', fillExpr);
                if (map.getLayer('aot-devices-line')) {
                    map.setPaintProperty('aot-devices-line', 'line-opacity', lineExpr);
                }
            } else {
                map.setPaintProperty('aot-devices-fill', 'fill-opacity', 0.2);
                if (map.getLayer('aot-devices-line')) {
                    map.setPaintProperty('aot-devices-line', 'line-opacity', 0.5);
                }
            }
        } catch (e) {
            console.warn('[AoT Map] Failed to update device shape opacity:', e);
        }
    }

    function setupRefresh(uniqueId, intervalSeconds) {
        const instance = window.AoTWidgetInstances[uniqueId];
        if (!instance) return;

        if (instance.refreshTimer) {
            clearInterval(instance.refreshTimer);
        }

        instance.refreshTimer = setInterval(function() {
            const vars = instance.vars;
            const map = instance.map;
            if (!vars || !map) return;

            const wOpts = (vars && vars.vars) || {};
            const mapUuid = wOpts.selected_map_uuid || wOpts.map_uuid || vars.contentMapUuid || '';
            const deviceIds = wOpts.map_device_ids || wOpts.device_ids || '';
            const includeAll = wOpts.include_all_devices === true || wOpts.include_all_devices === 'true';

            const params = new URLSearchParams();
            if (mapUuid) params.set('map_uuid', mapUuid);
            if (deviceIds) params.set('device_ids', deviceIds);
            params.set('include_all', String(includeAll));

            fetch('/api/geo/devices?' + params.toString())
                .then(function(r) { return r.json(); })
                .then(function(data) {
                    if (!data.ok) return;
                    const devices = data.devices || [];
                    if (data.all_measurements_map) wOpts.all_measurements_map = data.all_measurements_map;
                    // Update appearance only — no remove/re-add to prevent position flicker
                    if (devices.length > 0) {
                        refreshDeviceMarkersAppearance(uniqueId, devices, wOpts);
                    }
                })
                .catch(function(e) { console.warn('[AoT Map] Refresh failed:', e); });
        }, intervalSeconds * 1000);
    }

    /**
     * Clean up widget instance
     */
    window.destroyAoTMapVectorWidget = function(uniqueId) {
        const instance = window.AoTWidgetInstances?.[uniqueId];
        if (!instance) return;

        // Clear refresh timers
        if (instance.refreshTimer) {
            clearInterval(instance.refreshTimer);
        }
        if (instance.panelRefreshTimer) {
            clearInterval(instance.panelRefreshTimer);
        }

        // Remove all markers
        for (const marker of instance.markers.values()) {
            marker.remove();
        }

        // Remove unified collision handler
        if (instance._unifiedCollisionHandler && instance.map) {
            instance.map.off('moveend', instance._unifiedCollisionHandler);
            instance.map.off('zoomend', instance._unifiedCollisionHandler);
            instance._unifiedCollisionHandler = null;
        }

        // Remove geo/design label markers and cluster badges
        [
            'labelMarkers', 'siteZoneLabelMarkers', 'geoDeviceLabelMarkers',
            'labelClusterMarkers', 'siteZoneClusterMarkers', 'geoDeviceClusterMarkers',
            'deviceLabelMarkers', 'deviceClusterMarkers'
        ].forEach(function(key) {
            if (instance[key]) {
                instance[key].forEach(function(m) { try { m.remove(); } catch (e) {} });
                instance[key] = [];
            }
        });

        // Tear down restored UI
        if (instance.measurementPanel && typeof instance.measurementPanel.destroy === 'function') {
            try { instance.measurementPanel.destroy(); } catch (e) {}
        }
        if (instance.legendEl && instance.legendEl.parentNode) {
            instance.legendEl.parentNode.removeChild(instance.legendEl);
        }
        if (instance.toolbarLeft && instance.toolbarLeft.parentNode) {
            instance.toolbarLeft.parentNode.removeChild(instance.toolbarLeft);
        }
        if (instance.notePollTimer) {
            clearInterval(instance.notePollTimer);
            instance.notePollTimer = null;
        }
        if (instance.noteMarkers) {
            instance.noteMarkers.forEach(function(m) { try { m.remove(); } catch (e) {} });
            instance.noteMarkers.clear();
        }
        if (instance.layerPanelContainer && instance.layerPanelContainer.parentNode) {
            instance.layerPanelContainer.parentNode.removeChild(instance.layerPanelContainer);
        }

        // Remove map
        if (instance.map) {
            instance.map.remove();
        }

        delete window.AoTWidgetInstances[uniqueId];
    };

    console.log('[AoT Vector Widget] Script loaded - Pure MapLibre implementation v20260512f');

})();
