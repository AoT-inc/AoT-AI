/**
 * Leaflet-MapLibre-GL Plugin Shim
 * Allows using MapLibre GL layers within Leaflet maps
 * 
 * @version 1.0.0
 */

(function() {
    'use strict';

    // Check if Leaflet is loaded
    if (typeof L === 'undefined') {
        console.error('[Leaflet-MapLibre-GL] Leaflet not loaded');
        return;
    }

    /**
     * L.MapLibreGL - Embed MapLibre GL map as a Leaflet layer
     */
    L.MapLibreGL = L.Layer.extend({
        options: {
            style: 'https://demotiles.maplibre.org/style.json',
            updateInterval: 32,
            accessToken: null,
            interactive: false,
            opts: {}
        },

        initialize: function(options) {
            L.setOptions(this, options);
            this._map = null;
            this._maplibreMap = null;
            this._container = null;
            this._loaded = false;
        },

        onAdd: function(map) {
            this._map = map;
            
            // Create container
            this._container = L.DomUtil.create('div', 'leaflet-maplibre-gl', map._panes.overlayPane);
            this._container.style.position = 'absolute';
            this._container.style.width = '100%';
            this._container.style.height = '100%';
            this._container.style.zIndex = '1'; // Below Leaflet markers

            // Wait for map to be ready
            if (map._loaded) {
                this._initMapLibre();
            } else {
                map.whenReady(this._initMapLibre, this);
            }

            // Sync on move
            map.on('move', this._syncPosition, this);
            map.on('moveend', this._syncPosition, this);
            map.on('resize', this._syncPosition, this);
        },

        onRemove: function(map) {
            // Remove container
            if (this._container && this._container.parentNode) {
                this._container.parentNode.removeChild(this._container);
            }

            // Remove maplibre map
            if (this._maplibreMap) {
                this._maplibreMap.remove();
                this._maplibreMap = null;
            }

            // Remove event listeners
            map.off('move', this._syncPosition, this);
            map.off('moveend', this._syncPosition, this);
            map.off('resize', this._syncPosition, this);

            this._map = null;
        },

        _initMapLibre: function() {
            if (typeof maplibregl === 'undefined') {
                console.error('[Leaflet-MapLibre-GL] MapLibre GL not loaded');
                return;
            }

            var self = this;

            // Create MapLibre map
            this._maplibreMap = new maplibregl.Map({
                container: this._container,
                style: this.options.style,
                attributionControl: false,
                interactive: this.options.interactive,
                center: [0, 0],
                zoom: 0
            });

            // Sync initial position
            this._syncPosition();

            // Emit load event
            this._maplibreMap.on('load', function() {
                self._loaded = true;
                self.fire('load');
            });
        },

        _syncPosition: function() {
            if (!this._map || !this._maplibreMap) return;

            var center = this._map.getCenter();
            var zoom = this._map.getZoom();
            var bearing = this._map.getBearing();
            var pitch = this._map.getPitch();

            this._maplibreMap.jumpTo({
                center: [center.lng, center.lat],
                zoom: zoom,
                bearing: bearing,
                pitch: pitch
            });
        },

        getMap: function() {
            return this._maplibreMap;
        },

        getCanvas: function() {
            if (this._maplibreMap) {
                return this._maplibreMap.getCanvas();
            }
            return null;
        }
    });

    // Factory function
    L.maplibreGL = function(options) {
        return new L.MapLibreGL(options);
    };

    // Also expose as L.MapLibre (alias)
    L.MapLibre = L.MapLibreGL;

    console.log('[Leaflet-MapLibre-GL] Plugin loaded');
})();
