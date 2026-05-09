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
            // console.log("[AoT] Emergency Master Shield Activated");
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

        // 2. Create Map
        const map = L.map(containerId, mapOptions);

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
        } else {
            // Fallback if Utils not loaded
            L.control.attribution({ prefix: false, position: 'bottomleft' }).addTo(map);
        }

        // 3. Add Layers (Base Maps & Overlays)
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

                                if (customOptions.overlayDataOnly) {
                                    const dummy = L.layerGroup();
                                    dummy.aot_id = rvLayer.aot_id;
                                    dummy.aot_base_id = rvLayer.aot_base_id;
                                    dummy.name = rvLayer.name;
                                    dummy.aot_legend = rvLayer.aot_legend;
                                    if (rvLayer.options) dummy.options = Object.assign({}, rvLayer.options);
                                    rvLayer = dummy;
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
                    }).catch(e => { 
                         // Silent warning for discontinued services to keep console clean
                         console.info("[AoT] RainViewer Layer skipped: Service discontinued or unreachable."); 
                    });
                return; // Skip sync creation
            }

            // [Fix] Skip invalid URLs with unreplaced placeholders to prevent crash
            if (finalUrl && finalUrl.match(/\{(x|y|z|s|r|q)\}/) === null && finalUrl.match(/\{([a-zA-Z0-9_]+)\}/)) {
                // URL has placeholders OTHER than x,y,z,s,r (e.g. {key}, {style} missing)
                // console.warn("[AoTMapLoader] Skipping layer with unreplaced placeholders:", l.name, finalUrl);
                return;
            }

            if (l.type === 'xyz' && finalUrl) {
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

                if (customOptions.overlayDataOnly && !isBase) {
                    const dummy = L.layerGroup();
                    dummy.aot_id = layerFunc.aot_id;
                    dummy.aot_base_id = layerFunc.aot_base_id;
                    dummy.name = layerFunc.name;
                    dummy.aot_legend = layerFunc.aot_legend;
                    if (layerFunc.aot_channel_id !== undefined) {
                        dummy.aot_channel_id = layerFunc.aot_channel_id;
                    }
                    if (layerFunc.options) dummy.options = Object.assign({}, layerFunc.options);
                    layerFunc = dummy;
                }

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
                        layerFunc.addTo(map);
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

        map._aotOverlayDataOnly = !!customOptions.overlayDataOnly;

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
    }
};

}


// ============================================================
// Vector Map Support (MapLibre-GL)
// ============================================================

/**
 * AoTMapLoader Vector Mode - MapLibre-GL based vector map initialization
 * Provides high-performance vector tile rendering with customizable styles
 */
