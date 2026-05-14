/**
 * aot-map-loader.js
 * Standardized Map Initialization for AoT
 * Handles Global Configuration, Settings, and Layer Loading
 */

// [Iteration 16] Emergency Master Shield Guard
// Ensures that DomUtil.remove is patched even if parent layout globalization was bypassed.
(function() {
    function applyShield() {
        if (typeof L !== 'undefined' && L.DomUtil && L.DomUtil.remove) {
            if (L.DomUtil.__AOT_MASTER_SHIELD) return;
            L.DomUtil.__AOT_MASTER_SHIELD = true;
            const origRem = L.DomUtil.remove;
            L.DomUtil.remove = function(el) {
                if (!el) return;
                try {
                    if (typeof el === 'object' && ('parentNode' in el) && el.parentNode) {
                        origRem.call(L.DomUtil, el); 
                    }
                } catch(e) { /* Silent */ }
            };
            console.log("[AoT] Emergency Master Shield Activated");
        }
    }
    applyShield();
    // Re-check after 500ms just in case L was re-loaded
    setTimeout(applyShield, 500);
})();

/**
 * [AoT] Bing Maps / QuadKey Support
 * Extends L.TileLayer to support {q} placeholder which converts (x, y, z) to QuadKey.
 */
if (typeof L !== 'undefined') {
    L.TileLayer.QuadKey = L.TileLayer.extend({
        getTileUrl: function (coords) {
            var i = coords.z, x = coords.x, y = coords.y;
            var quadKey = "";
            for (var j = i; j > 0; j--) {
                var digit = 0;
                var mask = 1 << (j - 1);
                if ((x & mask) != 0) digit += 1;
                if ((y & mask) != 0) digit += 2;
                quadKey += digit;
            }
            // Use parent's getTileUrl but replace {q} with calculated quadKey
            return L.TileLayer.prototype.getTileUrl.call(this, coords).replace('{q}', quadKey);
        }
    });
    L.tileLayer.quadKey = function(url, options) {
        return new L.TileLayer.QuadKey(url, options);
    };
}

