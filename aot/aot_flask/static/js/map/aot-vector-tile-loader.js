/**
 * aot-vector-tile-loader.js
 * Vector Tile Support for AoT Map System
 * Provides MapLibre-GL integration with Leaflet
 * 
 * @requires maplibre-gl (loaded from CDN or bundled)
 */

(function(window) {
    'use strict';

    // Ensure AoT namespace exists
    window.AoTMapLoader = window.AoTMapLoader || {};

    /**
     * Vector Tile Layer Handler
     * Wraps MapLibre-GL as a Leaflet-compatible layer
     */
    var VectorTileLayer = L.Layer.extend({
        options: {
            styleUrl: '',
            apiKey: '',
            language: 'auto',
            maxZoom: 22,
            maxNativeZoom: 14,
            attribution: ''
        },

        initialize: function(options) {
            L.setOptions(this, options);
            this._map = null;
            this._glMap = null;
            this._container = null;
            this._loaded = false;
        },

        onAdd: function(map) {
            this._map = map;
            
            // Create container for MapLibre canvas
            this._container = L.DomUtil.create('div', 'leaflet-maplibre-layer');
            this._container.style.position = 'absolute';
            this._container.style.top = '0';
            this._container.style.left = '0';
            this._container.style.width = '100%';
            this._container.style.height = '100%';
            this._container.style.zIndex = '1'; // Below Leaflet markers
            
            map.getPanes().tilePane.appendChild(this._container);

            // Initialize MapLibre
            this._initMapLibre();

            // Sync view with Leaflet
            this._syncView();
            map.on('move', this._syncView, this);
            map.on('zoom', this._syncView, this);
            map.on('resize', this._syncView, this);
        },

        onRemove: function(map) {
            // Clean up MapLibre
            if (this._glMap) {
                this._glMap.remove();
                this._glMap = null;
            }

            // Remove container
            if (this._container && this._container.parentNode) {
                this._container.parentNode.removeChild(this._container);
            }

            // Remove listeners
            map.off('move', this._syncView, this);
            map.off('zoom', this._syncView, this);
            map.off('resize', this._syncView, this);
        },

        _initMapLibre: function() {
            var self = this;
            
            // Check if maplibre-gl is available
            if (typeof maplibregl === 'undefined') {
                console.error('[AoT VectorTiles] MapLibre-GL not loaded');
                return;
            }

            // Get container size from parent
            var size = this._map.getSize();

            // Create MapLibre map
            this._glMap = new maplibregl.Map({
                container: this._container,
                style: this.options.styleUrl + (this.options.apiKey ? '?key=' + this.options.apiKey : ''),
                crs: L.CRS.EPSG3857,
                interactive: false,
                attributionControl: false,
                fadeDuration: 0,
                crossSourceCollisions: false,
                collectResourceTiming: false,
                maxzoom: this.options.maxZoom,
                minzoom: 0
            });

            // Set language if supported
            if (this.options.language && this.options.language !== 'auto') {
                this._glMap.on('load', function() {
                    self._glMap.setLayoutProperty('place_name', 'text-field', [
                        'get', 'name_' + self.options.language
                    ]);
                    self._glMap.setLayoutProperty('road_label', 'text-field', [
                        'get', 'name_' + self.options.language
                    ]);
                });
            }

            // Mark as loaded
            this._glMap.on('load', function() {
                self._loaded = true;
                self.fire('load');
            });

            // Handle errors
            this._glMap.on('error', function(e) {
                console.warn('[AoT VectorTiles] Error:', e.error);
            });
        },

        _syncView: function() {
            if (!this._glMap || !this._map) return;

            var center = this._map.getCenter();
            var zoom = this._map.getZoom();

            // MapLibre uses lng/lat order
            this._glMap.jumpTo({
                center: [center.lng, center.lat],
                zoom: zoom,
                bearing: 0,
                pitch: 0
            });
        },

        getGlMap: function() {
            return this._glMap;
        },

        setOpacity: function(opacity) {
            if (this._container) {
                this._container.style.opacity = opacity;
            }
        }
    });

    // Factory function
    L.vectorTileLayer = function(styleUrl, options) {
        return new VectorTileLayer(L.Util.extend({
            styleUrl: styleUrl
        }, options));
    };

    /**
     * Create vector tile layer from AoT config
     */
    window.AoTMapLoader.createVectorTileLayer = function(config) {
        var options = {
            styleUrl: config.url || config.style,
            apiKey: config.api_key || config.options?.apiKey || '',
            language: config.language || config.options?.language || 'auto',
            maxZoom: config.options?.maxZoom || 22,
            maxNativeZoom: config.options?.maxNativeZoom || 14,
            attribution: config.attribution || ''
        };

        var layer = L.vectorTileLayer(options.styleUrl, options);
        
        // Attach metadata for persistence
        layer.aot_id = config.id;
        layer.aot_base_id = config.base_id || config.id;
        layer.name = config.name;
        layer.aot_legend = config.legend;
        layer.aot_layer_type = 'vector';

        return layer;
    };

    /**
     * Load MapLibre-GL from CDN if not already loaded
     */
    window.AoTMapLoader.ensureMapLibre = function() {
        return new Promise(function(resolve, reject) {
            if (typeof maplibregl !== 'undefined') {
                resolve();
                return;
            }

            // Load CSS
            var css = document.createElement('link');
            css.rel = 'stylesheet';
            css.href = 'https://unpkg.com/maplibre-gl@4.1.1/dist/maplibre-gl.css';
            document.head.appendChild(css);

            // Load JS
            var script = document.createElement('script');
            script.src = 'https://unpkg.com/maplibre-gl@4.1.1/dist/maplibre-gl.js';
            script.onload = function() {
                console.log('[AoT] MapLibre-GL loaded');
                resolve();
            };
            script.onerror = reject;
            document.head.appendChild(script);
        });
    };

    // Export for external use
    window.AoTMapLoader.VectorTileLayer = VectorTileLayer;

})(window);