AoTMapLoader.initVectorMap = function(containerId, mapType = 'default', customOptions = {}) {
    // 1. Validate container
    const container = document.getElementById(containerId);
    if (!container) {
        console.error(`[AoTMapLoader.Vector] Container not found: ${containerId}`);
        return null;
    }

    // 2. Check if maplibre-gl is available
    if (typeof maplibregl === 'undefined') {
        console.error('[AoTMapLoader.Vector] maplibre-gl not loaded. Include maplibre-gl.js first.');
        return null;
    }

    const config = window.AOT_GEO_CONFIG || {};
    const settings = config;

    // Parse configuration
    let defaultLat = parseFloat(settings.default_lat);
    if (isNaN(defaultLat)) defaultLat = 37.5665;

    let defaultLng = parseFloat(settings.default_lng);
    if (isNaN(defaultLng)) defaultLng = 126.9780;

    let defaultZoom = parseFloat(settings.zoom);
    if (isNaN(defaultZoom)) defaultZoom = 12;

    let maxZoom = parseInt(settings.max_zoom);
    if (isNaN(maxZoom)) maxZoom = 22;

    // 3. Find active vector tile source from layers config
    const layers = customOptions.layers !== undefined ? customOptions.layers : (config.layers || []);
    let vectorStyleUrl = null;
    let vectorTileUrl = null;
    let vectorApiKey = null;
    let vectorAttribution = '';

    layers.forEach(l => {
        // Check for vector type layer or maptiler vector provider
        if (l.type === 'vector' || 
            l.layer_type === 'vector' || 
            l.input_library === 'gis_maptiler_vector' ||
            (l.url && l.url.includes('maptiler'))) {
            
            if (!vectorStyleUrl) {
                // Use style.json URL for MapLibre (MapTiler API v2)
                vectorStyleUrl = l.url || l.style || 'https://api.maptiler.com/maps/streets/style.json?key={key}';
                vectorTileUrl = l.tileUrl || l.url;
                vectorApiKey = l.api_key || settings.keys?.maptiler || '';
                vectorAttribution = l.attribution || '&copy; MapTiler &copy; OpenStreetMap';
            }
        }
    });

    // Fallback to default MapTiler style if no vector layer configured
    if (!vectorStyleUrl) {
        vectorApiKey = settings.keys?.maptiler || '';
        if (vectorApiKey) {
            // MapTiler API v2: /maps/ not /styles/
            vectorStyleUrl = `https://api.maptiler.com/maps/streets/style.json?key=${vectorApiKey}`;
        } else {
            // Use OpenMapTiles demo (no API key required)
            vectorStyleUrl = 'https://demotiles.maplibre.org/style.json';
            vectorAttribution = '&copy; OpenStreetMap contributors';
        }
    }

    // Replace {key} placeholder in style URL
    if (vectorApiKey && vectorStyleUrl.includes('{key}')) {
        vectorStyleUrl = vectorStyleUrl.replace('{key}', vectorApiKey);
    }

    console.log('[AoTMapLoader.Vector] Initializing vector map with style:', vectorStyleUrl);

    // 4. Create MapLibre map
    const mapOptions = {
        container: container,
        style: vectorStyleUrl,
        center: [defaultLng, defaultLat], // [lng, lat] for MapLibre
        zoom: defaultZoom,
        maxZoom: maxZoom,
        attributionControl: false,
        antialias: true,
        preserveDrawingBuffer: true
    };

    // Apply preset options based on mapType
    const presets = {
        'geo_setting_map': {
            zoomControl: false,
            scrollWheelZoom: true,
            doubleClickZoom: true,
            dragRotate: false,
            touchZoomRotate: true
        },
        'geo_input_map': {
            zoomControl: true,
            scrollWheelZoom: true,
            doubleClickZoom: true,
            dragRotate: false
        },
        'general_map': {
            zoomControl: true,
            scrollWheelZoom: true,
            dragRotate: false
        },
        'default': {
            zoomControl: true,
            scrollWheelZoom: true
        }
    };

    const presetOptions = presets[mapType] || presets['default'];
    Object.assign(mapOptions, presetOptions, customOptions);

    // Remove Leaflet-specific options if present
    delete mapOptions.layers;

    try {
        // 5. Create MapLibre instance
        const map = new maplibregl.Map(mapOptions);
        
        // Add attribution control (bottom-left position)
        map.addControl(new maplibregl.AttributionControl({
            compact: true
        }), 'bottom-left');

        // Add navigation control (top-right by default)
        if (presetOptions.zoomControl !== false) {
            map.addControl(new maplibregl.NavigationControl({
                showCompass: false,
                showZoom: true
            }), 'top-right');
        }

        // 6. Set up virtual layer registries (for compatibility with Leaflet-style code)
        map.aotBaseMaps = {};
        map.aotOverlayMaps = {};
        map.aotVirtualLayers = [];
        map.aotVectorMode = true; // Flag to indicate vector mode

        // 7. Wait for style to load, then return
        map.on('load', function() {
            console.log('[AoTMapLoader.Vector] Style loaded successfully');
        });

        map.on('error', function(e) {
            console.error('[AoTMapLoader.Vector] Map error:', e);
        });

        // Return in same format as initMap for compatibility
        return {
            map: map,
            baseLayers: map.aotBaseMaps,
            overlays: map.aotOverlayMaps,
            layerControl: null, // Vector mode uses different layer control
            activeLayer: null
        };

    } catch (e) {
        console.error('[AoTMapLoader.Vector] Failed to initialize map:', e);
        return null;
    }
};

// ============================================================
// Vector Layer Management Helpers
// ============================================================

/**
 * Add a GeoJSON layer to the vector map
 * @param {maplibregl.Map} map - MapLibre map instance
 * @param {string} sourceId - Unique source identifier
 * @param {Object} geojson - GeoJSON data
 * @param {Object} options - Layer options (paint, layout, etc.)
 * @returns {Object} - Added layer info
 */