if (!window.AoTMapLoader) {
    window.AoTMapLoader = {

    /**
     * Initializes a Leaflet map with standard AoT configuration
     * @param {string} containerId - DOM ID of map container
     * @param {Object} overrideOptions - Optional overrides 
     *        { lat, lng, zoom, layerType: 'xyz'|'wms', layers: [] }
     * @returns {Object} { map, baseLayers, activeLayer }
     */
    /**
     * Initialize Leaflet Map
     * @param {string} containerId - DOM ID of map container
     * @param {string} mapType - Preset type ('geo_setting_map', 'geo_input_map', 'general_map')
     * @param {object} customOptions - Overrides for Leaflet options
     * @returns {object} { map, baseLayers }
     */
    initMap: function (containerId, mapType = 'default', customOptions = {}) {
        // 1. Resolve Config & Presets
        const config = window.AOT_GEO_CONFIG || {};
        // [Fix] config IS the settings object (flat structure from backend). 
        // There is no nested 'settings' key.
        const settings = config;

        // Helper: Strict False check (handles 0, 'false', false)
        // Default is true if undefined, unless logic says otherwise
        const isTrue = (val, def = true) => {
            if (val === false || val === 'false' || val === 0 || val === '0') return false;
            if (val === true || val === 'true' || val === 1 || val === '1') return true;
            return def;
        };

        // Base Options (Global preferences from Config)
        // [New Logic] Read Positional Settings from Config (Source of Truth)
        // Robust parsing: Handle 0 value correctly (don't fallback on 0).
        let defaultLat = parseFloat(settings.default_lat);
        if (isNaN(defaultLat)) defaultLat = 37.5665;

        let defaultLng = parseFloat(settings.default_lng);
        if (isNaN(defaultLng)) defaultLng = 126.9780;

        let defaultZoom = parseFloat(settings.zoom);
        if (isNaN(defaultZoom)) defaultZoom = 12;

        let maxZoom = parseInt(settings.max_zoom);
        if (isNaN(maxZoom)) maxZoom = 25;

        const globalOptions = {
            center: [defaultLat, defaultLng],
            zoom: defaultZoom,
            maxZoom: maxZoom,
            preferCanvas: isTrue(settings.prefer_canvas, true),
            fadeAnimation: isTrue(settings.tile_fade_animation, true),
            zoomAnimation: isTrue(settings.tile_fade_animation, true),
            markerZoomAnimation: isTrue(settings.tile_fade_animation, true),
            zoomSnap: isTrue(settings.smooth_zoom, true) ? 0.25 : 1,
            zoomDelta: isTrue(settings.smooth_zoom, true) ? 0.25 : 1,
            attributionControl: false
        };

        // Presets per Map Type
        const presets = {
            'geo_setting_map': {
                zoomControl: false, // Custom controls used
                scrollWheelZoom: true,
                doubleClickZoom: true,
                dragging: true
            },
            'geo_input_map': {
                zoomControl: true,
                scrollWheelZoom: true,
                doubleClickZoom: true,
                dragging: true,
                trackResize: true
            },
            'general_map': {
                zoomControl: true,
                scrollWheelZoom: true,
                dragging: true
            },
            'default': {
                zoomControl: true
            }
        };

        const presetOptions = presets[mapType] || presets['default'];

        // Merge: Global Defaults < Preset < Custom Overrides
        const finalOptions = Object.assign({}, globalOptions, presetOptions, customOptions);

        // [Fix] Remove 'layers' from options passed to L.map
        // Leaflet expects 'layers' to be an array of ILayer objects, but we pass config objects.
        // We will handle layer addition manually in Step 3.
        const mapOptions = { ...finalOptions };
        delete mapOptions.layers;

        // 2. Create Map (Pure MapLibre GL via AoTMapLibreLoader)
        let map = null;
        if (typeof AoTMapLibreLoader !== 'undefined') {
            // Use pure MapLibre loader for 3D support (pitch, bearing, terrain)
            const mlMap = AoTMapLibreLoader.initMap(containerId, {
                center: [defaultLng, defaultLat],
                zoom: defaultZoom,
                maxZoom: maxZoom,
                pitch: mapOptions.pitch || 0,
                bearing: mapOptions.bearing || 0,
                zoomControl: mapOptions.zoomControl !== false,
                scrollWheelZoom: mapOptions.scrollWheelZoom !== false
            });
            // Wrap the MapLibre map in L.map-compatible interface
            if (mlMap && typeof L !== 'undefined' && L.Map) {
                // Create L.map wrapper and inject the MapLibre map
                map = L.map(containerId, mapOptions);
                // Replace the internally-created MapLibre map with the AoTMapLibreLoader one
                if (map._mlMap && map._mlMap.remove) {
                    map._mlMap.remove(); // Remove the auto-created one
                }
                map._mlMap = mlMap; // Use the AoTMapLibreLoader's map (3D-ready)
                // Re-sync events
                const self = map;
                mlMap.on('click', (e) => self._emit('click', { latlng: new L.LatLng(e.lngLat.lat, e.lngLat.lng) }));
                mlMap.on('dblclick', (e) => self._emit('dblclick', { latlng: new L.LatLng(e.lngLat.lat, e.lngLat.lng) }));
                mlMap.on('contextmenu', (e) => self._emit('contextmenu', { latlng: new L.LatLng(e.lngLat.lat, e.lngLat.lng) }));
                mlMap.on('zoom', () => self._emit('zoom'));
                mlMap.on('move', () => self._emit('move'));
                mlMap.on('moveend', () => self._emit('moveend'));
                mlMap.on('layeradd', (e) => self._emit('layeradd', { layer: e.layer }));
                mlMap.on('overlayadd', (e) => self._emit('overlayadd', { layer: e.layer }));
                mlMap.on('overlayremove', (e) => self._emit('overlayremove', { layer: e.layer }));
                mlMap.on('resize', () => self._emit('resize'));
            } else if (mlMap) {
                map = mlMap; // Use MapLibre map directly as fallback
            }
        }
        // Fallback: Use L.map shim (MapLibre-backed)
        if (!map && typeof L !== 'undefined' && typeof L.map !== 'undefined') {
            map = L.map(containerId, mapOptions);
        }
        if (!map) {
            console.error('[AoTMapLoader] No map engine available');
            return { map: null, baseLayers: {}, overlays: {}, activeLayer: null, layerControl: null };
        }

        // [New] Virtual Layers for "Data Only" mode
        map.aotVirtualLayers = [];

        // [Fix] Add Attribution Control EARLY (Before layers)
        // This ensures layers added in step 3 register their attribution correctly.
        // User requested Bottom-Left.
        // Z-Index: Set lower than tools (which are usually 1000+ or handled by containers).
        // [Fix] Add Attribution Control via Central Utility
        // This ensures consistent behavior (VWorld Logo injection, positioning)
        if (window.AoTMapUtils && window.AoTMapUtils.addCopyrightControl) {
            window.AoTMapUtils.addCopyrightControl(map);
        } else if (map._mlMap && maplibregl && maplibregl.AttributionControl) {
            // MapLibre: use native attribution
            map._mlMap.addControl(new maplibregl.AttributionControl({ compact: true }), 'bottom-right');
        } else if (typeof L !== 'undefined' && L.control && L.control.attribution) {
            // Fallback: L shim attribution
            L.control.attribution({ prefix: false, position: 'bottomleft' }).addTo(map);
        }

        // 3. Add Layers (Base Maps & Overlays)
        // Allow override from customOptions (e.g. for Preview Map to be clean)
        const layers = (customOptions.layers !== undefined) ? customOptions.layers : (config.layers || []);
        map.aotBaseMaps = {};
        map.aotOverlayMaps = {};
        let activeBaseLayer = null;

        // Helper to get or create Layer Control
        let layerControl = null;
        const ensureLayerControl = () => {
            if (!layerControl) {
                // Create if not exists (showing whatever base/overlays we have so far)
                if (Object.keys(map.aotBaseMaps).length > 0 || Object.keys(map.aotOverlayMaps).length > 0) {
                    if (map._mlMap && maplibregl && maplibregl.NavigationControl) {
                        // MapLibre: use navigation control instead of layer switcher
                        // Layer management is handled via source/layer visibility
                        map._mlMap.addControl(new maplibregl.NavigationControl({ showCompass: true, showZoom: true }), 'top-right');
                    }
                    layerControl = L.control.layers(map.aotBaseMaps, map.aotOverlayMaps).addTo(map);
                }
            }
            return layerControl;
        };

        layers.forEach(l => {
            let layerFunc = null;
            let finalUrl = l.url;
            const finalOpts = { ...l.options };

            // [Common] Relative Date Calculation
            // Supports keywords: today, 1_day_ago, 2_days_ago, 7_days_ago
            if (finalOpts.date_mode) {
                const mode = finalOpts.date_mode;
                const now = new Date();
                let dateStr = 'default';

                if (mode === 'today') {
                    dateStr = now.toISOString().split('T')[0];
                } else if (mode === '1_day_ago') {
                    now.setDate(now.getDate() - 1);
                    dateStr = now.toISOString().split('T')[0];
                } else if (mode === '2_days_ago') {
                    now.setDate(now.getDate() - 2);
                    dateStr = now.toISOString().split('T')[0];
                } else if (mode === '7_days_ago') {
                    now.setDate(now.getDate() - 7);
                    dateStr = now.toISOString().split('T')[0];
                } else if (mode === 'custom' && finalOpts.target_date) {
                    dateStr = finalOpts.target_date;
                }

                if (dateStr !== 'default') {
                    finalOpts.time = dateStr;
                }
            }

            // [Fix] Generic Placeholder Replacement from finalOpts
            // This replaces {time}, {layer}, {style}, {tilematrixset}, etc.
            if (finalUrl && finalOpts) {
                Object.keys(finalOpts).forEach(key => {
                    const val = finalOpts[key];
                    if (typeof val === 'string' || typeof val === 'number') {
                        // Use regex for global replacement of {key}
                        finalUrl = finalUrl.split('{' + key + '}').join(val);
                    }
                });
            }

            // Resolve API Keys (Explicit fallback if not in options)
            if (l.api_key) {
                finalUrl = finalUrl.split('{api_key}').join(l.api_key)
                                   .split('{key}').join(l.api_key)
                                   .split('{accessToken}').join(l.api_key);
                finalOpts['accessToken'] = l.api_key;
                finalOpts['key'] = l.api_key;
                finalOpts['apikey'] = l.api_key;
            } else if (config.keys) {
                const kf = l.key_field || (l.requires_key ? 'default' : null);
                if (kf && config.keys[kf]) {
                    const k = config.keys[kf];
                    finalUrl = finalUrl.split('{api_key}').join(k)
                                       .split('{key}').join(k)
                                       .split('{accessToken}').join(k);
                }
            }

            // [Fix] Inject Attribution from Layer Config if available
            if (l.attribution && !finalOpts.attribution) {
                finalOpts.attribution = l.attribution;
            }

            // [New Logic] Digital Zoom Handling
            const useDigital = isTrue(settings.digital_zoom, true);
            if (useDigital) {
                // Ensure number formatting (handle string inputs from config)
                let layerMax = finalOpts.maxZoom;
                if (layerMax !== undefined) layerMax = parseInt(layerMax, 10);

                let layerNative = finalOpts.maxNativeZoom;
                if (layerNative !== undefined) layerNative = parseInt(layerNative, 10);

                // If native max is missing or invalid
                if (layerNative === undefined || isNaN(layerNative)) {
                    // Infers from maxZoom if available (e.g. Esri=17)
                    if (layerMax !== undefined && !isNaN(layerMax)) {
                        finalOpts.maxNativeZoom = layerMax;
                    } else {
                        finalOpts.maxNativeZoom = 19; // Default Standard
                    }
                } else {
                    // Explicit native max exists
                    finalOpts.maxNativeZoom = layerNative;
                }

                // Debug Log for Esri (or high diff layers)
                if (l.name && (l.name.includes('Esri') || l.name.includes('Satellite'))) {
                    /* console.log(`[AoTMapLoader] Digital Zoom Active for ${l.name}:`, {
                        native: finalOpts.maxNativeZoom,
                        scalingTo: finalOptions.maxZoom,
                        configMax: finalOpts.maxZoom
                    }); */
                }

                // Force global max to allow scaling
                finalOpts.maxZoom = finalOptions.maxZoom;
            }

            // [Fix] RainViewer Global Support - Vector Mode (MapLibre) and Raster Mode (Leaflet)
            // RainViewer provides historical radar data via PNG tiles
            if (finalUrl && finalUrl.includes('{ts}')) {
                // Fetch timestamp metadata from backend proxy
                fetch('/api/geo/proxy/rainviewer/meta')
                    .then(r => {
                        if (!r.ok) throw new Error("RainViewer API error");
                        return r.json();
                    })
                    .then(data => {
                        // Extract timestamps for animation
                        let timestamps = [];
                        if (data.radar && data.radar.past) {
                            data.radar.past.forEach(item => {
                                if (item.time) timestamps.push(item.time);
                            });
                        }
                        
                        if (timestamps.length === 0) {
                            console.info("[AoT] RainViewer: No radar timestamps available");
                            return;
                        }
                        
                        // Get the most recent timestamp
                        const lastTs = timestamps[timestamps.length - 1];
                        const realUrl = finalUrl.replace('{ts}', lastTs);
                        
                        // Check if we're in vector mode (MapLibre) or raster mode (Leaflet)
                        if (typeof window.AoTVectorLayerManager !== 'undefined' && 
                            window.AOT_GEO_CONFIG && 
                            window.AOT_GEO_CONFIG.geo_mode === 'vector') {
                            
                            // === Vector Mode: Use MapLibre raster source ===
                            if (typeof maplibregl !== 'undefined') {
                                const vectorManager = window.AoTVectorLayerManager.bind(map);
                                
                                // Configure RainViewer for MapLibre
                                const rainviewerConfig = {
                                    url: finalUrl,
                                    currentTimestamp: lastTs,
                                    colorScheme: l.color_scheme || '2',
                                    smoothing: l.smoothing !== false,
                                    opacity: finalOpts.opacity || 0.7,
                                    maxZoom: finalOpts.maxNativeZoom || 7,
                                    frameInterval: 600,
                                    totalFrames: timestamps.length
                                };
                                
                                vectorManager.addRainViewerSource(l.id, rainviewerConfig);
                                
                                // Store reference for animation control
                                map.aotVectorLayerManager = vectorManager;
                                map.aotRainViewerTimestamps = timestamps;
                                
                                console.info("[AoT] RainViewer: Added to vector map (timestamps: " + timestamps.length + ")");
                                
                                // Auto-start animation if visible
                                if (l.visible !== false) {
                                    setTimeout(() => {
                                        if (vectorManager.layers.has(l.id)) {
                                            vectorManager.startRainViewerAnimation(l.id, timestamps, 600);
                                        }
                                    }, 1000);
                                }
                            } else {
                                console.warn("[AoT] RainViewer: maplibregl not available");
                            }
                        } else if (window.L && typeof L !== 'undefined') {
                            // === Raster Mode: Use Leaflet ===
                            let rvLayer = null;
                            if (l.type === 'xyz') rvLayer = L.tileLayer(realUrl, finalOpts);
                            else if (l.type === 'wms') rvLayer = L.tileLayer.wms(realUrl, finalOpts);

                            if (rvLayer) {
                                rvLayer.aot_id = l.id;
                                rvLayer.aot_base_id = l.base_id || l.id;
                                rvLayer.name = l.name;
                                if (l.legend) {
                                    rvLayer.aot_legend = l.legend;
                                }

                                map.aotOverlayMaps[l.name] = rvLayer;

                                let shouldAdd = false;
                                if (l.visible !== undefined && l.visible !== null) {
                                    shouldAdd = (l.visible === true || l.visible === 'true');
                                } else {
                                    shouldAdd = (l.is_active || l.is_default);
                                }

                                if (shouldAdd) {
                                    rvLayer.addTo(map);
                                }

                                const ctl = ensureLayerControl();
                                if (ctl) {
                                    ctl.addOverlay(rvLayer, l.name);
                                } else {
                                    layerControl = L.control.layers(map.aotBaseMaps, map.aotOverlayMaps).addTo(map);
                                }
                                
                                if (shouldAdd && typeof updateLegendAndSyncPanel === 'function') {
                                    updateLegendAndSyncPanel();
                                }
                                
                                console.info("[AoT] RainViewer: Added to raster map");
                            }
                        } else {
                            console.info("[AoT] RainViewer skipped: No map engine available");
                        }
                    }).catch(e => { 
                         console.info("[AoT] RainViewer: Service unavailable (" + e.message + ")"); 
                    });
                return; // Skip sync creation
            }

            // [Fix] Skip invalid URLs with unreplaced placeholders to prevent crash
            if (finalUrl && finalUrl.match(/\{(x|y|z|s|r|q)\}/) === null && finalUrl.match(/\{([a-zA-Z0-9_]+)\}/)) {
                // URL has placeholders OTHER than x,y,z,s,r (e.g. {key}, {style} missing)
                // console.warn("[AoTMapLoader] Skipping layer with unreplaced placeholders:", l.name, finalUrl);
                return;
            }

            if (l.type === 'vector' && finalUrl) {
                // Vector tile layer via MapLibre GL (rendered inside Leaflet via bridge)
                if (typeof L.MapLibreGL !== 'undefined') {
                    layerFunc = L.maplibreGL({
                        style: finalUrl,
                        attribution: finalOpts.attribution || l.attribution || ''
                    });
                } else {
                    // Bridge not loaded: fall back to blank placeholder so the map still opens
                    console.warn('[AoTMapLoader] L.MapLibreGL bridge not available for vector layer:', l.name);
                }
            } else if (l.type === 'xyz' && finalUrl) {
                // [New] Check for QuadKey placeholder
                if (finalUrl.indexOf('{q}') !== -1) {
                    layerFunc = L.tileLayer.quadKey(finalUrl, finalOpts);
                } else {
                    layerFunc = L.tileLayer(finalUrl, finalOpts);
                }
            } else if (l.type === 'wms' && finalUrl) {
                layerFunc = L.tileLayer.wms(finalUrl, finalOpts);
            } else if (l.data || l.type === 'geojson') {
                // [New] GeoJSON Support
                // If backend provided data content (e.g. SGIS stats), render it as GeoJSON
                try {
                    layerFunc = L.geoJSON(l.data, {
                        onEachFeature: function (feature, layer) {
                            if (feature.properties && feature.properties.popupContent) {
                                layer.bindPopup(feature.properties.popupContent);
                            }
                        },
                        pointToLayer: function (feature, latlng) {
                            // Simple Circle Marker
                            return L.circleMarker(latlng, {
                                radius: 8,
                                fillColor: "#ff7800",
                                color: "#000",
                                weight: 1,
                                opacity: 1,
                                fillOpacity: 0.8
                            });
                        }
                    });
                } catch (e) {
                    console.warn("[AoTMapLoader] GeoJSON Render Error:", e);
                }
            }

            if (layerFunc) {
                // Attach Metadata for Persistence Tracking
                layerFunc.aot_id = l.id; // Unique GeoLayer ID (Exploded if applicable)
                layerFunc.aot_base_id = l.base_id || l.id; // [Fix] Track DB ID
                layerFunc.name = l.name; // [Fix] Store name for virtual layer persistence

                // [New] Attach Legend Data
                if (l.legend) {
                    layerFunc.aot_legend = l.legend;
                }

                if (l.channel_id !== undefined) {
                    layerFunc.aot_channel_id = l.channel_id;
                }

                // Check if Base Layer
                // Support both legacy 'is_base' and new 'role' property
                const isBase = (l.is_base === true) || (l.role === 'base');

                if (isBase) {
                    map.aotBaseMaps[l.name] = layerFunc;

                    const isExplicit = (l.visible === true || l.visible === 'true');

                    if (isExplicit) {
                        // Found saved preference: Replace any existing active layer
                        if (activeBaseLayer) {
                            map.removeLayer(activeBaseLayer);
                        }
                        layerFunc.addTo(map);
                        activeBaseLayer = layerFunc;
                        activeBaseLayer.isExplicit = true;
                    } else {
                        // Not explicit: Default to first base layer appearing (Fallback)
                        if (!activeBaseLayer) {
                            layerFunc.addTo(map);
                            activeBaseLayer = layerFunc;
                            activeBaseLayer.isFallback = true;
                        } else if (activeBaseLayer.isFallback === true) {
                            // Keep fallback until explicit found
                        }
                    }
                } else {
                    map.aotOverlayMaps[l.name] = layerFunc;
                    // Overlays are usually OFF by default unless specified
                    // Check if explicit active flag or strictly overlay role with active flag

                    // [Fix] Respect explicit 'visible' property from backend (User Preference)
                    let shouldAdd = false;
                    if (l.visible !== undefined && l.visible !== null) {
                        shouldAdd = (l.visible === true || l.visible === 'true');
                    } else {
                        // Fallback to legacy is_active behavior
                        shouldAdd = (l.is_active || l.is_default);
                    }

                    if (shouldAdd) {
                        // [New] Overlay Data Only Support
                        // If enabled, we do NOT add to map (no tiles), but track it for Legends.
                        if (customOptions.overlayDataOnly) {
                            // console.log(`[AoTMapLoader] "${l.name}" added as Data-Only layer.`);
                            map.aotVirtualLayers.push(layerFunc);
                            // Note: No 'layeradd' event fired, so we must trigger updateLegend manually at end.
                        } else {
                            layerFunc.addTo(map);
                        }
                    }
                }
            }
        });

        // Fallback: If no BASE layer found, add Default OSM
        if (!activeBaseLayer) {
            // [UX] Demote to info/log to avoid user panic. It is standard behavior.
            // console.log("[AoTMapLoader] Using fallback OSM (No custom base layer active).");
 
            // Check Digital Zoom for Fallback
            const useDigital = isTrue(settings.digital_zoom, true);
            const osmOpts = {
                attribution: '© OpenStreetMap'
            };

            if (useDigital) {
                osmOpts.maxNativeZoom = 19;
                osmOpts.maxZoom = globalOptions.maxZoom || 25;
            } else {
                osmOpts.maxZoom = 19;
            }

            const osm = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', osmOpts);
            osm.addTo(map);
            activeBaseLayer = osm;
            map.aotBaseMaps['OpenStreetMap'] = osm;
        }

        // 4. Add Layer Control
        // [UX] Always add if we have at least one layer (even if just Fallback OSM).
        // This ensures the "Layer Manager" icon appears, confirming it's working.
        if (Object.keys(map.aotBaseMaps).length > 0 || Object.keys(map.aotOverlayMaps).length > 0) {
            layerControl = L.control.layers(map.aotBaseMaps, map.aotOverlayMaps).addTo(map);
        }

        // 5. Add Legend Control (Generic)
        const legendControl = L.control({ position: 'bottomright' });

        legendControl.onAdd = function (map) {
            const div = L.DomUtil.create('div', 'aot-legend-container');
            div.style.display = 'none'; // Hidden by default

            // Note: Styles are now handled in map.css (.aot-legend-container)
            // margins are handled by .leaflet-bottom .leaflet-control spacing or CSS.

            return div;
        };
        legendControl.addTo(map);

        // [Fix] Add wrapper class for mobile positioning control
        if (legendControl.getContainer()) {
            legendControl.getContainer().classList.add('aot-legend-wrapper-control');
        }

        // Helper: Refresh Legend Content
        let legendMoveListener = null;

        const updateLegend = () => {
            const container = legendControl.getContainer();

            // Clear previous move listener
            if (legendMoveListener) {
                map.off('moveend', legendMoveListener);
                legendMoveListener = null;
            }

            if (!container) return;
            container.innerHTML = ''; // Reset
            container.style.display = 'none';

            // Find all visible layers with a legend (Map Layers + Virtual Layers)
            const targetLayers = [];

            // 1. Visible Map Layers
            map.eachLayer(layer => {
                if (layer.aot_legend) {
                    targetLayers.push(layer);
                }
            });

            // 2. Virtual Data Layers
            if (map.aotVirtualLayers && map.aotVirtualLayers.length > 0) {
                map.aotVirtualLayers.forEach(layer => {
                    if (layer.aot_legend) {
                        targetLayers.push(layer);
                    }
                });
            }
 
            // console.log("[LegendDebug] Layers with legends found:", targetLayers.length);
 
            if (targetLayers.length === 0) {
                return;
            }

            container.style.display = 'block';

            // Render Stacked Legends
            targetLayers.forEach((layer, index) => {
                const legendData = layer.aot_legend;
                const wrapper = L.DomUtil.create('div', 'aot-legend-item-wrapper');

                if (legendData.type === 'html') {
                    wrapper.innerHTML = legendData.content;

                    // Inject API Key into Value Box for Dynamic Fetching
                    const valueBox = wrapper.querySelector('.aot-legend-value-box');
                    const apiKey = layer.options ? (layer.options.apiKey || layer.options.api_key) : null;

                    if (valueBox && apiKey) {
                        valueBox.dataset.apiKey = apiKey;
                    }

                } else if (legendData.type === 'img') {
                    wrapper.innerHTML = `<img src="${legendData.url}" alt="Legend" style="max-width:100%;">`;
                }

                container.appendChild(wrapper);
            });

            // Setup Dynamic Updater
            const fetchAllValues = () => {
                // [Fix] Visibility Guard to prevent fetching when hidden
                if (container.offsetParent === null) return;

                const boxes = container.querySelectorAll('.aot-legend-value-box');
                if (boxes.length === 0) return;

                const center = map.getCenter();

                boxes.forEach(box => {
                    const apiKey = box.dataset.apiKey; // Optional now
                    const paramPath = box.getAttribute('data-api-param'); // Required
                    const customUrl = box.getAttribute('data-api-url');   // Optional
                    const valueText = box.querySelector('.aot-legend-value-text');

                    if (!valueText || !paramPath) return;

                    // Determine URL
                    let url = '';
                    if (customUrl) {
                        // Round to 3 decimal places (~111m precision) to maximise cache hits.
                        // ISRIC SoilGrids native resolution is ~250m, so this loses no useful precision.
                        const rLat = Math.round(center.lat * 1000) / 1000;
                        const rLng = Math.round(center.lng * 1000) / 1000;
                        url = customUrl.replace('{lat}', rLat)
                            .replace('{lon}', rLng)
                            .replace('{lng}', rLng)
                            .replace('{apiKey}', apiKey || '');
                    } else {
                        if (!apiKey) return;
                        url = `https://api.openweathermap.org/data/2.5/weather?lat=${center.lat}&lon=${center.lng}&appid=${apiKey}&units=metric`;
                    }

                    /* 
```javascript
                    // [Temporarily Unblocked per user request]
                    if (url.includes('isric.org')) {
                        valueText.innerText = '-';
                        return;
                    }
                    */

                    valueText.innerText = '...';

                    // [Fix] Use AoTAPIManager for caching and deduplication
                    const requestPromise = window.AoTAPIManager 
                        ? window.AoTAPIManager.request(url)
                        : fetch(url).then(r => r.json());
                    
                    requestPromise.then(data => {
                            const keys = paramPath.split('.');
                            let val = data;
                            for (let k of keys) {
                                if (val && k in val) {
                                    val = val[k];
                                } else if (val && !isNaN(parseInt(k)) && Array.isArray(val)) {
                                    val = val[parseInt(k)];
                                } else {
                                    val = undefined;
                                    break;
                                }
                            }

                            if (val !== undefined && val !== null) {
                                let finalVal = parseFloat(val);
                                
                                const dFactor = box.getAttribute('data-d-factor');
                                if (dFactor) {
                                    finalVal = finalVal / parseFloat(dFactor);
                                }

                                valueText.innerText = Math.round(finalVal * 100) / 100;
                            } else {
                                valueText.innerText = '-';
                            }
                        })
                        .catch(err => {
                            console.warn('Legend Fetch Error:', url, err); 
                            valueText.innerText = 'Error';
                            valueText.title = 'Failed to fetch data. Check console.';
                        });
                });
            };

            // Register Listener (Debounced)
            let debounceTimer;
            legendMoveListener = () => {
                clearTimeout(debounceTimer);
                debounceTimer = setTimeout(() => {
                    fetchAllValues();
                }, 500);
            };
            map.on('moveend', legendMoveListener);

            // Initial Fetch (Delayed to prevent thread blocking during load)
            setTimeout(fetchAllValues, 200);
        };

        // Listeners for Layer Changes
        const updateLegendAndSyncPanel = () => {
            updateLegend();
            // [Fix] Also sync MeasurementPanel layout for side-by-side desktop view
            if (map._aotMeasurementPanel) {
                map._aotMeasurementPanel.adjustLayout();
            }
        };

        // [Fix] Overlay Data Only Interceptor
        // Intercepts layer control events to prevent tile display in overlay_data_only mode
        map._aotOverlayDataOnly = !!customOptions.overlayDataOnly;

        if (map._aotOverlayDataOnly) {
            map.on('overlayadd', function(e) {
                // Intercept all overlay adds: remove tile layer from map, add to virtual layers
                map.removeLayer(e.layer);
                if (!map.aotVirtualLayers) map.aotVirtualLayers = [];
                map.aotVirtualLayers.push(e.layer);
                updateLegendAndSyncPanel();
            });

            map.on('overlayremove', function(e) {
                // Remove from virtual layers array if present
                if (map.aotVirtualLayers) {
                    const idx = map.aotVirtualLayers.indexOf(e.layer);
                    if (idx !== -1) {
                        map.aotVirtualLayers.splice(idx, 1);
                        updateLegendAndSyncPanel();
                    }
                }
            });
        }

        map.on('overlayadd', updateLegendAndSyncPanel);
        map.on('overlayremove', updateLegendAndSyncPanel);
        map.on('layerremove', updateLegendAndSyncPanel);
        
        // Also initial update
        setTimeout(updateLegendAndSyncPanel, 300);


        // Return standard object
        return {
            map: map,
            baseLayers: map.aotBaseMaps,
            overlays: map.aotOverlayMaps,
            activeLayer: activeBaseLayer,
            layerControl: layerControl
        };
    },

    /**
     * Toggles a device ON/OFF via API
     * Supports both Outputs and Functions
     * @param {string} deviceId - Unique ID of device
     * @param {boolean} state - Target state
     * @param {number} channel - Optional channel index
     * @param {string} deviceType - 'output' or 'function'
     */
    toggleDevice: function (deviceId, state, channel = 0, deviceType = 'output') {
        if (channel === 'undefined' || channel === 'null' || !channel) channel = 0;
        
        let baseId = deviceId;
        if (deviceId && deviceId.indexOf('::') !== -1) {
            baseId = deviceId.split('::')[0];
        }

        if (deviceType === 'function') {
            // Function toggle logic (Activate/Deactivate)
            const formData = new FormData();
            formData.append('function_id', baseId);
            if (state) {
                formData.append('function_activate', 'True');
            } else {
                formData.append('function_deactivate', 'True');
            }

            fetch('/function_submit', {
                method: 'POST',
                body: formData
            })
            .then(res => res.json())
            .then(data => {
                // console.log(`[AoTMapLoader] Function control success:`, data);
            })
            .catch(err => {
                // console.error(`[AoTMapLoader] Function control error:`, err);
            });
            return;
        }

        // Default Output logic
        const payload = { state: state, channel: channel };
        fetch(`/api/outputs/${baseId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/vnd.aot.v1+json',
                'Accept': 'application/vnd.aot.v1+json'
            },
            body: JSON.stringify(payload)
        })
            .then(res => {
                if (!res.ok) {
                    // If not found in outputs, it might be a function. 
                    // Functional control via routes_function /function_submit might be needed
                    // but that requires a form-encoded payload.
                    // For now, we assume simple output control as requested.
                    // console.warn(`[AoTMapLoader] Control failed for ${deviceId}`, res.status);
                }
                return res.json();
            })
            .then(data => {
                // console.log(`[AoTMapLoader] Control response for ${deviceId}:`, data);
                // Optionally trigger a global refresh or wait for polling
            })
            .catch(err => { /* console.error(`[AoTMapLoader] Control error:`, err); */ });
    },

    /**
     * commandActuator: control a 3-way actuator output (Open/Stop/Close/goto).
     * Maps logical actions to the /api/outputs/<id> POST payload:
     *   - 'open'  -> position: 100
     *   - 'close' -> position: 0
     *   - 'stop'  -> state: false
     *   - 'goto'  -> position: <value 0..100>
     * Also primes _pending_command on the marker (10s local override) so polled
     * server state cannot snap the UI back before the command takes effect.
     *
     * @param {string} deviceId
     * @param {string} action one of 'open' | 'close' | 'stop' | 'goto'
     * @param {number|null} value target position (0-100) when action === 'goto' (otherwise ignored)
     * @param {number|string} channel
     * @param {string} widgetUniqueId widget instance id (used to locate marker for pending guard)
     */
    commandActuator: function (deviceId, action, value, channel = 0, widgetUniqueId = null) {
        if (channel === 'undefined' || channel === 'null' || !channel) channel = 0;

        let baseId = deviceId;
        if (deviceId && deviceId.indexOf('::') !== -1) {
            baseId = deviceId.split('::')[0];
        }

        const payload = { channel: channel };
        let optimisticPos = null;
        if (action === 'open') {
            payload.position = 100;
            optimisticPos = 100;
        } else if (action === 'close') {
            payload.position = 0;
            optimisticPos = 0;
        } else if (action === 'stop') {
            payload.state = false;
        } else if (action === 'goto') {
            const v = parseFloat(value);
            if (isNaN(v)) return;
            payload.position = Math.max(0, Math.min(100, v));
            optimisticPos = payload.position;
        } else {
            return;
        }

        try {
            if (widgetUniqueId && window.AoTMapApp && window.AoTMapApp[widgetUniqueId]) {
                const m = window.AoTMapApp[widgetUniqueId].deviceMarkers[deviceId];
                if (m) {
                    m.options._pending_command = Date.now();
                    if (optimisticPos !== null) {
                        m.options.position_pct = optimisticPos;
                    }
                    if (action === 'stop') {
                        m.options.is_active = false;
                    } else if (optimisticPos !== null) {
                        m.options.is_active = (optimisticPos > 0);
                        m.options.last_status_change = m.options.is_active ? Math.floor(Date.now() / 1000) : null;
                    }
                }
            }
        } catch (e) { /* noop */ }

        fetch(`/api/outputs/${baseId}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/vnd.aot.v1+json',
                'Accept': 'application/vnd.aot.v1+json'
            },
            body: JSON.stringify(payload)
        })
            .then(res => res.json())
            .catch(() => {});
    },

    /**
     * Formats duration in seconds to HH:MM:SS
     */
    formatDuration: function (seconds) {
        const h = Math.floor(seconds / 3600);
        const m = Math.floor((seconds % 3600) / 60);
        const s = Math.floor(seconds % 60);
        return [h, m, s].map(v => v < 10 ? "0" + v : v).join(":");
    },

    /**
     * Updates duration displays on popups
     * Called by polling logic in widgets
     */
    updateDurations: function (deviceMarkers) {
        if (!window.AoTStopwatchManager) return;
        
        Object.keys(deviceMarkers).forEach(id => {
            const marker = deviceMarkers[id];
            const durEl = document.getElementById(`dur-${id}`);
            if (durEl) {
                const channel = marker.options.channel_id || 0;
                const isActive = !!marker.options.is_active;
                const lastStatusChange = marker.options.last_status_change || null;
                
                // [Runtime Service] 항상 등록하여 상태(Active/Idle)를 매니저에 동기화
                window.AoTStopwatchManager.register(id, channel, isActive, lastStatusChange, durEl);
            }
        });
    },

    /**
     * =====================================================
     * VECTOR MAP: MapLibre GL 기반 벡터 맵 초기화
     * =====================================================
     * Leaflet 맵 위에 MapLibre GL 벡터 레이어를 오버레이합니다.
     * 기존 Leaflet 레이어와 호환됩니다.
     * 
     * @param {L.Map} leafletMap - 기존 Leaflet 맵 인스턴스
     * @param {Object} options - 벡터 맵 옵션
     * @param {string} [options.style] - MapLibre 스타일 URL
     * @param {Array} [options.center] - [lng, lat] 기본 중심
     * @param {number} [options.zoom] - 줌 레벨
     * @returns {maplibregl.Map|null} MapLibre 맵 인스턴스
     */
    initVectorMap: function(leafletMap, options = {}) {
        console.log('[AoTMapLoader] initVectorMap() called');
        
        // MapLibre GL 확인
        if (typeof maplibregl === 'undefined') {
            console.error('[AoTMapLoader] MapLibre GL not loaded. Vector map unavailable.');
            return null;
        }
        
        // Leaflet-MapLibre-GL 플러그인 확인
        if (typeof L.MapLibreGL === 'undefined') {
            console.error('[AoTMapLoader] Leaflet-MapLibre-GL plugin not loaded.');
            return null;
        }
        
        // MapLibre 벡터 맵 컨테이너 생성
        const container = leafletMap.getContainer();
        const rect = container.getBoundingClientRect();
        
        // MapLibre GL 맵 생성
        const maplibreOptions = {
            container: {
                create: function() {
                    const div = document.createElement('div');
                    div.style.position = 'absolute';
                    div.style.top = '0';
                    div.style.left = '0';
                    div.style.width = '100%';
                    div.style.height = '100%';
                    div.style.zIndex = '1'; // Leaflet 타일 아래
                    div.className = 'maplibre-vector-layer';
                    container.appendChild(div);
                    return div;
                }
            },
            // MapTiler API v2: /maps/ not /styles/
        style: options.style || (options.apiKey 
            ? `https://api.maptiler.com/maps/streets/style.json?key=${options.apiKey}` 
            : 'https://demotiles.maplibre.org/style.json'),
            center: options.center || [126.978, 37.5665],
            zoom: options.zoom || 12,
            attributionControl: false,
            interactive: false // Leaflet 이벤트 방해 방지
        };
        
        let maplibreMap = null;
        
        try {
            // MapLibre 맵 생성 (임시 컨테이너)
            const tempContainer = document.createElement('div');
            tempContainer.style.position = 'absolute';
            tempContainer.style.top = '0';
            tempContainer.style.left = '0';
            tempContainer.style.width = '100%';
            tempContainer.style.height = '100%';
            tempContainer.style.zIndex = '1';
            tempContainer.className = 'maplibre-vector-layer';
            container.appendChild(tempContainer);
            
            maplibreMap = new maplibregl.Map({
                container: tempContainer,
                style: maplibreOptions.style,
                center: maplibreOptions.center,
                zoom: maplibreOptions.zoom,
                attributionControl: false,
                interactive: false
            });
            
            // MapLibre 맵의 크기를 Leaflet에 동기화
            maplibreMap.on('load', function() {
                // Leaflet과 MapLibre 좌표 동기화
                const syncMap = function() {
                    const center = leafletMap.getCenter();
                    const zoom = leafletMap.getZoom();
                    maplibreMap.jumpTo({
                        center: [center.lng, center.lat],
                        zoom: zoom,
                        bearing: leafletMap.getBearing(),
                        pitch: leafletMap.getPitch()
                    });
                };
                
                // Leaflet 이벤트에 동기화
                leafletMap.on('move', syncMap);
                leafletMap.on('zoom', syncMap);
                leafletMap.on('resize', syncMap);
                
                // 초기 동기화
                syncMap();
                
                console.log('[AoTMapLoader] MapLibre map synced with Leaflet');
            });
            
            // VectorLayerManager 초기화 (생성+바인딩 한번에)
            if (window.AoTVectorLayerManager && window.AoTVectorLayerManager.bind) {
                const vlm = window.AoTVectorLayerManager.bind(maplibreMap);
                console.log('[AoTMapLoader] VectorLayerManager initialized');
            }
            
            // RasterBridge 초기화
            if (window.AoTRasterBridge) {
                window.AoTRasterBridge.create(maplibreMap);
                console.log('[AoTMapLoader] RasterBridge initialized');
            }
            
            // maplibreMap을 Leaflet 맵에 저장
            leafletMap.maplibreMap = maplibreMap;
            
            console.log('[AoTMapLoader] Vector map initialized successfully');
            return maplibreMap;
            
        } catch (error) {
            console.error('[AoTMapLoader] Vector map initialization failed:', error);
            return null;
        }
    },
    
    /**
     * =====================================================
     * VECTOR SOURCE: 벡터 소스 추가
     * =====================================================
     * MapLibre 맵에 벡터 타일 소스를 추가합니다.
     * 
     * @param {string} sourceId - 소스 ID
     * @param {Object} options - 소스 옵션
     * @param {string[]} options.tiles - 벡터 타일 URL 배열
     * @param {string} [options.type='vector'] - 소스 타입
     * @param {number} [options.minzoom=0] - 최소 줌
     * @param {number} [options.maxzoom=14] - 최대 줌
     * @returns {boolean} 성공 여부
     */
    addVectorSource: function(sourceId, options) {
        if (window.AoTVectorLayerManager) {
            return window.AoTVectorLayerManager.addVectorSource(sourceId, options);
        }
        console.error('[AoTMapLoader] VectorLayerManager not available');
        return false;
    },
    
    /**
     * =====================================================
     * VECTOR LAYER: 벡터 레이어 추가
     * =====================================================
     * MapLibre 맵에 벡터 레이어를 추가합니다.
     * 
     * @param {string} layerId - 레이어 ID
     * @param {string} sourceId - 소스 ID
     * @param {Object} style - 레이어 스타일
     * @returns {boolean} 성공 여부
     */
    addVectorLayer: function(layerId, sourceId, style) {
        if (window.AoTVectorLayerManager) {
            return window.AoTVectorLayerManager.addStyledLayer(layerId, sourceId, style);
        }
        console.error('[AoTMapLoader] VectorLayerManager not available');
        return false;
    }
};

