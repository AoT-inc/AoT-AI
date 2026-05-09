/**
 * aot-multi-source-manager.js
 * Multi-Source Map Manager for AoT Map System
 * Manages multiple map sources (MapTiler, VWorld, OSM, Google) with seamless switching
 * 
 * @version 1.0.0
 * @requires Leaflet or MapLibre-GL
 * @namespace AoTMultiSourceManager
 */

(function(window) {
    'use strict';

    /**
     * Supported map source types
     * @readonly
     * @enum {string}
     */
    var SOURCE_TYPES = {
        MAPTILER_VECTOR: 'maptiler_vector',
        MAPTILER_RASTER: 'maptiler_raster',
        VWORLD_WMTS: 'vworld_wmts',
        VWORLD_WMS: 'vworld_wms',
        OSM_RASTER: 'osm_raster',
        OSM_VECTOR: 'osm_vector',
        GOOGLE_MAPS: 'google_maps'
    };

    /**
     * Default source configurations
     * @private
     */
    var DEFAULT_SOURCES = {
        maptiler_vector: {
            type: SOURCE_TYPES.MAPTILER_VECTOR,
            name: 'MapTiler Vector',
            attribution: '© MapTiler © OpenStreetMap contributors',
            style: 'https://api.maptiler.com/tiles/v3-free/style.json',
            tileUrl: 'https://api.maptiler.com/tiles/v3/{z}/{x}/{y}.pbf',
            minZoom: 0,
            maxZoom: 18,
            requiresApiKey: true
        },
        maptiler_raster: {
            type: SOURCE_TYPES.MAPTILER_RASTER,
            name: 'MapTiler Raster',
            attribution: '© MapTiler © OpenStreetMap contributors',
            tileUrl: 'https://api.maptiler.com/tiles/v3/{z}/{x}/{y}.png',
            minZoom: 0,
            maxZoom: 18,
            requiresApiKey: true
        },
        vworld_wmts: {
            type: SOURCE_TYPES.VWORLD_WMTS,
            name: 'VWorld WMTS',
            attribution: '© VWorld',
            tileUrl: 'http://api.vworld.kr/req/wmts/1.0.0/{apiKey}/{layer}/{z}/{y}/{x}',
            layers: {
                Base: 'Base',
                Satellite: 'Satellite',
                Hybrid: 'Hybrid',
                'Base+Traffic': 'Traffic',
                'Base+Address': 'Address'
            },
            minZoom: 1,
            maxZoom: 19,
            requiresApiKey: true,
            apiKeyParam: 'apiKey'
        },
        vworld_wms: {
            type: SOURCE_TYPES.VWORLD_WMS,
            name: 'VWorld WMS',
            attribution: '© VWorld',
            wmsUrl: 'http://api.vworld.kr/req/wms',
            layers: ['Base', 'Satellite'],
            minZoom: 1,
            maxZoom: 19,
            requiresApiKey: true
        },
        osm_raster: {
            type: SOURCE_TYPES.OSM_RASTER,
            name: 'OpenStreetMap',
            attribution: '© OpenStreetMap contributors',
            tileUrl: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
            minZoom: 0,
            maxZoom: 19,
            requiresApiKey: false
        },
        osm_vector: {
            type: SOURCE_TYPES.OSM_VECTOR,
            name: 'OSM Vector',
            attribution: '© OpenStreetMap contributors',
            tileUrl: 'https://tile.openstreetmap.fr/hot/{z}/{x}/{y}.pbf',
            minZoom: 0,
            maxZoom: 18,
            requiresApiKey: false
        },
        google_maps: {
            type: SOURCE_TYPES.GOOGLE_MAPS,
            name: 'Google Maps',
            attribution: '© Google',
            minZoom: 0,
            maxZoom: 20,
            requiresApiKey: true,
            layers: ['roadmap', 'satellite', 'terrain', 'hybrid']
        }
    };

    /**
     * AoTMultiSourceManager
     * Manages multiple map sources with switching capabilities
     * 
     * @param {Object} map - Leaflet or MapLibre map instance
     * @param {Object} options - Configuration options
     * @param {string} [options.defaultSource='osm_raster'] - Default source ID
     * @param {Object} [options.apiKeys] - API keys for services
     * @param {boolean} [options.enableMultiLayer=true] - Allow multiple sources displayed simultaneously
     * @param {boolean} [options.showControls=true] - Show source switching controls
     * @param {string} [options.containerId='map'] - Map container ID
     */
    var AoTMultiSourceManager = function(map, options) {
        this.map = map;
        this.options = Object.assign({}, this._getDefaultOptions(), options);

        // Source registry
        this.sources = new Map();
        this.activeSources = new Set();
        this.sourceLayers = new Map();

        // Event handlers
        this.eventHandlers = {
            sourceChange: [],
            sourceAdd: [],
            sourceRemove: []
        };

        // Track if using Leaflet or MapLibre
        this._isLeaflet = (typeof L !== 'undefined' && map instanceof L.Map);
        this._isMapLibre = (typeof maplibregl !== 'undefined' && map instanceof maplibregl.Map);

        // Initialize default sources
        this._initializeDefaultSources();

        // Bind methods
        this._onSourceChange = this._onSourceChange.bind(this);
    };

    /**
     * Default configuration options
     * @private
     */
    AoTMultiSourceManager.prototype._getDefaultOptions = function() {
        return {
            defaultSource: 'osm_raster',
            apiKeys: {},
            enableMultiLayer: true,
            showControls: false,
            containerId: 'map'
        };
    };

    /**
     * Initialize default source configurations
     * @private
     */
    AoTMultiSourceManager.prototype._initializeDefaultSources = function() {
        var self = this;
        Object.keys(DEFAULT_SOURCES).forEach(function(key) {
            self.sources.set(key, Object.assign({}, DEFAULT_SOURCES[key]));
        });
    };

    // ========================================
    // Source Registration
    // ========================================

    /**
     * Register a new map source
     * @param {string} id - Unique source identifier
     * @param {Object} config - Source configuration
     * @param {string} config.type - Source type (from SOURCE_TYPES)
     * @param {string} config.name - Display name
     * @param {string} [config.tileUrl] - Tile URL template
     * @param {string} [config.style] - Style URL (for MapLibre)
     * @param {string} [config.wmsUrl] - WMS URL
     * @param {string} [config.attribution] - Attribution text
     * @param {Object} [config.options] - Additional options
     * @returns {AoTMultiSourceManager}
     */
    AoTMultiSourceManager.prototype.registerSource = function(id, config) {
        if (!id || !config || !config.type) {
            console.error('[AoTMultiSourceManager] Invalid source configuration:', id);
            return this;
        }

        if (this.sources.has(id)) {
            console.warn('[AoTMultiSourceManager] Source already exists:', id);
            return this;
        }

        var sourceConfig = Object.assign({
            id: id,
            registeredAt: new Date().toISOString()
        }, config);

        this.sources.set(id, sourceConfig);
        console.log('[AoTMultiSourceManager] Source registered:', id);

        this._emit('sourceAdd', { sourceId: id, config: sourceConfig });

        return this;
    };

    /**
     * Unregister a map source
     * @param {string} id - Source identifier
     * @returns {AoTMultiSourceManager}
     */
    AoTMultiSourceManager.prototype.unregisterSource = function(id) {
        if (!this.sources.has(id)) {
            console.warn('[AoTMultiSourceManager] Source not found:', id);
            return this;
        }

        // Remove from map if active
        if (this.activeSources.has(id)) {
            this._removeSourceLayer(id);
            this.activeSources.delete(id);
        }

        this.sources.delete(id);
        console.log('[AoTMultiSourceManager] Source unregistered:', id);

        this._emit('sourceRemove', { sourceId: id });

        return this;
    };

    /**
     * Get registered source configuration
     * @param {string} id - Source identifier
     * @returns {Object|null}
     */
    AoTMultiSourceManager.prototype.getSource = function(id) {
        return this.sources.get(id) || null;
    };

    /**
     * Get all registered sources
     * @returns {Array}
     */
    AoTMultiSourceManager.prototype.getAllSources = function() {
        return Array.from(this.sources.keys()).map(function(id) {
            return this.sources.get(id);
        }, this);
    };

    // ========================================
    // Source Switching
    // ========================================

    /**
     * Switch to a different map source
     * @param {string} id - Source identifier
     * @param {Object} [options] - Switch options
     * @param {boolean} [options.preserveView=false] - Preserve current map view
     * @param {boolean} [options.addToOverlay=false] - Add as overlay instead of replacing
     * @returns {Promise}
     */
    AoTMultiSourceManager.prototype.switchSource = function(id, options) {
        options = options || {};
        var self = this;

        return new Promise(function(resolve, reject) {
            var source = self.sources.get(id);
            if (!source) {
                console.error('[AoTMultiSourceManager] Source not found:', id);
                reject(new Error('Source not found: ' + id));
                return;
            }

            // Get current view if preserving
            var view = null;
            if (options.preserveView) {
                view = self._getCurrentView();
            }

            try {
                // If not multi-layer mode, remove all active sources first
                if (!self.options.enableMultiLayer && !options.addToOverlay) {
                    self._removeAllActiveSources();
                }

                // Add the new source
                self._addSourceLayer(id, source, options).then(function() {
                    self.activeSources.add(id);

                    // Restore view if preserved
                    if (view) {
                        self._restoreView(view);
                    }

                    console.log('[AoTMultiSourceManager] Switched to source:', id);
                    self._emit('sourceChange', {
                        sourceId: id,
                        activeSources: Array.from(self.activeSources)
                    });

                    resolve();
                }).catch(function(err) {
                    console.error('[AoTMultiSourceManager] Failed to switch source:', err);
                    reject(err);
                });

            } catch (e) {
                console.error('[AoTMultiSourceManager] Error switching source:', e);
                reject(e);
            }
        });
    };

    /**
     * Add source as overlay (multiple layers)
     * @param {string} id - Source identifier
     * @param {Object} [options] - Layer options
     * @returns {Promise}
     */
    AoTMultiSourceManager.prototype.addSourceOverlay = function(id, options) {
        options = options || {};
        options.addToOverlay = true;

        return this.switchSource(id, options);
    };

    /**
     * Remove a source from overlay
     * @param {string} id - Source identifier
     * @returns {AoTMultiSourceManager}
     */
    AoTMultiSourceManager.prototype.removeSourceOverlay = function(id) {
        if (!this.activeSources.has(id)) {
            return this;
        }

        this._removeSourceLayer(id);
        this.activeSources.delete(id);

        this._emit('sourceChange', {
            sourceId: null,
            activeSources: Array.from(self.activeSources)
        });

        return this;
    };

    /**
     * Get currently active sources
     * @returns {Array}
     */
    AoTMultiSourceManager.prototype.getActiveSources = function() {
        return Array.from(this.activeSources);
    };

    /**
     * Check if a source is active
     * @param {string} id - Source identifier
     * @returns {boolean}
     */
    AoTMultiSourceManager.prototype.isSourceActive = function(id) {
        return this.activeSources.has(id);
    };

    // ========================================
    // Source Layer Management
    // ========================================

    /**
     * Add source layer to map
     * @private
     */
    AoTMultiSourceManager.prototype._addSourceLayer = function(id, source, options) {
        var self = this;
        options = options || {};

        return new Promise(function(resolve, reject) {
            try {
                var layer;
                var layerId = 'aot-source-' + id;

                // Handle different source types
                switch (source.type) {
                    case SOURCE_TYPES.MAPTILER_VECTOR:
                        layer = self._createMapTilerVectorLayer(source, layerId);
                        break;
                    case SOURCE_TYPES.MAPTILER_RASTER:
                        layer = self._createMapTilerRasterLayer(source, layerId);
                        break;
                    case SOURCE_TYPES.VWORLD_WMTS:
                        layer = self._createVWorldWMTLayer(source, layerId);
                        break;
                    case SOURCE_TYPES.VWORLD_WMS:
                        layer = self._createVWorldWMSLayer(source, layerId);
                        break;
                    case SOURCE_TYPES.OSM_RASTER:
                        layer = self._createOSMRasterLayer(source, layerId);
                        break;
                    case SOURCE_TYPES.OSM_VECTOR:
                        layer = self._createOSMVectorLayer(source, layerId);
                        break;
                    case SOURCE_TYPES.GOOGLE_MAPS:
                        layer = self._createGoogleMapsLayer(source, layerId);
                        break;
                    default:
                        console.warn('[AoTMultiSourceManager] Unknown source type:', source.type);
                        resolve();
                        return;
                }

                if (layer) {
                    self.sourceLayers.set(id, layer);
                    // For MapLibre, need to wait for style load
                    if (self._isMapLibre && source.type === SOURCE_TYPES.MAPTILER_VECTOR) {
                        if (self.map.isStyleLoaded()) {
                            resolve();
                        } else {
                            self.map.once('style.load', resolve);
                        }
                    } else {
                        resolve();
                    }
                } else {
                    resolve();
                }
            } catch (e) {
                reject(e);
            }
        });
    };

    /**
     * Create MapTiler vector layer
     * @private
     */
    AoTMultiSourceManager.prototype._createMapTilerVectorLayer = function(source, layerId) {
        var self = this;
        var apiKey = this.options.apiKeys.maptiler || '';

        if (this._isLeaflet) {
            // For Leaflet, use raster tiles or a custom vector tile layer
            console.warn('[AoTMultiSourceManager] Vector tiles in Leaflet require additional plugins');
            return null;
        }

        if (this._isMapLibre) {
            // MapLibre-GL handles vector tiles natively
            var styleUrl = source.style;
            if (apiKey) {
                styleUrl += (styleUrl.indexOf('?') > -1 ? '&' : '?') + 'key=' + apiKey;
            }

            // Load the style
            this.map.addSource('maptiler-vector', {
                type: 'vector',
                tiles: [source.tileUrl + (apiKey ? '?key=' + apiKey : '')],
                minzoom: source.minZoom,
                maxzoom: source.maxZoom,
                attribution: source.attribution
            });

            // Load style JSON and apply
            fetch(styleUrl)
                .then(function(response) { return response.json(); })
                .then(function(style) {
                    // Replace source in style
                    if (style.sources && style.sources.openmaptiles) {
                        style.sources.openmaptiles.tiles = [source.tileUrl + (apiKey ? '?key=' + apiKey : '')];
                    }
                    self.map.setStyle(style);
                })
                .catch(function(err) {
                    console.error('[AoTMultiSourceManager] Failed to load MapTiler style:', err);
                });

            return { id: layerId, type: 'vector' };
        }

        return null;
    };

    /**
     * Create MapTiler raster layer
     * @private
     */
    AoTMultiSourceManager.prototype._createMapTilerRasterLayer = function(source, layerId) {
        var apiKey = this.options.apiKeys.maptiler || '';
        var tileUrl = source.tileUrl + (apiKey ? '?key=' + apiKey : '');

        if (this._isLeaflet) {
            return L.tileLayer(tileUrl, {
                id: layerId,
                attribution: source.attribution,
                maxZoom: source.maxZoom,
                minZoom: source.minZoom
            }).addTo(this.map);
        }

        if (this._isMapLibre) {
            this.map.addSource(layerId, {
                type: 'raster',
                tiles: [tileUrl],
                tileSize: 256,
                attribution: source.attribution
            });

            this.map.addLayer({
                id: layerId,
                type: 'raster',
                source: layerId
            });

            return { id: layerId, type: 'raster' };
        }

        return null;
    };

    /**
     * Create VWorld WMTS layer
     * @private
     */
    AoTMultiSourceManager.prototype._createVWorldWMTLayer = function(source, layerId) {
        var self = this;
        var apiKey = this.options.apiKeys.vworld || '';

        if (!apiKey) {
            console.warn('[AoTMultiSourceManager] VWorld API key required');
            return null;
        }

        var layer = source.layers.Base || 'Base';
        var tileUrl = source.tileUrl
            .replace('{apiKey}', apiKey)
            .replace('{layer}', layer);

        if (this._isLeaflet) {
            // Use WMTS plugin or custom URL
            if (typeof L.TileLayer.WMTS !== 'undefined') {
                return L.tileLayer.wmts(tileUrl, {
                    layer: layer,
                    style: 'default',
                    tilematrixset: 'GoogleMapsCompatible',
                    format: 'image/png',
                    attribution: source.attribution
                }).addTo(this.map);
            } else {
                // Fallback to modified URL pattern
                return L.tileLayer(tileUrl.replace('WMTS', 'tile'), {
                    id: layerId,
                    attribution: source.attribution,
                    maxZoom: source.maxZoom
                }).addTo(this.map);
            }
        }

        if (this._isMapLibre) {
            this.map.addSource(layerId, {
                type: 'raster',
                tiles: [tileUrl],
                tileSize: 256,
                attribution: source.attribution
            });

            this.map.addLayer({
                id: layerId,
                type: 'raster',
                source: layerId
            });

            return { id: layerId, type: 'raster' };
        }

        return null;
    };

    /**
     * Create VWorld WMS layer
     * @private
     */
    AoTMultiSourceManager.prototype._createVWorldWMSLayer = function(source, layerId) {
        var apiKey = this.options.apiKeys.vworld || '';

        if (!apiKey) {
            console.warn('[AoTMultiSourceManager] VWorld API key required');
            return null;
        }

        var wmsUrl = source.wmsUrl + '?service=WMS&version=1.3.0&request=GetMap' +
            '&layers=' + (source.layers || ['Base']).join(',') +
            '&crs=EPSG:3857' +
            '&apiKey=' + apiKey +
            '&format=image/png' +
            '&width=256&height=256' +
            '&bbox={bbox-epsg-3857}';

        if (this._isLeaflet) {
            return L.tileLayer.wms(wmsUrl, {
                id: layerId,
                layers: source.layers ? source.layers[0] : 'Base',
                format: 'image/png',
                attribution: source.attribution,
                transparent: true
            }).addTo(this.map);
        }

        if (this._isMapLibre) {
            this.map.addSource(layerId, {
                type: 'raster',
                tiles: [wmsUrl],
                tileSize: 256,
                attribution: source.attribution
            });

            this.map.addLayer({
                id: layerId,
                type: 'raster',
                source: layerId
            });

            return { id: layerId, type: 'raster' };
        }

        return null;
    };

    /**
     * Create OSM raster layer
     * @private
     */
    AoTMultiSourceManager.prototype._createOSMRasterLayer = function(source, layerId) {
        if (this._isLeaflet) {
            return L.tileLayer(source.tileUrl, {
                id: layerId,
                attribution: source.attribution,
                maxZoom: source.maxZoom,
                minZoom: source.minZoom
            }).addTo(this.map);
        }

        if (this._isMapLibre) {
            this.map.addSource(layerId, {
                type: 'raster',
                tiles: [source.tileUrl],
                tileSize: 256,
                attribution: source.attribution
            });

            this.map.addLayer({
                id: layerId,
                type: 'raster',
                source: layerId
            });

            return { id: layerId, type: 'raster' };
        }

        return null;
    };

    /**
     * Create OSM vector layer
     * @private
     */
    AoTMultiSourceManager.prototype._createOSMVectorLayer = function(source, layerId) {
        if (this._isLeaflet) {
            console.warn('[AoTMultiSourceManager] OSM Vector requires MapLibre-GL for full support');
            // Fallback to raster
            return L.tileLayer('https://tile.openstreetmap.fr/hot/{z}/{x}/{y}.png', {
                id: layerId,
                attribution: source.attribution,
                maxZoom: source.maxZoom
            }).addTo(this.map);
        }

        if (this._isMapLibre) {
            this.map.addSource(layerId, {
                type: 'vector',
                tiles: [source.tileUrl],
                minzoom: source.minZoom,
                maxzoom: source.maxZoom,
                attribution: source.attribution
            });

            return { id: layerId, type: 'vector' };
        }

        return null;
    };

    /**
     * Create Google Maps layer
     * @private
     */
    AoTMultiSourceManager.prototype._createGoogleMapsLayer = function(source, layerId) {
        if (this._isLeaflet) {
            // Requires leaflet-googlemutant plugin
            if (typeof L.gridLayer !== 'undefined' && typeof L.gridLayer.googleMutant === 'function') {
                var mapType = source.layers ? source.layers[0] : 'roadmap';
                return L.gridLayer.googleMutant({
                    type: mapType,
                    attribution: source.attribution
                }).addTo(this.map);
            } else {
                console.warn('[AoTMultiSourceManager] Google Maps requires leaflet-googlemutant plugin');
                return null;
            }
        }

        if (this._isMapLibre) {
            console.warn('[AoTMultiSourceManager] Google Maps in MapLibre requires @maplibre/google-mutations');
            return null;
        }

        return null;
    };

    /**
     * Remove source layer from map
     * @private
     */
    AoTMultiSourceManager.prototype._removeSourceLayer = function(id) {
        var layer = this.sourceLayers.get(id);
        if (!layer) return;

        try {
            if (this._isLeaflet && layer.remove) {
                layer.remove();
            }

            if (this._isMapLibre) {
                var layerId = 'aot-source-' + id;
                if (this.map.getLayer(layerId)) {
                    this.map.removeLayer(layerId);
                }
                if (this.map.getSource(layerId)) {
                    this.map.removeSource(layerId);
                }
                // Also try without prefix
                if (this.map.getLayer(id)) {
                    this.map.removeLayer(id);
                }
                if (this.map.getSource(id)) {
                    this.map.removeSource(id);
                }
            }
        } catch (e) {
            console.warn('[AoTMultiSourceManager] Error removing layer:', id, e);
        }

        this.sourceLayers.delete(id);
    };

    /**
     * Remove all active source layers
     * @private
     */
    AoTMultiSourceManager.prototype._removeAllActiveSources = function() {
        var self = this;
        this.activeSources.forEach(function(id) {
            self._removeSourceLayer(id);
        });
        this.activeSources.clear();
    };

    // ========================================
    // View Management
    // ========================================

    /**
     * Get current map view state
     * @private
     */
    AoTMultiSourceManager.prototype._getCurrentView = function() {
        if (this._isLeaflet) {
            var center = this.map.getCenter();
            return {
                center: [center.lat, center.lng],
                zoom: this.map.getZoom(),
                bearing: 0,
                pitch: 0
            };
        }

        if (this._isMapLibre) {
            var center = this.map.getCenter();
            return {
                center: [center.lng, center.lat],
                zoom: this.map.getZoom(),
                bearing: this.map.getBearing(),
                pitch: this.map.getPitch()
            };
        }

        return null;
    };

    /**
     * Restore map view state
     * @private
     */
    AoTMultiSourceManager.prototype._restoreView = function(view) {
        if (!view) return;

        if (this._isLeaflet) {
            this.map.setView(view.center, view.zoom);
        }

        if (this._isMapLibre) {
            this.map.jumpTo({
                center: view.center,
                zoom: view.zoom,
                bearing: view.bearing,
                pitch: view.pitch
            });
        }
    };

    // ========================================
    // Style Settings
    // ========================================

    /**
     * Apply style presets to a source
     * @param {string} sourceId - Source identifier
     * @param {string} stylePreset - Style preset name
     * @returns {AoTMultiSourceManager}
     */
    AoTMultiSourceManager.prototype.applyStylePreset = function(sourceId, stylePreset) {
        var source = this.sources.get(sourceId);
        if (!source) {
            console.warn('[AoTMultiSourceManager] Source not found:', sourceId);
            return this;
        }

        var styles = this._getStylePresets();
        var style = styles[stylePreset];
        if (!style) {
            console.warn('[AoTMultiSourceManager] Style preset not found:', stylePreset);
            return this;
        }

        // Apply style to layer
        var layerId = 'aot-source-' + sourceId;
        if (this._isMapLibre && this.map.getLayer(layerId)) {
            if (style.paint) {
                Object.keys(style.paint).forEach(function(prop) {
                    this.map.setPaintProperty(layerId, prop, style.paint[prop]);
                }, this);
            }
            if (style.layout) {
                Object.keys(style.layout).forEach(function(prop) {
                    this.map.setLayoutProperty(layerId, prop, style.layout[prop]);
                }, this);
            }
        }

        return this;
    };

    /**
     * Get available style presets
     * @private
     */
    AoTMultiSourceManager.prototype._getStylePresets = function() {
        return {
            default: {},
            satellite: {
                paint: {
                    'raster-saturation': 0.5
                }
            },
            dark: {
                paint: {
                    'raster-saturation': -1,
                    'raster-brightness-min': 0.1,
                    'raster-brightness-max': 0.4
                }
            },
            light: {
                paint: {
                    'raster-saturation': -0.5,
                    'raster-brightness-min': 0.6,
                    'raster-brightness-max': 1
                }
            },
            overlay: {
                paint: {
                    'raster-opacity': 0.5
                }
            }
        };
    };

    // ========================================
    // Event Handling
    // ========================================

    /**
     * Register event handler
     * @param {string} event - Event name (sourceChange, sourceAdd, sourceRemove)
     * @param {Function} callback - Callback function
     * @returns {Function} Unsubscribe function
     */
    AoTMultiSourceManager.prototype.on = function(event, callback) {
        if (!this.eventHandlers[event]) {
            this.eventHandlers[event] = [];
        }
        this.eventHandlers[event].push(callback);

        var self = this;
        return function() {
            var idx = self.eventHandlers[event].indexOf(callback);
            if (idx > -1) {
                self.eventHandlers[event].splice(idx, 1);
            }
        };
    };

    /**
     * Emit event to registered handlers
     * @private
     */
    AoTMultiSourceManager.prototype._emit = function(event, data) {
        var handlers = this.eventHandlers[event] || [];
        handlers.forEach(function(handler) {
            try {
                handler(data);
            } catch (e) {
                console.error('[AoTMultiSourceManager] Event handler error:', e);
            }
        });
    };

    /**
     * Handle source change event
     * @private
     */
    AoTMultiSourceManager.prototype._onSourceChange = function(data) {
        this._emit('sourceChange', data);
    };

    // ========================================
    // Control UI
    // ========================================

    /**
     * Create source switching control
     * @param {Object} [options] - Control options
     * @param {string} [options.position='topright'] - Control position
     * @param {string} [options.containerId] - Custom container ID
     * @returns {HTMLElement} Control element
     */
    AoTMultiSourceManager.prototype.createSourceControl = function(options) {
        options = options || {};
        var self = this;

        var control = document.createElement('div');
        control.className = 'aot-source-control leaflet-bar';
        control.innerHTML = '<div class="aot-source-title">지도 소스</div>';

        var sourceList = document.createElement('div');
        sourceList.className = 'aot-source-list';

        this.sources.forEach(function(source, id) {
            var item = document.createElement('div');
            item.className = 'aot-source-item';
            item.dataset.sourceId = id;

            var radio = document.createElement('input');
            radio.type = 'radio';
            radio.name = 'aot-source';
            radio.value = id;
            radio.id = 'aot-source-' + id;
            if (this.activeSources.has(id)) {
                radio.checked = true;
            }

            var label = document.createElement('label');
            label.htmlFor = 'aot-source-' + id;
            label.textContent = source.name;

            item.appendChild(radio);
            item.appendChild(label);
            sourceList.appendChild(item);

            radio.addEventListener('change', function() {
                if (this.checked) {
                    self.switchSource(id, { preserveView: true });
                }
            });
        }, this);

        control.appendChild(sourceList);

        // Add multi-layer toggle
        var multiToggle = document.createElement('div');
        multiToggle.className = 'aot-source-multi';
        multiToggle.innerHTML = '<label><input type="checkbox" id="aot-multi-toggle">' +
            ' 다중 레이어 표시</label>';
        control.appendChild(multiToggle);

        multiToggle.querySelector('input').addEventListener('change', function() {
            self.options.enableMultiLayer = this.checked;
        });

        return control;
    };

    // ========================================
    // Utility Methods
    // ========================================

    /**
     * Set API key for a service
     * @param {string} service - Service name (maptiler, vworld, google)
     * @param {string} apiKey - API key
     * @returns {AoTMultiSourceManager}
     */
    AoTMultiSourceManager.prototype.setApiKey = function(service, apiKey) {
        this.options.apiKeys[service] = apiKey;
        console.log('[AoTMultiSourceManager] API key set for:', service);
        return this;
    };

    /**
     * Get API key for a service
     * @param {string} service - Service name
     * @returns {string|null}
     */
    AoTMultiSourceManager.prototype.getApiKey = function(service) {
        return this.options.apiKeys[service] || null;
    };

    /**
     * Configure a source with custom options
     * @param {string} id - Source identifier
     * @param {Object} config - New configuration
     * @returns {AoTMultiSourceManager}
     */
    AoTMultiSourceManager.prototype.configureSource = function(id, config) {
        var source = this.sources.get(id);
        if (!source) {
            console.warn('[AoTMultiSourceManager] Source not found:', id);
            return this;
        }

        Object.assign(source, config);
        console.log('[AoTMultiSourceManager] Source configured:', id);
        return this;
    };

    /**
     * Clone a source with new configuration
     * @param {string} sourceId - Source to clone
     * @param {string} newId - New source identifier
     * @param {Object} [overrides] - Configuration overrides
     * @returns {AoTMultiSourceManager}
     */
    AoTMultiSourceManager.prototype.cloneSource = function(sourceId, newId, overrides) {
        var source = this.sources.get(sourceId);
        if (!source) {
            console.warn('[AoTMultiSourceManager] Source not found:', sourceId);
            return this;
        }

        var cloned = Object.assign({}, source, overrides || {}, { id: newId });
        this.sources.set(newId, cloned);
        console.log('[AoTMultiSourceManager] Source cloned:', sourceId, '->', newId);
        return this;
    };

    /**
     * Set multi-layer mode
     * @param {boolean} enabled - Enable/disable multi-layer
     * @returns {AoTMultiSourceManager}
     */
    AoTMultiSourceManager.prototype.setMultiLayerMode = function(enabled) {
        this.options.enableMultiLayer = enabled;
        if (!enabled) {
            // Keep only the first active source
            var firstSource = this.activeSources.values().next().value;
            if (firstSource) {
                this._removeAllActiveSources();
                this.activeSources.add(firstSource);
            }
        }
        return this;
    };

    /**
     * Refresh all active sources
     * @returns {AoTMultiSourceManager}
     */
    AoTMultiSourceManager.prototype.refresh = function() {
        var self = this;
        var activeSources = Array.from(this.activeSources);

        this._removeAllActiveSources();

        activeSources.forEach(function(sourceId) {
            var source = self.sources.get(sourceId);
            if (source) {
                self._addSourceLayer(sourceId, source, {}).then(function() {
                    self.activeSources.add(sourceId);
                });
            }
        });

        return this;
    };

    /**
     * Destroy the manager and clean up
     */
    AoTMultiSourceManager.prototype.destroy = function() {
        this._removeAllActiveSources();
        this.sources.clear();
        this.sourceLayers.clear();

        Object.keys(this.eventHandlers).forEach(function(key) {
            this.eventHandlers[key] = [];
        }, this);

        this.map = null;
        console.log('[AoTMultiSourceManager] Manager destroyed');
    };

    // Export to global namespace
    window.AoTMultiSourceManager = AoTMultiSourceManager;
    window.AoTMultiSourceManager.SOURCE_TYPES = SOURCE_TYPES;
    window.AoTMultiSourceManager.DEFAULT_SOURCES = DEFAULT_SOURCES;

})(window);