AoTMapLoader.addVectorGeoJSON = function(map, sourceId, geojson, options = {}) {
    if (!map || !map.aotVectorMode) {
        console.warn('[AoTMapLoader.Vector] Invalid vector map instance');
        return null;
    }

    const defaultOptions = {
        type: 'fill',
        color: '#ff7800',
        opacity: 0.6
    };

    const layerOptions = { ...defaultOptions, ...options };

    try {
        // Add source if not exists
        if (!map.getSource(sourceId)) {
            map.addSource(sourceId, {
                type: 'geojson',
                data: geojson
            });
        }

        // Add fill layer
        const fillLayerId = `${sourceId}-fill`;
        if (!map.getLayer(fillLayerId)) {
            map.addLayer({
                id: fillLayerId,
                type: 'fill',
                source: sourceId,
                paint: {
                    'fill-color': layerOptions.color,
                    'fill-opacity': layerOptions.opacity
                },
                filter: ['==', '$type', 'Polygon']
            });
        }

        // Add line layer for outlines
        const lineLayerId = `${sourceId}-line`;
        if (!map.getLayer(lineLayerId)) {
            map.addLayer({
                id: lineLayerId,
                type: 'line',
                source: sourceId,
                paint: {
                    'line-color': layerOptions.color,
                    'line-width': 2
                },
                filter: ['==', '$type', 'Polygon']
            });
        }

        // Add circle layer for points
        const circleLayerId = `${sourceId}-circle`;
        if (!map.getLayer(circleLayerId)) {
            map.addLayer({
                id: circleLayerId,
                type: 'circle',
                source: sourceId,
                paint: {
                    'circle-color': layerOptions.color,
                    'circle-radius': 6,
                    'circle-stroke-width': 2,
                    'circle-stroke-color': '#ffffff'
                },
                filter: ['==', '$type', 'Point']
            });
        }

        console.log(`[AoTMapLoader.Vector] Added GeoJSON layer: ${sourceId}`);
        return { fillLayerId, lineLayerId, circleLayerId, sourceId };

    } catch (e) {
        console.error(`[AoTMapLoader.Vector] Failed to add GeoJSON layer: ${sourceId}`, e);
        return null;
    }
};

/**
 * Add a WMS overlay layer to the vector map
 * @param {maplibregl.Map} map - MapLibre map instance
 * @param {string} layerId - Unique layer identifier
 * @param {string} wmsUrl - WMS service URL
 * @param {Object} options - WMS options (layers, format, etc.)
 */
AoTMapLoader.addVectorWMS = function(map, layerId, wmsUrl, options = {}) {
    if (!map || !map.aotVectorMode) {
        console.warn('[AoTMapLoader.Vector] Invalid vector map instance');
        return null;
    }

    const defaultOptions = {
        layers: options.layers || '',
        format: 'image/png',
        transparent: true,
        opacity: 0.7
    };

    try {
        // For MapLibre, WMS layers are added as raster sources with a custom tile URL
        // MapLibre doesn't natively support WMS, so we create XYZ tiles from WMS
        const wmsParams = new URLSearchParams({
            'SERVICE': 'WMS',
            'VERSION': '1.3.0',
            'REQUEST': 'GetMap',
            'FORMAT': defaultOptions.format,
            'TRANSPARENT': defaultOptions.transparent,
            'LAYERS': options.layers || '',
            'WIDTH': '256',
            'HEIGHT': '256',
            'CRS': 'EPSG:3857',
            'STYLES': options.styles || ''
        });

        // Build tile URL pattern from WMS GetMap
        const tileUrl = wmsUrl.split('?')[0] + '?' + wmsParams.toString()
            .replace(/&/g, '&')
            .replace('{bbox}', '{bbox-epsg-3857}')
            .replace('{width}', '256')
            .replace('{height}', '256');

        // Add raster source
        if (!map.getSource(layerId)) {
            map.addSource(layerId, {
                type: 'raster',
                tiles: [tileUrl],
                tileSize: 256,
                bounds: [-180, -85.0511, 180, 85.0511]
            });
        }

        // Add raster layer
        if (!map.getLayer(layerId)) {
            map.addLayer({
                id: layerId,
                type: 'raster',
                source: layerId,
                paint: {
                    'raster-opacity': defaultOptions.opacity
                }
            });
        }

        console.log(`[AoTMapLoader.Vector] Added WMS layer: ${layerId}`);
        return layerId;

    } catch (e) {
        console.error(`[AoTMapLoader.Vector] Failed to add WMS layer: ${layerId}`, e);
        return null;
    }
};

// ES6 Exports
export { AoTMapLoader };