/**
 * =====================================================
 * GIS INPUT PREVIEW: 설정 미리보기
 * =====================================================
 * GIS Input 설정 페이지에서 레이어 미리보기를 제공합니다.
 * 객체/함수 형태로 정의하여 AoTGeoInputPreview.load(uniqueId) 호출 가능
 */
var AoTGeoInputPreview = function() {
    return true;
};

/**
 * GIS Input 설정 변경 시 유효성 검사 및 미리보기
 * @param {string} uniqueId - 입력 고유 ID
 */
AoTGeoInputPreview.load = function(uniqueId) {
    console.log('[AoTGeoInputPreview] Load requested for:', uniqueId);
    
    // 그리드 스택 컨테이너에서 해당 입력 항목 찾기
    var inputContainer = document.getElementById('gridstack_input_' + uniqueId);
    if (!inputContainer) {
        console.warn('[AoTGeoInputPreview] Input container not found:', uniqueId);
        return false;
    }
    
    // 입력 유형 결정 (data-input-type 속성 또는 input_name에서 추출)
    var inputType = inputContainer.getAttribute('data-input-type') || '';
    var inputName = inputContainer.getAttribute('data-input-name') || '';
    
    console.log('[AoTGeoInputPreview] Input info:', { uniqueId, inputType, inputName });
    
    // MapTiler Vector인 경우 API Key 확인
    if (inputName === 'MapTiler Vector' || inputName.toLowerCase().includes('maptiler')) {
        var apiKeyInput = inputContainer.querySelector('[name*="api_key"], [name*="apikey"], [name*="apiKey"]');
        if (apiKeyInput && !apiKeyInput.value.trim()) {
            console.warn('[AoTGeoInputPreview] MapTiler API Key is empty');
            // API Key가 비어있어도 저장은 계속 진행 (저장 버튼은 별도 처리)
        }
    }
    
    // RainViewer인 경우 API 상태 확인
    if (inputName === 'RainViewer Radar' || inputName.toLowerCase().includes('rainviewer')) {
        console.info('[AoTGeoInputPreview] RainViewer API may be discontinued. Checking configuration...');
    }
    
    console.log('[AoTGeoInputPreview] Validation passed for:', uniqueId);
    return true;
};

}
